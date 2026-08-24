import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import worker, { canonicalJson } from "../src/index.mjs";

const HMAC_DERIVATION_PREFIX = "buildinghub-relay-v1\0";

function sign(secret, timestamp, nonce, endpoint, body) {
  return crypto.createHmac("sha256", secret)
    .update(`${timestamp}\n${nonce}\n${endpoint}\n${canonicalJson(body)}`)
    .digest("hex");
}

function derivedSecret(serviceKey) {
  return crypto.createHash("sha256")
    .update(`${HMAC_DERIVATION_PREFIX}${serviceKey}`)
    .digest("hex");
}

function requestFor(endpoint, body, secret, overrides = {}, basePath = "") {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = "abcdefghijklmnopQRSTUVWX12345678";
  const signature = sign(secret, timestamp, nonce, endpoint, body);
  return new Request(`https://relay.example${basePath}/v1/building-hub/${endpoint}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-building-hub-timestamp": timestamp,
      "x-building-hub-nonce": nonce,
      "x-building-hub-signature": signature,
      ...overrides,
    },
    body: JSON.stringify(body),
  });
}

function realtyRequestFor(endpoint, body, secret, basePath = "") {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = "realtyPriceNonceQRSTUVWX12345678";
  const signature = sign(secret, timestamp, nonce, `realty-price:${endpoint}`, body);
  return new Request(`https://relay.example${basePath}/v1/realty-price/${endpoint}`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      "x-building-hub-timestamp": timestamp,
      "x-building-hub-nonce": nonce,
      "x-building-hub-signature": signature,
    },
    body: JSON.stringify(body),
  });
}

test("canonical JSON matches sorted Python-style serialization", () => {
  assert.equal(canonicalJson({ z: 1, a: { y: 2, x: "한글" } }), '{"a":{"x":"한글","y":2},"z":1}');
});

test("health endpoint does not require secrets", async () => {
  const response = await worker.fetch(new Request("https://relay.example/healthz"), {});
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
});

test("readiness endpoint requires the upstream service key", async () => {
  const missing = await worker.fetch(new Request("https://relay.example/readyz"), {});
  assert.equal(missing.status, 503);
  assert.deepEqual(await missing.json(), { status: "not_configured" });

  const configured = await worker.fetch(
    new Request("https://relay.example/readyz"),
    { DATA_GO_SERVICE_KEY: "configured" },
  );
  assert.equal(configured.status, 200);
  assert.deepEqual(await configured.json(), { status: "ready" });
});

test("unknown endpoint is rejected", async () => {
  const response = await worker.fetch(
    new Request("https://relay.example/v1/building-hub/evil", { method: "POST", body: "{}" }),
    { DATA_GO_SERVICE_KEY: "x" },
  );
  assert.equal(response.status, 400);
});

test("valid signed request can derive HMAC from service key", async () => {
  const serviceKey = "PUBLIC-KEY";
  const secret = derivedSecret(serviceKey);
  const body = { params: { sigunguCd: "41110", bjdongCd: "10100", platGbCd: "0", bun: "396", ji: "30", pageNo: 1, numOfRows: 100, _type: "json" } };
  const originalFetch = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async (url) => {
    forwarded = new URL(url);
    return new Response('{"response":{"header":{"resultCode":"00"},"body":{"items":"","totalCount":0,"pageNo":1}}}', { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const response = await worker.fetch(requestFor("getBrTitleInfo", body, secret), { DATA_GO_SERVICE_KEY: serviceKey });
    assert.equal(response.status, 200);
    assert.equal(forwarded.origin, "https://apis.data.go.kr");
    assert.equal(forwarded.pathname, "/1613000/BldRgstHubService/getBrTitleInfo");
    assert.equal(forwarded.searchParams.get("serviceKey"), serviceKey);
    assert.equal(forwarded.searchParams.get("bun"), "0396");
    assert.equal(forwarded.searchParams.get("ji"), "0030");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("valid signed request accepts a Supabase function path prefix", async () => {
  const serviceKey = "PUBLIC-KEY";
  const secret = derivedSecret(serviceKey);
  const body = { params: { sigunguCd: "41115", bjdongCd: "14000", platGbCd: "0", bun: "585", ji: "1" } };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('{"response":{"header":{"resultCode":"00"},"body":{"items":"","totalCount":0,"pageNo":1}}}', { status: 200 });
  try {
    const response = await worker.fetch(
      requestFor(
        "getBrTitleInfo",
        body,
        secret,
        {},
        "/functions/v1/building-hub-relay",
      ),
      { DATA_GO_SERVICE_KEY: serviceKey, SB_REGION: "ap-northeast-2" },
    );
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("x-relay-region"), "ap-northeast-2");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("explicit relay secret remains backward compatible", async () => {
  const secret = "h".repeat(48);
  const body = { params: { sigunguCd: "41110", bjdongCd: "10100", platGbCd: "0", bun: "396", ji: "30" } };
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => new Response('{"response":{"header":{"resultCode":"00"},"body":{"items":"","totalCount":0,"pageNo":1}}}', { status: 200, headers: { "content-type": "application/json" } });
  try {
    const response = await worker.fetch(requestFor("getBrTitleInfo", body, secret), { DATA_GO_SERVICE_KEY: "PUBLIC-KEY", RELAY_HMAC_SECRET: secret });
    assert.equal(response.status, 200);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("bad signature is rejected before upstream call", async () => {
  const serviceKey = "PUBLIC-KEY";
  const secret = derivedSecret(serviceKey);
  const body = { params: { sigunguCd: "41110", bjdongCd: "10100", platGbCd: "0", bun: "396", ji: "30" } };
  const request = requestFor("getBrTitleInfo", body, secret, { "x-building-hub-signature": "0".repeat(64) });
  const response = await worker.fetch(request, { DATA_GO_SERVICE_KEY: serviceKey });
  assert.equal(response.status, 401);
});

test("serviceKey injection in body is rejected", async () => {
  const serviceKey = "PUBLIC-KEY";
  const secret = derivedSecret(serviceKey);
  const body = { params: { sigunguCd: "41110", bjdongCd: "10100", platGbCd: "0", bun: "396", ji: "30", serviceKey: "attacker" } };
  const response = await worker.fetch(requestFor("getBrTitleInfo", body, secret), { DATA_GO_SERVICE_KEY: serviceKey });
  assert.equal(response.status, 400);
});

test("signed individual-house price request is narrowly forwarded", async () => {
  const serviceKey = "PUBLIC-KEY";
  const secret = derivedSecret(serviceKey);
  const body = { params: { reg: "41111", eub: "13400", san: "1", bun1: "0396", bun2: "0030", from_year: "2005", to_year: "2026" } };
  const originalFetch = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async (url) => {
    forwarded = new URL(url);
    return new Response('{"model":{"list":[]}}', { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const response = await worker.fetch(
      realtyRequestFor("individual", body, secret, "/functions/v1/building-hub-relay"),
      { DATA_GO_SERVICE_KEY: serviceKey, SB_REGION: "ap-northeast-2" },
    );
    assert.equal(response.status, 200);
    assert.equal(forwarded.origin, "https://www.realtyprice.kr");
    assert.equal(forwarded.pathname, "/notice/search/hpiSearchListApi.search");
    assert.equal(forwarded.searchParams.get("bun1"), "0396");
    assert.equal(forwarded.searchParams.get("serviceKey"), null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("realty price relay rejects unknown parameters", async () => {
  const serviceKey = "PUBLIC-KEY";
  const secret = derivedSecret(serviceKey);
  const body = { params: { reg: "41111", eub: "13400", san: "1", bun1: "0396", bun2: "0030", from_year: "2005", to_year: "2026", url: "https://evil.example" } };
  const response = await worker.fetch(
    realtyRequestFor("individual", body, secret),
    { DATA_GO_SERVICE_KEY: serviceKey },
  );
  assert.equal(response.status, 400);
});
