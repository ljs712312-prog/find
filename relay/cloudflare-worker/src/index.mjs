const UPSTREAM_BASE_URL = "https://apis.data.go.kr/1613000/BldRgstHubService";
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
const HMAC_DERIVATION_PREFIX = "buildinghub-relay-v1\u0000";
const encoder = new TextEncoder();

export default {
  async fetch(request, env) {
    if (request.method === "GET" && new URL(request.url).pathname === "/healthz") {
      return jsonResponse({ status: "ok" }, 200);
    }

    const url = new URL(request.url);
    const match = url.pathname.match(/^\/v1\/building-hub\/([^/]+)$/);
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
      });
    } catch {
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
    headers.set("cache-control", "no-store");
    return new Response(responseBytes, { status: upstream.status, headers });
  },
};

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
  const expected = [...digest].map((b) => b.toString(16).padStart(2, "0")).join("");
  return timingSafeEqualHex(expected, signature);
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

function timingSafeEqualHex(a, b) {
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i = 0; i < a.length; i += 1) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}

function jsonResponse(value, status) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
  });
}
