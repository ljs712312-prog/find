const UPSTREAM_BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService";
const REALTY_PRICE_ORIGIN = "https://www.realtyprice.kr";
const REALTY_PRICE_ENDPOINTS = new Map([
  ["individual", "/notice/search/hpiSearchListApi.search"],
  ["collective-options", "/notice/search/searchApt.search"],
  ["collective-prices", "/notice/search/townPriceListPastYearMap.search"],
]);
const ALLOWED_ENDPOINTS = new Set([
  "getBrTitleInfo",
  "getBrBasisOulnInfo",
  "getBrFlrOulnInfo",
  "getBrExposPubuseAreaInfo",
  "getBrHsprcInfo",
  "getBrExposInfo",
  "getBrWclfInfo",
  "getBrRecapTitleInfo",
  "getBrAtchJibunInfo",
  "getBrJijiguInfo",
]);
const OPTIONAL_DATE_FIELDS = new Set(["startDate", "endDate"]);
const EXPOS_ONLY_FIELDS = new Set(["dongNm", "hoNm"]);
const REQUIRED_FIELDS = new Set(["sigunguCd", "bjdongCd", "platGbCd", "bun", "ji"]);
const PAGING_FIELDS = new Set(["pageNo", "numOfRows", "_type"]);
const MAX_BODY_BYTES = 8192;
const MAX_RESPONSE_BYTES = 1_000_000;
const MAX_CLOCK_SKEW_SECONDS = 300;
const UPSTREAM_TIMEOUT_MS = 12_000;
const HMAC_DERIVATION_PREFIX = "buildinghub-relay-v1\u0000";
const encoder = new TextEncoder();

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = url.pathname.replace(/\/+$/, "");
    if (request.method === "GET" && path.endsWith("/healthz")) {
      return jsonResponse({ status: "ok" }, 200);
    }
    if (request.method === "GET" && path.endsWith("/readyz")) {
      return env.DATA_GO_SERVICE_KEY
        ? jsonResponse({ status: "ready" }, 200)
        : jsonResponse({ status: "not_configured" }, 503);
    }

    const realtyMatch = url.pathname.match(/\/v1\/realty-price\/([^/]+)$/);
    if (request.method === "POST" && realtyMatch) {
      return relayRealtyPrice(request, env, realtyMatch[1]);
    }

    // Supabase prefixes function paths with `/functions/v1/<function-name>`.
    // Matching the route at the end keeps the same core usable by both
    // standalone Workers and Supabase Edge Functions.
    const match = url.pathname.match(/\/v1\/building-hub\/([^/]+)$/);
    if (request.method !== "POST" || !match) {
      return jsonResponse({ error: "not_found" }, 404);
    }

    if (!env.DATA_GO_SERVICE_KEY) {
      return jsonResponse({ error: "relay_not_configured" }, 503);
    }

    let endpoint;
    try {
      endpoint = decodeURIComponent(match[1]);
    } catch {
      return jsonResponse({ error: "invalid_endpoint" }, 400);
    }
    if (!ALLOWED_ENDPOINTS.has(endpoint)) {
      return jsonResponse({ error: "invalid_endpoint" }, 400);
    }

    const contentLength = Number(request.headers.get("content-length") || "0");
    if (Number.isFinite(contentLength) && contentLength > MAX_BODY_BYTES) {
      return jsonResponse({ error: "request_too_large" }, 413);
    }

    const rawBody = await request.text();
    if (encoder.encode(rawBody).byteLength > MAX_BODY_BYTES) {
      return jsonResponse({ error: "request_too_large" }, 413);
    }

    let body;
    try {
      body = JSON.parse(rawBody);
    } catch {
      return jsonResponse({ error: "invalid_json" }, 400);
    }
    if (!isPlainObject(body) || Object.keys(body).length !== 1 || !isPlainObject(body.params)) {
      return jsonResponse({ error: "invalid_request" }, 400);
    }

    const authOk = await authenticateRequest(request.headers, endpoint, body, env);
    if (!authOk) {
      return jsonResponse({ error: "unauthorized" }, 401);
    }

    let params;
    try {
      params = validateParams(endpoint, body.params);
    } catch {
      return jsonResponse({ error: "invalid_params" }, 400);
    }

    // Optional replay protection. Bind a Workers KV namespace as RELAY_NONCES
    // if you want cross-isolate replay rejection. The relay remains authenticated
    // without it because every request is HMAC-signed and time-bounded over TLS.
    if (env.RELAY_NONCES) {
      const nonce = request.headers.get("x-building-hub-nonce");
      const nonceKey = `n:${nonce}`;
      if (await env.RELAY_NONCES.get(nonceKey)) {
        return jsonResponse({ error: "unauthorized" }, 401);
      }
      await env.RELAY_NONCES.put(nonceKey, "1", { expirationTtl: (MAX_CLOCK_SKEW_SECONDS * 2) + 30 });
    }

    const upstreamUrl = new URL(`${UPSTREAM_BASE_URL}/${endpoint}`);
    for (const [key, value] of Object.entries(params)) {
      upstreamUrl.searchParams.set(key, String(value));
    }
    upstreamUrl.searchParams.set("serviceKey", String(env.DATA_GO_SERVICE_KEY));

    let upstream;
    try {
      upstream = await fetch(upstreamUrl.toString(), {
        method: "GET",
        headers: { Accept: "application/json, application/xml" },
        redirect: "manual",
        signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
      });
    } catch (error) {
      console.error(JSON.stringify({
        message: "BuildingHUB upstream request failed",
        endpoint,
        error: error instanceof Error ? error.name : "UnknownError",
      }));
      return jsonResponse({ error: "upstream_unreachable" }, 503);
    }

    if (upstream.status >= 300 && upstream.status < 400) {
      return jsonResponse({ error: "upstream_redirect_rejected" }, 502);
    }

    const responseBytes = await upstream.arrayBuffer();
    if (responseBytes.byteLength > MAX_RESPONSE_BYTES) {
      return jsonResponse({ error: "upstream_response_too_large" }, 502);
    }

    const headers = new Headers();
    const contentType = upstream.headers.get("content-type");
    if (contentType) headers.set("content-type", contentType);
    if (env.SB_REGION) headers.set("x-relay-region", String(env.SB_REGION));
    headers.set("cache-control", "no-store");
    return new Response(responseBytes, { status: upstream.status, headers });
  },
};

async function relayRealtyPrice(request, env, encodedEndpoint) {
  if (!env.DATA_GO_SERVICE_KEY) {
    return jsonResponse({ error: "relay_not_configured" }, 503);
  }

  let endpoint;
  try {
    endpoint = decodeURIComponent(encodedEndpoint);
  } catch {
    return jsonResponse({ error: "invalid_endpoint" }, 400);
  }
  const upstreamPath = REALTY_PRICE_ENDPOINTS.get(endpoint);
  if (!upstreamPath) {
    return jsonResponse({ error: "invalid_endpoint" }, 400);
  }

  const contentLength = Number(request.headers.get("content-length") || "0");
  if (Number.isFinite(contentLength) && contentLength > MAX_BODY_BYTES) {
    return jsonResponse({ error: "request_too_large" }, 413);
  }
  const rawBody = await request.text();
  if (encoder.encode(rawBody).byteLength > MAX_BODY_BYTES) {
    return jsonResponse({ error: "request_too_large" }, 413);
  }

  let body;
  try {
    body = JSON.parse(rawBody);
  } catch {
    return jsonResponse({ error: "invalid_json" }, 400);
  }
  if (!isPlainObject(body) || Object.keys(body).length !== 1 || !isPlainObject(body.params)) {
    return jsonResponse({ error: "invalid_request" }, 400);
  }
  if (!await authenticateRequest(request.headers, `realty-price:${endpoint}`, body, env)) {
    return jsonResponse({ error: "unauthorized" }, 401);
  }

  let params;
  try {
    params = validateRealtyPriceParams(endpoint, body.params);
  } catch {
    return jsonResponse({ error: "invalid_params" }, 400);
  }

  const upstreamUrl = new URL(`${REALTY_PRICE_ORIGIN}${upstreamPath}`);
  for (const [key, value] of Object.entries(params)) {
    upstreamUrl.searchParams.set(key, String(value));
  }
  let upstream;
  try {
    upstream = await fetch(upstreamUrl.toString(), {
      method: "GET",
      headers: {
        Accept: "application/json",
        Referer: endpoint === "individual"
          ? `${REALTY_PRICE_ORIGIN}/notice/hpindividual/search.htm`
          : `${REALTY_PRICE_ORIGIN}/notice/town/searchPastYear.htm`,
        "X-Requested-With": "XMLHttpRequest",
      },
      redirect: "manual",
      signal: AbortSignal.timeout(UPSTREAM_TIMEOUT_MS),
    });
  } catch (error) {
    console.error(JSON.stringify({
      message: "RealtyPrice upstream request failed",
      endpoint,
      error: error instanceof Error ? error.name : "UnknownError",
    }));
    return jsonResponse({ error: "upstream_unreachable" }, 503);
  }
  if (upstream.status >= 300 && upstream.status < 400) {
    return jsonResponse({ error: "upstream_redirect_rejected" }, 502);
  }
  const responseBytes = await upstream.arrayBuffer();
  if (responseBytes.byteLength > MAX_RESPONSE_BYTES) {
    return jsonResponse({ error: "upstream_response_too_large" }, 502);
  }
  const headers = new Headers();
  const contentType = upstream.headers.get("content-type");
  if (contentType) headers.set("content-type", contentType);
  if (env.SB_REGION) headers.set("x-relay-region", String(env.SB_REGION));
  headers.set("cache-control", "no-store");
  return new Response(responseBytes, { status: upstream.status, headers });
}

function validateRealtyPriceParams(endpoint, raw) {
  const allowedByEndpoint = {
    individual: new Set(["reg", "eub", "san", "bun1", "bun2", "from_year", "to_year"]),
    "collective-options": new Set(["reg", "eub", "bun1", "bun2", "year", "notice_date", "gbnApt", "apt_code", "dong_code"]),
    "collective-prices": new Set(["reg", "eub", "bun1", "bun2", "year", "notice_date", "apt_code", "dong_code", "ho_code"]),
  };
  const allowed = allowedByEndpoint[endpoint];
  if (!allowed || Object.keys(raw).some((key) => !allowed.has(key))) {
    throw new Error("unsupported param");
  }

  const reg = digits(raw.reg, 5, 5);
  const eub = digits(raw.eub, 5, 5);
  const bun = digits(raw.bun1, 1, 4);
  const ji = digits(raw.bun2, 1, 4);
  if (endpoint === "individual") {
    const san = String(raw.san);
    if (san !== "1" && san !== "2") throw new Error("san");
    const fromYear = year(raw.from_year);
    const toYear = year(raw.to_year);
    if (Number(fromYear) > Number(toYear)) throw new Error("year range");
    return {
      page_no: "1", gbn: "1", year: "", reg, eub, san,
      bun1: bun.padStart(4, "0"), bun2: ji.padStart(4, "0"),
      road_code: "", p_initialword: "", build_bun1: "", build_bun2: "",
      from_year: fromYear, to_year: toYear, dong_gbn: "", tabGbn: "Text",
    };
  }

  const searchYear = year(raw.year);
  const noticeDate = optionalDate(raw.notice_date);
  const aptCode = optionalCode(raw.apt_code);
  const dongCode = optionalCode(raw.dong_code);
  const common = {
    gbn: "1", year: searchYear, notice_date: noticeDate,
    notice_date_year: `${searchYear}0430`, road_reg: "", road: "",
    initialword: "", build_bun1: "", build_bun2: "", reg, eub,
    apt_name: "", bun1: String(Number(bun)), bun2: String(Number(ji)),
    apt_code: aptCode, dong_code: dongCode, ho_code: "", past_yn: "1",
    init_gbn: "N", searchGbnRoad: "", searchGbnBunji: "1",
    searchGbnBunjiYear: "",
  };
  if (endpoint === "collective-options") {
    const stage = String(raw.gbnApt || "");
    if (!new Set(["", "DONG", "HO"]).has(stage)) throw new Error("gbnApt");
    if (stage === "DONG" && !aptCode) throw new Error("apt_code");
    if (stage === "HO" && (!aptCode || !dongCode)) throw new Error("codes");
    return { ...common, gbnApt: stage };
  }

  const hoCode = optionalCode(raw.ho_code);
  if (!noticeDate || !aptCode || !dongCode || !hoCode) throw new Error("codes");
  return {
    ...common, page_no: "1", reg_name: "", sreg: "", seub: "",
    old_reg: "", old_eub: "", ho_code: hoCode, tabGbn: "Text",
    full_addr_name: "", dong_name: "", ho_name: "", notice_amt: "",
    ktown_ho_seq: "", print_yn: "0", capcha: "", capcha_chk_yn: "",
    recaptcha_token: "",
  };
}

function year(value) {
  const text = digits(value, 4, 4);
  const number = Number(text);
  if (number < 2005 || number > new Date().getUTCFullYear() + 1) throw new Error("year");
  return text;
}

function optionalDate(value) {
  const text = String(value || "");
  if (!text) return "";
  const result = digits(text, 8, 8);
  if (!isValidDate(result)) throw new Error("date");
  return result;
}

function optionalCode(value) {
  const text = String(value || "");
  return text ? digits(text, 1, 30) : "";
}

export function canonicalJson(value) {
  if (value === null) return "null";
  if (typeof value === "string" || typeof value === "boolean") return JSON.stringify(value);
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new TypeError("non-finite number");
    return JSON.stringify(value);
  }
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(",")}]`;
  if (isPlainObject(value)) {
    return `{${Object.keys(value).sort().map((key) => `${JSON.stringify(key)}:${canonicalJson(value[key])}`).join(",")}}`;
  }
  throw new TypeError("unsupported JSON value");
}

async function relayHmacSecret(env) {
  if (env.RELAY_HMAC_SECRET) return String(env.RELAY_HMAC_SECRET);
  const material = encoder.encode(`${HMAC_DERIVATION_PREFIX}${String(env.DATA_GO_SERVICE_KEY)}`);
  const digest = new Uint8Array(await crypto.subtle.digest("SHA-256", material));
  return [...digest].map((b) => b.toString(16).padStart(2, "0")).join("");
}

async function authenticateRequest(headers, endpoint, body, env) {
  const timestamp = headers.get("x-building-hub-timestamp") || "";
  const nonce = headers.get("x-building-hub-nonce") || "";
  const signature = headers.get("x-building-hub-signature") || "";
  if (!/^[1-9][0-9]{9,10}$/.test(timestamp)) return false;
  if (!/^[A-Za-z0-9_-]{16,128}$/.test(nonce)) return false;
  if (!/^[0-9a-f]{64}$/.test(signature)) return false;
  const ts = Number(timestamp);
  if (!Number.isSafeInteger(ts) || Math.abs(Date.now() / 1000 - ts) > MAX_CLOCK_SKEW_SECONDS) return false;

  const signed = `${timestamp}\n${nonce}\n${endpoint}\n${canonicalJson(body)}`;
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(await relayHmacSecret(env)),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const digest = new Uint8Array(await crypto.subtle.sign("HMAC", key, encoder.encode(signed)));
  return timingSafeEqualBytes(digest, hexToBytes(signature));
}

function validateParams(endpoint, raw) {
  const allowed = new Set([...REQUIRED_FIELDS, ...PAGING_FIELDS, ...OPTIONAL_DATE_FIELDS]);
  if (endpoint === "getBrExposPubuseAreaInfo") {
    for (const field of EXPOS_ONLY_FIELDS) allowed.add(field);
  }
  for (const key of Object.keys(raw)) {
    if (!allowed.has(key)) throw new Error("unsupported param");
  }
  for (const key of REQUIRED_FIELDS) {
    if (!(key in raw)) throw new Error("missing param");
  }

  const sigunguCd = digits(raw.sigunguCd, 5, 5);
  const bjdongCd = digits(raw.bjdongCd, 5, 5);
  const platGbCd = String(raw.platGbCd);
  if (!new Set(["0", "1", "2"]).has(platGbCd)) throw new Error("platGbCd");
  const bun = digits(raw.bun, 1, 4).padStart(4, "0");
  const ji = digits(raw.ji, 1, 4).padStart(4, "0");
  const pageNo = integerInRange(raw.pageNo ?? 1, 1, 10000);
  const numOfRows = integerInRange(raw.numOfRows ?? 100, 1, 100);
  const type = String(raw._type ?? "json").toLowerCase();
  if (type !== "json" && type !== "xml") throw new Error("_type");

  const result = { sigunguCd, bjdongCd, platGbCd, bun, ji, pageNo, numOfRows, _type: type };
  for (const field of OPTIONAL_DATE_FIELDS) {
    if (field in raw) {
      const value = digits(raw[field], 8, 8);
      if (!isValidDate(value)) throw new Error(field);
      result[field] = value;
    }
  }
  if (endpoint === "getBrExposPubuseAreaInfo") {
    for (const field of EXPOS_ONLY_FIELDS) {
      if (field in raw) {
        const value = String(raw[field]).trim();
        if (!value || value.length > 100 || /[\u0000-\u001f\u007f]/.test(value)) throw new Error(field);
        result[field] = value;
      }
    }
  }
  return result;
}

function digits(value, min, max) {
  const text = String(value);
  if (!new RegExp(`^[0-9]{${min},${max}}$`).test(text)) throw new Error("digits");
  return text;
}

function integerInRange(value, min, max) {
  const number = Number(value);
  if (!Number.isInteger(number) || number < min || number > max) throw new Error("integer");
  return number;
}

function isValidDate(value) {
  const year = Number(value.slice(0, 4));
  const month = Number(value.slice(4, 6));
  const day = Number(value.slice(6, 8));
  const date = new Date(Date.UTC(year, month - 1, day));
  return date.getUTCFullYear() === year && date.getUTCMonth() === month - 1 && date.getUTCDate() === day;
}

function isPlainObject(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function hexToBytes(value) {
  const bytes = new Uint8Array(value.length / 2);
  for (let index = 0; index < value.length; index += 2) {
    bytes[index / 2] = Number.parseInt(value.slice(index, index + 2), 16);
  }
  return bytes;
}

function timingSafeEqualBytes(a, b) {
  if (typeof crypto.subtle.timingSafeEqual === "function") {
    return crypto.subtle.timingSafeEqual(a, b);
  }
  if (a.byteLength !== b.byteLength) return false;
  let difference = 0;
  for (let index = 0; index < a.byteLength; index += 1) {
    difference |= a[index] ^ b[index];
  }
  return difference === 0;
}

function jsonResponse(value, status) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
