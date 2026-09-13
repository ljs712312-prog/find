from types import SimpleNamespace as NS

import pytest

from src.room_count import total_rooms


def floor(name, detail):
    return NS(dong_name="", floor_group_code="10", floor_number=None,
              floor_name=name, other_purpose=detail)


def building(**kw):
    return NS(**{"unit_count": 0, "household_count": 0, "family_count": 0,
                 "other_purpose": "", "floors": (), **kw})


def test_officetel_register_count_is_separate_from_zero_households_and_families():
    value = total_rooms(building(unit_count=35))
    assert (value.count, value.source) == (35, "대장 호수")


def test_multi_house_explicit_room_count_is_labelled_as_reference():
    value = total_rooms(building(other_purpose="다중주택(16실)", family_count=1))
    assert value.count == 16 and "참고" in value.source


@pytest.mark.parametrize("missing", [None, 0, -1, True])
def test_absent_reported_count_does_not_mean_zero_actual_rooms(missing):
    assert total_rooms(building(unit_count=missing, household_count=20, family_count=8)).count is None


def test_officetel_floor_counts_exclude_auxiliary_rows_without_counting_floors_as_rooms():
    b = building(floors=(floor("1층", "주차장"), floor("1층", "장애인화장실,창고"),
                        floor("2층", "통신실"), floor("2층", "오피스텔(5호)"),
                        floor("3층", "오피스텔(6호)"), floor("옥탑1층", "계단실(연면적제외)")))
    value = total_rooms(b)
    assert value.count == 11 and "참고" in value.source
    assert total_rooms(b, allow_floor_reference=False).count is None


@pytest.mark.parametrize("detail", ["다중주택", "주택(3가구)", "오피스텔 201호", "오피스텔(20㎡)", "근린생활시설"])
def test_partial_or_non_count_floor_descriptions_do_not_become_total(detail):
    assert total_rooms(building(floors=(floor("1층", "오피스텔(6호)"), floor("2층", detail)))).count is None


def test_repeated_counts_on_same_floor_are_not_double_counted():
    assert total_rooms(building(floors=(floor("1층", "오피스텔(6호)"), floor("1층", "오피스텔(6호)")))).count is None


def test_reported_title_count_takes_priority_over_reference_text():
    assert total_rooms(building(unit_count=20, other_purpose="오피스텔(16호)")).count == 20
