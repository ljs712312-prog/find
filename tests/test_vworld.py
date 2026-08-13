from unittest.mock import Mock

import pytest
import requests

from src.address import parse_address
from src.vworld import (
    ViolationState,
    VWorldClient,
    VWorldError,
    land_key_to_pnu,
)


def response(payload, status=200):
    result = Mock()
    result.status_code = status
    result.json.return_value = payload
    result.text = ""
    return result


def test_land_and_mountain_pnu_are_distinct() -> None:
    normal = parse_address("오목천동 1-5").land_key
    mountain = parse_address("오목천동 산1-5").land_key

    assert land_key_to_pnu(normal) == "4111312900100010005"
    assert land_key_to_pnu(mountain) == "4111312900200010005"


def test_violation_yes_and_no_are_not_silently_collapsed() -> None:
    session = Mock()
    session.get.return_value = response(
        {
            "features": [
                {"properties": {"violt_bild": "1", "last_updt_dt": "2026-08-01"}},
                {"properties": {"violt_bild": "0", "last_updt_dt": "2026-08-02"}},
            ]
        }
    )
    client = VWorldClient("secret", domain="example.com", session=session)

    result = client.get_violation_reference(parse_address("망포동 6-11").land_key)

    assert result.state is ViolationState.MIXED
    assert result.as_of == "2026-08-02"
    _, kwargs = session.get.call_args
    assert kwargs["params"]["key"] == "secret"
    assert kwargs["params"]["domain"] == "example.com"
    assert "secret" not in str(result)


def test_empty_features_mean_unknown_not_no() -> None:
    session = Mock()
    session.get.return_value = response({"features": []})
    result = VWorldClient("secret", session=session).get_violation_reference(
        parse_address("망포동 6-11").land_key
    )
    assert result.state is ViolationState.UNKNOWN


def test_connection_error_does_not_expose_key() -> None:
    session = Mock()
    session.get.side_effect = requests.Timeout("secret")
    with pytest.raises(VWorldError) as error:
        VWorldClient("secret", session=session).get_violation_reference(
            parse_address("망포동 6-11").land_key
        )
    assert "secret" not in str(error.value)

