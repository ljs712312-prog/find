import pandas as pd

from src.address import parse_address
from src.legacy import lookup_legacy


def frames():
    master = pd.DataFrame(
        [
            {
                "대지위치": "경기도 수원시 권선구 오목천동 1-5번지",
                "번": "0001",
                "지": "0005",
                "관리건축물대장PK": "normal",
            },
            {
                "대지위치": "경기도 수원시 권선구 오목천동 산1-5번지",
                "번": "0001",
                "지": "0005",
                "관리건축물대장PK": "mountain",
            },
        ]
    )
    floors = pd.DataFrame(
        [
            {"관리건축물대장PK": "normal", "층번호": "1"},
            {"관리건축물대장PK": "mountain", "층번호": "2"},
        ]
    )
    return master, floors


def test_mountain_and_normal_snapshot_rows_do_not_mix() -> None:
    master, floors = frames()
    normal = lookup_legacy(parse_address("오목천동 1-5"), master, floors)
    mountain = lookup_legacy(parse_address("오목천동 산1-5"), master, floors)

    assert [item.title["관리건축물대장PK"] for item in normal] == ["normal"]
    assert [item.title["관리건축물대장PK"] for item in mountain] == ["mountain"]
    assert normal[0].floors[0]["층번호"] == "1"
    assert mountain[0].floors[0]["층번호"] == "2"

