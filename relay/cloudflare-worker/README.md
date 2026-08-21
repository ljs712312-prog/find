# Free Cloudflare Workers relay

This is the recommended **zero-additional-cost** fallback relay for the Streamlit Community Cloud deployment.
The Streamlit app still calls BuildingHUB directly first. Only direct `connect_timeout`, DNS/connection, or TLS failures fall back to this Worker.

## Why this path

- Cloudflare Workers has a Free plan.
- The Worker stores the BuildingHUB API key as a Worker secret, never in browser code.
- The relay URL is fixed to `apis.data.go.kr/1613000/BldRgstHubService` and only the existing allowlisted BuildingHUB endpoints/parameters are accepted.
- `placement.hostname = "apis.data.go.kr"` asks Cloudflare to execute the Worker near the BuildingHUB upstream rather than near the Streamlit caller.
- No GCP billing project or Cloud Run deployment is required.

## Deploy

Requirements: Node.js 20+ and a free Cloudflare account.

```powershell
Set-Location relay\cloudflare-worker
npx wrangler@latest login
npx wrangler@latest deploy
```

The first deploy prints a `https://...workers.dev` URL.

Set the two Worker secrets interactively. Never put their values in Git or command history:

```powershell
npx wrangler@latest secret put DATA_GO_SERVICE_KEY
npx wrangler@latest secret put RELAY_HMAC_SECRET
```

- `DATA_GO_SERVICE_KEY`: the existing public-data BuildingHUB service key.
- `RELAY_HMAC_SECRET`: a new random secret of at least 32 UTF-8 bytes. Use the same value in Streamlit Community Cloud.

Then set Streamlit Community Cloud secrets:

```toml
BUILDING_HUB_API_KEY = "existing BuildingHUB key used for direct-first access"
BUILDING_HUB_RELAY_URL = "https://your-worker.workers.dev"
BUILDING_HUB_RELAY_HMAC_SECRET = "same random HMAC secret"
```

Do not remove `BUILDING_HUB_API_KEY`: direct access remains the first path and the relay is only a transport fallback.

## Optional replay cache

HMAC + timestamp + nonce authentication works without storage. If strict replay rejection across Worker isolates is desired, bind a Workers KV namespace as `RELAY_NONCES`. The code automatically uses it when present. This is optional because it adds another quota/resource to operate.

## Verify

```powershell
Invoke-RestMethod https://your-worker.workers.dev/healthz
```

Expected:

```json
{"status":"ok"}
```

`/healthz` never calls BuildingHUB and does not consume BuildingHUB API quota.

Run local unit tests:

```powershell
npm test
```
