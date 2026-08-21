import relay from "../_shared/building_hub_relay.mjs";

Deno.serve((request: Request): Promise<Response> => {
  return relay.fetch(request, {
    DATA_GO_SERVICE_KEY: Deno.env.get("DATA_GO_SERVICE_KEY"),
    RELAY_HMAC_SECRET: Deno.env.get("RELAY_HMAC_SECRET"),
    SB_REGION: Deno.env.get("SB_REGION"),
  });
});
