"""Public deployment defaults for the optional BuildingHUB relay.

The relay URL is not a credential.  It is intentionally kept in a tiny module so
Streamlit Community Cloud can receive a deployed relay URL through a normal
GitHub code update without requiring the user to edit Streamlit Secrets.
"""

DEFAULT_BUILDING_HUB_RELAY_URL = (
    "https://hnkvahtiuindislwyogz.supabase.co/functions/v1/building-hub-relay"
)
