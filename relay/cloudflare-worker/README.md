# Free Cloudflare Workers relay

This is the recommended **zero-additional-cost** fallback relay for the Streamlit Community Cloud deployment.
The Streamlit app still calls BuildingHUB directly first. Only direct `connect_timeout`, DNS/connection, or TLS failures fall back to this Worker.

## Why this path

- Cloudflare Workers has a Free plan.
- The Worker stores the BuildingHUB API key as a Worker secret, never in browser code.
- The relay URL is fixed to `apis.data.go.kr/1613000/BldRgstHubService` and only the existing allowlisted BuildingHUB endpoints/parameters are accepted.
- `placement.hostname = "apis.data.go.kr"` asks Cloudflare to execute the Worker near the BuildingHUB upstream rather than near the Streamlit caller.
- No GCP billing project or Cloud Run deployment is required.
- A second Streamlit HMAC secret is not required. The Streamlit backend and Worker derive the same domain-separated HMAC key from the existing BuildingHUB key without sending that key in relay requests.

## Recommended Windows deployment

Requirements: Node.js 20+ and a free Cloudflare account.

### Run from any PowerShell directory

This avoids the common `C:\WINDOWS\system32` relative-path problem:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -Command "irm 'https://raw.githubusercontent.com/ljs712312-prog/find/main/scripts/bootstrap_cloudflare_worker.ps1' | iex"
```

The bootstrap downloads the current `main` branch to a temporary folder and runs the real deployment helper there. The temporary copy is removed afterwards.

If you already have the repository checked out, you may instead run from the repository root:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_cloudflare_worker.ps1
```

The helper:

1. runs the Worker unit tests;
2. checks Cloudflare authentication and opens browser login when needed;
3. deploys the Worker;
4. asks for the existing `BUILDING_HUB_API_KEY` with hidden console input;
5. saves only that key as the Worker `DATA_GO_SERVICE_KEY` secret;
6. checks `/healthz`;
7. prints and copies the public `workers.dev` URL.

Send only that public Worker URL back to the maintainer/ChatGPT. Do **not** send the BuildingHUB API key. The URL can be committed to `src/relay_config.py`, after which Streamlit Community Cloud picks it up through the normal GitHub redeploy and no manual Streamlit secret edit is required.

## Manual deployment

```powershell
Set-Location relay\cloudflare-worker
npx wrangler@latest login
npx wrangler@latest deploy
npx wrangler@latest secret put DATA_GO_SERVICE_KEY
```

`DATA_GO_SERVICE_KEY` is the existing BuildingHUB public-data service key. `RELAY_HMAC_SECRET` is optional and supported only for backward compatibility with older deployments; new deployments do not need it.

The Streamlit app must keep its existing `BUILDING_HUB_API_KEY` because direct access remains the first path. A relay URL may be supplied either through `BUILDING_HUB_RELAY_URL` or the public default in `src/relay_config.py`.

## Optional replay cache

HMAC + timestamp + nonce authentication works without storage. If strict replay rejection across Worker isolates is desired, bind a Workers KV namespace as `RELAY_NONCES`. The code automatically uses it when present.

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
