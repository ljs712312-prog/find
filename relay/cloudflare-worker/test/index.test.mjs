import test from "node:test";
import assert from "node:assert/strict";
import crypto from "node:crypto";
import worker, { canonicalJson } from "../src/index.mjs";

function sign(secret, timestamp, nonce, endpoint, body) {
  return crypto.createHmac("sha256", secret)
    .update(`${timestamp}\n${nonce}\n${endpoint}\n${canonicalJson(body)}`)
    .digest("hex");
}

function requestFor(endpoint, body, secret, overrides = {}) {
  const timestamp = String(Math.floor(Date.now() / 1000));
  const nonce = "abcdefghijklmnopQRSTUVWX12345678";
  const signature = sign(secret, timestamp, nonce, endpoint, body);
  return new Request(`https://relay.example/v1/building-hub/${endpoint}`, {
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

test("canonical JSON matches sorted Python-style serialization", () => {
  assert.equal(canonicalJson({ z: 1, a: { y: 2, x: "한글" } }), '{"a":{"x":"한글","y":2},"z":1}');
});

test("health endpoint does not require secrets", async () => {
  const response = await worker.fetch(new Request("https://relay.example/healthz"), {});
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { status: "ok" });
});

test("unknown endpoint is rejected", async () => {
  const response = await worker.fetch(
    new Request("https://relay.example/v1/building-hub/evil", { method: "POST", body: "{}" }),
    { DATA_GO_SERVICE_KEY: "x", RELAY_HMAC_SECRET: "x".repeat(32) },
  );
  assert.equal(response.status, 400);
});

test("valid signed request forwards only to fixed upstream", async () => {
  const secret = "h".repeat(48);
  const body = { params: { sigunguCd: "41110", bjdongCd: "10100", platGbCd: "0", bun: "396", ji: "30", pageNo: 1, numOfRows: 100, _type: "json" } };
  const originalFetch = globalThis.fetch;
  let forwarded;
  globalThis.fetch = async (url) => {
    forwarded = new URL(url);
    return new Response('{"response":{"header":{"resultCode":"00"},"body":{"items":"","totalCount":0,"pageNo":1}}}', { status: 200, headers: { "content-type": "application/json" } });
  };
  try {
    const response = await worker.fetch(requestFor("getBrTitleInfo", body, secret), { DATA_GO_SERVICE_KEY: "PUBLIC-KEY", RELAY_HMAC_SECRET: secret });
    assert.equal(response.status, 200);
    assert.equal(forwarded.origin, "https://apis.data.go.kr");
    assert.equal(forwarded.pathname, "/1613000/BldRgstHubService/getBrTitleInfo");
    assert.equal(forwarded.searchParams.get("serviceKey"), "PUBLIC-KEY");
    assert.equal(forwarded.searchParams.get("bun"), "0396");
    assert.equal(forwarded.searchParams.get("ji"), "0030");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("bad signature is rejected before upstream call", async () => {
  const secret = "h".repeat(48);
  const body = { params: { sigunguCd: "41110", bjdongCd: "10100", platGbCd: "0", bun: "396", ji: "30" } };
  const request = requestFor("getBrTitleInfo", body, secret, { "x-building-hub-signature": "0".repeat(64) });
  const response = await worker.fetch(request, { DATA_GO_SERVICE_KEY: "PUBLIC-KEY", RELAY_HMAC_SECRET: secret });
  assert.equal(response.status, 401);
});

test("serviceKey injection in body is rejected", async () => {
  const secret = "h".repeat(48);
  const body = { params: { sigunguCd: "41110", bjdongCd: "10100", platGbCd: "0", bun: "396", ji: "30", serviceKey: "attacker" } };
  const response = await worker.fetch(requestFor("getBrTitleInfo", body, secret), { DATA_GO_SERVICE_KEY: "PUBLIC-KEY", RELAY_HMAC_SECRET: secret });
  assert.equal(response.status, 400);
});
