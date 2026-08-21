# BuildingHUB authenticated relay

> **Recommended for zero-additional-cost operation:** use `relay/cloudflare-worker/`. It keeps the same Streamlit direct-first fallback contract, uses Cloudflare Workers Free, and requires no billed GCP project. The FastAPI/Cloud Run implementation below is retained as an optional alternative.

This is a deliberately narrow FastAPI relay for the official BuildingHUB
building-register service. It is intended to give the Streamlit Community
Cloud app a Korean cloud egress route when direct connections to
`apis.data.go.kr` fail.

It is **not** a generic proxy. It only accepts a small BldRgstHubService
endpoint allowlist, a parcel/pagination request schema, and an HMAC-signed
request from the Streamlit server. The browser must never call this service
directly.

## Wire contract

`POST /v1/building-hub/{endpoint}` accepts only these endpoint names:

- `getBrTitleInfo`
- `getBrBasisOulnInfo`
- `getBrFlrOulnInfo`
- `getBrExposPubuseAreaInfo`
- `getBrHsprcInfo`
- `getBrExposInfo`
- `getBrWclfInfo`
- `getBrRecapTitleInfo`
- `getBrAtchJibunInfo`
- `getBrJijiguInfo`

The JSON body has exactly one key, `params`. Its allowed fields are:

```json
{
  "params": {
    "sigunguCd": "41110",
    "bjdongCd": "10100",
    "platGbCd": "0",
    "bun": "396",
    "ji": "30",
    "pageNo": 1,
    "numOfRows": 100,
    "_type": "json"
  }
}
```

`sigunguCd` and `bjdongCd` must each be five ASCII digits; `platGbCd` is
`0`, `1`, or `2`; `bun` and `ji` are one to four digits and are padded to four
digits only while forwarding upstream. `pageNo` is 1–10,000 and `numOfRows`
is 1–100. `_type` is `json` (default) or `xml`.

The documented optional `startDate` and `endDate` filters are accepted as
valid `YYYYMMDD` dates on every listed endpoint. `dongNm` and `hoNm` are
accepted only for `getBrExposPubuseAreaInfo`, matching the official service
restriction. Any other field—including `serviceKey`, arbitrary URLs, headers,
or query-string parameters—is rejected.

Each request must have all three headers below:

```text
X-Building-Hub-Timestamp: Unix epoch seconds
X-Building-Hub-Nonce: 16–128 URL-safe random characters
X-Building-Hub-Signature: lowercase hexadecimal HMAC-SHA256
```

The signed bytes are UTF-8 text exactly as follows:

```text
{timestamp}\n{nonce}\n{endpoint}\n{canonical-json-body}
```

`endpoint` has no leading slash (for example, `getBrTitleInfo`).
`canonical-json-body` uses Python-equivalent JSON serialization:

```python
json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
```

The signature is `hmac.new(secret.encode("utf-8"), signed_bytes,
hashlib.sha256).hexdigest()`. The service allows a five-minute clock skew and
stores used nonces for the whole accepted timestamp window. Invalid signature,
stale timestamp, malformed nonce, and replay use the same `401` response.

The body returned to the Streamlit server is the validated BuildingHUB JSON or
XML envelope and retains the upstream HTTP status. Transient connection and
gateway failures return a safe `503` relay error; malformed/oversized upstream
responses return `502`. The official service key is never forwarded to the
browser or written to relay logs.

`GET /healthz` is a liveness endpoint and never calls BuildingHUB.

## Local test

From the repository root:

```powershell
python -m venv relay\.venv
.\relay\.venv\Scripts\Activate.ps1
pip install -r relay\requirements-dev.txt
pytest -q relay\tests
ruff check relay
```

For a local run, set secrets only in the current shell—never in a committed
file:

```powershell
$env:DATA_GO_SERVICE_KEY = "your-public-data-service-key"
$env:RELAY_HMAC_SECRET = "a-random-secret-at-least-32-utf8-bytes-long"
uvicorn relay.app:create_app --factory --host 127.0.0.1 --port 8080
```

The Docker build context must be `relay/`, not the repository root:

```powershell
Set-Location relay
docker build -t won-top-buildinghub-relay .
docker run --rm -p 8080:8080 `
  -e DATA_GO_SERVICE_KEY `
  -e RELAY_HMAC_SECRET `
  won-top-buildinghub-relay
```

## Cloud Run deployment (Seoul)

These are operator steps; do not put either value in source control, a Docker
build argument, a GitHub Actions log, or a browser-facing Streamlit component.
The Cloud Run endpoint is public only so Streamlit can reach it; the HMAC is
the application authentication layer.

1. Select a billed Google Cloud project and enable Cloud Run, Cloud Build, and
   Secret Manager APIs. Run the following from `relay/` after authenticating
   `gcloud` as a project administrator:

   ```powershell
   gcloud services enable run.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
   ```

2. Create two Secret Manager secrets. Enter each value only at the interactive
   prompt. Use the issued public-data key for `DATA_GO_SERVICE_KEY`; create a
   random 48-byte-or-longer URL-safe string for `RELAY_HMAC_SECRET` and retain
   it for the Streamlit server secret.

   ```powershell
   gcloud secrets create building-hub-service-key --replication-policy=automatic
   gcloud secrets versions add building-hub-service-key --data-file=-
   gcloud secrets create building-hub-relay-hmac --replication-policy=automatic
   gcloud secrets versions add building-hub-relay-hmac --data-file=-
   ```

3. Use a dedicated Cloud Run service account and grant it `Secret Manager
   Secret Accessor` on both secrets. Then deploy in Seoul. Keep one Uvicorn
   worker and one Cloud Run instance while using the included in-memory nonce
   cache.

   ```powershell
   $projectId = gcloud config get-value project
   $serviceAccount = "buildinghub-relay@$projectId.iam.gserviceaccount.com"
   gcloud iam service-accounts create buildinghub-relay
   gcloud secrets add-iam-policy-binding building-hub-service-key `
     --member="serviceAccount:$serviceAccount" `
     --role="roles/secretmanager.secretAccessor"
   gcloud secrets add-iam-policy-binding building-hub-relay-hmac `
     --member="serviceAccount:$serviceAccount" `
     --role="roles/secretmanager.secretAccessor"
   gcloud run deploy won-top-buildinghub-relay `
     --source . `
     --region asia-northeast3 `
     --allow-unauthenticated `
     --service-account "$serviceAccount" `
     --set-secrets "DATA_GO_SERVICE_KEY=building-hub-service-key:latest,RELAY_HMAC_SECRET=building-hub-relay-hmac:latest" `
     --max-instances 1
   ```

   The deploy command prints the relay URL; treat it as a server-side Streamlit
   setting, not a browser link.

4. In Streamlit Community Cloud secrets, add:

   ```toml
   BUILDING_HUB_RELAY_URL = "https://your-cloud-run-url"
   BUILDING_HUB_RELAY_HMAC_SECRET = "the-same-random-secret"
   ```

   Keep the existing `BUILDING_HUB_API_KEY` in Streamlit because the current
   application is direct-first and only invokes the relay after a qualifying
   transport failure. Do **not** set `DATA_GO_SERVICE_KEY` in Streamlit; that
   secret belongs only on the relay. The Streamlit backend must not forward
   the service key, an arbitrary URL, or user-controlled headers.

The nonce cache is intentionally in process and has no data-store dependency.
For more than one Cloud Run instance, multiple Uvicorn workers, or security
requirements that include replay prevention across restarts, replace it with a
shared atomic nonce store (for example, Memorystore Redis with a TTL) before
scaling. HMAC-over-TLS still authenticates all normal requests.

## Operational notes

- The destination is permanently fixed to
  `https://apis.data.go.kr/1613000/BldRgstHubService`; it cannot be redirected
  by request data or environment configuration.
- The relay uses HTTPS, disables proxy environment variables and redirects,
  limits request/response sizes, retries only safe upstream GET failures, and
  redacts the service key and encoded forms before returning an upstream body.
- Never log request URLs, request bodies, HMAC values, nonce values, or
  exceptions that may contain an upstream URL.
- Cloud Run health checks should target `/healthz`; the endpoint does not
  consume public-data quota.
