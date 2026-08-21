from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file_path = Path(path)
    text = file_path.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one patch target, found {count}")
    file_path.write_text(text.replace(old, new), encoding="utf-8")


replace_once(
    "src/building_hub.py",
    "import requests\n\n\nLOGGER = logging.getLogger(__name__)\n",
    "import requests\n\nfrom .relay_config import DEFAULT_BUILDING_HUB_RELAY_URL\n\n\nLOGGER = logging.getLogger(__name__)\n",
)

replace_once(
    "src/building_hub.py",
    '''        raw_url = relay_url\n        if raw_url is None:\n            raw_url = os.environ.get(self._RELAY_URL_ENV)\n''',
    '''        raw_url = relay_url\n        if raw_url is None:\n            raw_url = os.environ.get(self._RELAY_URL_ENV) or DEFAULT_BUILDING_HUB_RELAY_URL\n''',
)
