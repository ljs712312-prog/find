"""Refresh Seoul legal-dong codes from MOIS's public full download."""

from collections import Counter
from datetime import date
import hashlib
from io import BytesIO
import json
from pathlib import Path
import urllib.request
import zipfile


SOURCE_URL = "https://www.code.go.kr/etc/codeFullDown.do?codeseId=00002"
OUTPUT = Path(__file__).resolve().parents[1] / "data" / "seoul_legal_dongs.json"


def build_snapshot(archive: bytes) -> dict:
    with zipfile.ZipFile(BytesIO(archive)) as zipped:
        names = zipped.namelist()
        if len(names) != 1:
            raise ValueError("Unexpected official archive layout")
        rows = zipped.read(names[0]).decode("cp949").splitlines()
    entries = []
    for line in rows:
        fields = line.split("\t")
        if len(fields) != 3:
            continue
        code, name, status = fields
        parts = name.split()
        if code.startswith("11") and status == "존재" and len(parts) == 3:
            entries.append({"code": code, "district": parts[1], "name": parts[2]})
    counts = Counter(row["district"] for row in entries)
    if len(counts) != 25 or len(entries) < 400:
        raise ValueError("Incomplete Seoul code download; existing file retained")
    if len({row["code"] for row in entries}) != len(entries):
        raise ValueError("Duplicate legal-dong codes")
    return {
        "source": "행정안전부 행정표준코드관리시스템 · 법정동 전체자료",
        "source_url": SOURCE_URL,
        "retrieved_on": date.today().isoformat(),
        "archive_sha256": hashlib.sha256(archive).hexdigest(),
        "legal_dongs": sorted(entries, key=lambda row: row["code"]),
    }


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, help="Use a downloaded official ZIP")
    args = parser.parse_args()
    if args.archive:
        archive = args.archive.read_bytes()
    else:
        request = urllib.request.Request(SOURCE_URL, data=b"codeseId=00002")
        with urllib.request.urlopen(request, timeout=60) as response:
            archive = response.read()
    snapshot = build_snapshot(archive)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(snapshot['legal_dongs'])} Seoul legal dongs to {OUTPUT.name}")
