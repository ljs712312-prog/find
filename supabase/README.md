# Supabase BuildingHUB relay

The production fallback relay is deployed as the `building-hub-relay` Edge
Function in Supabase's Seoul region. Streamlit calls the official BuildingHUB
API directly first and uses this endpoint only when no usable response arrives,
including connection, TLS, proxy, connect-timeout, read-timeout, and interrupted
response failures. The Streamlit client retries one transient relay transport or
`408`/`429`/`5xx` response with a fresh timestamp and nonce.

Required project secret:

- `DATA_GO_SERVICE_KEY`: the same BuildingHUB service key stored in Streamlit.

The function must have legacy JWT verification disabled because it performs its
own timestamped HMAC authentication. The service key itself is never included in
the Streamlit-to-relay request.

Health endpoints:

- `/functions/v1/building-hub-relay/healthz`
- `/functions/v1/building-hub-relay/readyz`

The client sends `X-Region: ap-northeast-2` so Supabase executes the invocation
in Seoul.

CLI deployment, when authenticated:

```powershell
supabase functions deploy building-hub-relay --project-ref hnkvahtiuindislwyogz --no-verify-jwt
```
