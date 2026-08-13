"""Read-only fallback for the app's historical Suwon CSV snapshot.

This repository snapshot predates the BuildingHUB primary-key migration and
does not preserve the parent key needed to connect collective-building units.
It is therefore used only for building summaries and floors when the official
API is unavailable.  It must never be mixed with API unit rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import pandas as pd

from .address import ParsedAddress


@dataclass(frozen=True, slots=True)
class LegacyBuilding:
    title: dict[str, str]
    floors: tuple[dict[str, str], ...]


def _read_csv(path: Path) -> pd.DataFrame:
    if not path.exists():
        return pd.DataFrame()
    try:
        frame = pd.read_csv(path, dtype=str, encoding="utf-8")
    except UnicodeDecodeError:
        frame = pd.read_csv(path, dtype=str, encoding="cp949")
    return frame.fillna("").astype(str)


def load_legacy_frames(base_dir: str | Path = ".") -> tuple[pd.DataFrame, pd.DataFrame]:
    base = Path(base_dir)
    return (
        _read_csv(base / "suwon_building_master.csv.gz"),
        _read_csv(base / "suwon_floor_info.csv.gz"),
    )


def lookup_legacy(
    parsed: ParsedAddress,
    master: pd.DataFrame,
    floors: pd.DataFrame,
) -> tuple[LegacyBuilding, ...]:
    if master.empty:
        return ()
    required = {"대지위치", "번", "지", "관리건축물대장PK"}
    if not required.issubset(master.columns):
        return ()

    bun = parsed.land_key.bun
    ji = parsed.land_key.ji
    expected_suffix = f"{parsed.legal_dong} {parsed.lot_number}번지"
    address = master["대지위치"].str.strip()
    mask = (
        master["번"].str.zfill(4).eq(bun)
        & master["지"].str.zfill(4).eq(ji)
        & address.str.endswith(expected_suffix, na=False)
    )
    matched = master.loc[mask]
    results: list[LegacyBuilding] = []
    for row in matched.to_dict("records"):
        pk = str(row.get("관리건축물대장PK", ""))
        floor_rows: list[dict[str, str]] = []
        if not floors.empty and "관리건축물대장PK" in floors.columns:
            floor_rows = floors.loc[
                floors["관리건축물대장PK"].eq(pk)
            ].to_dict("records")
        results.append(
            LegacyBuilding(
                title={str(k): str(v) for k, v in row.items()},
                floors=tuple(
                    {str(k): str(v) for k, v in floor.items()}
                    for floor in floor_rows
                ),
            )
        )
    return tuple(results)
