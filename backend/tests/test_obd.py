"""Car Scanner OBD import: CSV parser, downsampling, health verdicts, endpoints."""

from __future__ import annotations

import datetime as dt

import pytest
from fastapi.testclient import TestClient

from app.services.obd import (
    MAX_SERIES_POINTS,
    ObdParseError,
    battery_verdict,
    downsample,
    dpf_verdict,
    injector_verdict,
    parse_obd_csv,
    summarize,
)

# Sample logs — shaped like the real Car Scanner ELM OBD2 exports the owner's
# 2016 Golf 1.6 TDI produces: one column per PID, headers carrying their unit
# in parentheses, and a profile-dependent language.

ENGLISH_CSV = """\
Time,Engine RPM (rpm),Vehicle speed (km/h),Coolant temperature (°C),\
Control module voltage (V),DPF soot mass (g),Distance since DPF regeneration (km),\
Injector correction 1 (mm3/st),Injector correction 2 (mm3/st)
0.0,850,0,88,14.2,18.4,120,0.5,-0.3
1.0,1500,20,89,14.1,18.6,121,0.7,-0.2
2.0,2100,45,90,14.0,18.8,122,0.6,-0.4
"""

# The Ukrainian profile also switches the delimiter to ';' and the decimal
# separator to ',' — a locale pairing that always travels together.
UKRAINIAN_CSV = """\
Час;Оберти двигуна (об/хв);Швидкість (км/год);Температура ОЖ (°C);Напруга (В);\
Маса сажі (г);Пробіг з останньої регенерації (км);Корекція форсунки 1 (мм3/такт);\
Корекція форсунки 2 (мм3/такт)
0,0;850;0;88;14,2;18,4;120;0,5;-0,3
1,0;1500;20;89;14,1;18,6;121;0,7;-0,2
2,0;2100;45;90;14,0;18,8;122;0,6;-0,4
"""

ABSOLUTE_TIME_CSV = """\
Time,Control module voltage (V)
2026-07-15T10:30:00,14.2
2026-07-15T10:30:05,14.1
2026-07-15T10:30:15,14.0
"""


def _keys(parsed: dict) -> set[str]:
    return {metric["key"] for metric in parsed["metrics"]}


def _metric(parsed: dict, key: str) -> dict:
    (found,) = [m for m in parsed["metrics"] if m["key"] == key]
    return found


# Column mapping


def test_parses_english_headers() -> None:
    parsed = parse_obd_csv(ENGLISH_CSV)

    assert _keys(parsed) == {
        "engine_rpm",
        "vehicle_speed",
        "coolant_temp",
        "battery_voltage",
        "dpf_soot_mass",
        "dpf_distance_since_regen",
        "injector_correction_1",
        "injector_correction_2",
    }
    soot = _metric(parsed, "dpf_soot_mass")
    assert soot["source_column"] == "DPF soot mass (g)"
    assert soot["samples"] == [(0.0, 18.4), (1.0, 18.6), (2.0, 18.8)]
    assert parsed["duration_s"] == 2.0
    assert parsed["unmapped_columns"] == []


def test_parses_ukrainian_headers_with_semicolons_and_decimal_commas() -> None:
    """Same drive, Ukrainian profile: mapping must land on the same keys."""
    parsed = parse_obd_csv(UKRAINIAN_CSV)

    assert _keys(parsed) == _keys(parse_obd_csv(ENGLISH_CSV))
    assert _metric(parsed, "dpf_soot_mass")["samples"] == [
        (0.0, 18.4),
        (1.0, 18.6),
        (2.0, 18.8),
    ]
    # The decimal comma has to survive on the time axis too, not just values.
    assert _metric(parsed, "battery_voltage")["samples"] == [
        (0.0, 14.2),
        (1.0, 14.1),
        (2.0, 14.0),
    ]
    assert _metric(parsed, "injector_correction_2")["samples"][0] == (0.0, -0.3)


def test_injector_columns_map_per_cylinder() -> None:
    csv_text = (
        "Time,Cylinder 1 correction (mm3),Cylinder 4 correction (mm3)\n0,1.2,-0.8\n"
    )
    parsed = parse_obd_csv(csv_text)

    assert _keys(parsed) == {"injector_correction_1", "injector_correction_4"}
    assert _metric(parsed, "injector_correction_4")["samples"] == [(0.0, -0.8)]


def test_units_are_read_off_the_header() -> None:
    parsed = parse_obd_csv(ENGLISH_CSV)
    assert _metric(parsed, "dpf_soot_mass")["unit"] == "g"
    assert _metric(parsed, "battery_voltage")["unit"] == "V"


def test_unknown_columns_are_reported_not_dropped() -> None:
    csv_text = (
        "Time,DPF soot mass (g),Ambient air pressure (kPa),Some vendor PID\n"
        "0,18.4,101,7\n"
    )
    parsed = parse_obd_csv(csv_text)

    assert _keys(parsed) == {"dpf_soot_mass"}
    assert parsed["unmapped_columns"] == ["Ambient air pressure (kPa)", "Some vendor PID"]


# Time axis


def test_relative_seconds_leave_recorded_at_unknown() -> None:
    parsed = parse_obd_csv(ENGLISH_CSV)
    assert parsed["recorded_at"] is None
    assert parsed["duration_s"] == 2.0


def test_absolute_timestamps_set_recorded_at_and_rebase_to_seconds() -> None:
    parsed = parse_obd_csv(ABSOLUTE_TIME_CSV)

    assert parsed["recorded_at"] == dt.datetime(2026, 7, 15, 10, 30, 0)
    assert parsed["duration_s"] == 15.0
    # The X axis the UI draws is seconds from the start of the log.
    assert _metric(parsed, "battery_voltage")["samples"] == [
        (0.0, 14.2),
        (5.0, 14.1),
        (15.0, 14.0),
    ]


# Robustness: junk cells, comment preambles, sanity ranges


def test_junk_cells_are_skipped_without_failing() -> None:
    csv_text = (
        "Time,DPF soot mass (g),Control module voltage (V)\n"
        "0,18.4,14.2\n"
        "1,,14.1\n"  # empty cell
        "2,NaN,14.0\n"
        "3,-,13.9\n"
        "4,18.8,\n"
        "5,18.9,14.3\n"
    )
    parsed = parse_obd_csv(csv_text)

    assert _metric(parsed, "dpf_soot_mass")["samples"] == [
        (0.0, 18.4),
        (4.0, 18.8),
        (5.0, 18.9),
    ]
    assert len(_metric(parsed, "battery_voltage")["samples"]) == 5


def test_comment_preamble_is_skipped() -> None:
    csv_text = (
        "# Car Scanner ELM OBD2 export\n"
        "# Volkswagen Golf 1.6 TDI\n"
        "\n"
        "Time,DPF soot mass (g)\n"
        "0,18.4\n"
    )
    parsed = parse_obd_csv(csv_text)
    assert _metric(parsed, "dpf_soot_mass")["samples"] == [(0.0, 18.4)]


def test_sanity_ranges_discard_obd_garbage() -> None:
    csv_text = (
        "Time,DPF soot mass (g),Control module voltage (V),Coolant temperature (°C),"
        "Injector correction 1 (mm3)\n"
        "0,18.4,14.2,88,0.5\n"
        "1,999,0.0,-300,50\n"  # every cell out of its sanity range
        "2,18.6,14.1,89,0.6\n"
    )
    parsed = parse_obd_csv(csv_text)

    assert _metric(parsed, "dpf_soot_mass")["samples"] == [(0.0, 18.4), (2.0, 18.6)]
    assert _metric(parsed, "battery_voltage")["samples"] == [(0.0, 14.2), (2.0, 14.1)]
    assert _metric(parsed, "coolant_temp")["samples"] == [(0.0, 88.0), (2.0, 89.0)]
    assert _metric(parsed, "injector_correction_1")["samples"] == [(0.0, 0.5), (2.0, 0.6)]


def test_csv_without_a_recognizable_time_column_is_rejected() -> None:
    with pytest.raises(ObdParseError):
        parse_obd_csv("alpha,beta\n1,2\n")


def test_empty_text_is_rejected() -> None:
    with pytest.raises(ObdParseError):
        parse_obd_csv("")


# Downsampling


def test_downsample_caps_the_series_and_keeps_the_extremes() -> None:
    # A 5000-point log with its min and max buried mid-series.
    samples = [(float(i), float(i % 7)) for i in range(5000)]
    samples[1234] = (1234.0, -99.0)
    samples[4321] = (4321.0, 99.0)

    series = downsample(samples)

    assert len(series) <= MAX_SERIES_POINTS
    assert (1234.0, -99.0) in series
    assert (4321.0, 99.0) in series
    assert series[0] == samples[0]
    assert series[-1] == samples[-1]
    # Evenly thinned, in time order.
    assert series == sorted(series, key=lambda point: point[0])


def test_downsample_leaves_short_series_untouched() -> None:
    samples = [(float(i), float(i)) for i in range(10)]
    assert downsample(samples) == samples


def test_summarize_reports_stats_over_the_full_series_not_the_downsample() -> None:
    samples = [(float(i), float(i % 7)) for i in range(5000)]
    samples[1234] = (1234.0, -99.0)

    summary = summarize("dpf_soot_mass", "g", samples)

    assert summary["min"] == -99.0
    assert summary["max"] == 6.0
    assert summary["last"] == samples[-1][1]
    assert len(summary["series"]) <= MAX_SERIES_POINTS


# Health verdicts — the reason the whole import exists


@pytest.mark.parametrize(
    ("soot", "level"),
    [(12.0, "ok"), (18.0, "ok"), (18.1, "warn"), (24.0, "warn"), (24.1, "crit")],
)
def test_dpf_verdict_thresholds(soot: float, level: str) -> None:
    verdict = dpf_verdict(soot, 120.0)
    assert verdict["level"] == level
    assert verdict["text"]


def test_dpf_verdict_without_data() -> None:
    assert dpf_verdict(None, None) is None


@pytest.mark.parametrize(
    ("corrections", "level"),
    [
        ([0.5, 0.6, 0.4, 0.7], "ok"),
        ([0.5, 0.6, 0.4, 3.8], "warn"),  # spread 3.4 > 3
        ([0.5, 0.6, 0.4, 5.6], "crit"),  # |5.6| > 5
        ([-6.0, 0.1, 0.2, 0.3], "crit"),
    ],
)
def test_injector_verdict_thresholds(corrections: list[float], level: str) -> None:
    verdict = injector_verdict(corrections)
    assert verdict["level"] == level


def test_injector_verdict_names_the_bad_cylinder() -> None:
    verdict = injector_verdict([0.5, 0.6, 5.6, 0.3])
    assert "3" in verdict["text"]


def test_injector_verdict_without_data() -> None:
    assert injector_verdict([]) is None


@pytest.mark.parametrize(
    ("voltage_min", "level"),
    [(13.9, "ok"), (12.2, "ok"), (12.1, "warn"), (9.6, "warn"), (9.5, "crit")],
)
def test_battery_verdict_thresholds(voltage_min: float, level: str) -> None:
    verdict = battery_verdict(voltage_min)
    assert verdict["level"] == level


def test_battery_verdict_without_data() -> None:
    assert battery_verdict(None) is None


# Endpoints


def _upload(
    client: TestClient,
    headers: dict,
    car_id: int,
    content: bytes | str = ENGLISH_CSV,
    filename: str = "golf.csv",
    content_type: str = "text/csv",
):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return client.post(
        f"/api/cars/{car_id}/obd",
        files={"file": (filename, content, content_type)},
        headers=headers,
    )


def test_upload_returns_session_metrics_and_verdicts(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = _upload(client, auth_headers, car["id"])

    assert response.status_code == 201, response.text
    body = response.json()
    assert body["session"]["filename"] == "golf.csv"
    assert body["session"]["sample_count"] == 3
    assert body["session"]["duration_s"] == 2.0
    assert {m["key"] for m in body["metrics"]} >= {"dpf_soot_mass", "battery_voltage"}
    assert body["unmapped_columns"] == []

    soot = next(m for m in body["metrics"] if m["key"] == "dpf_soot_mass")
    assert soot["last"] == 18.8
    assert soot["series"] == [[0.0, 18.4], [1.0, 18.6], [2.0, 18.8]]

    verdict_keys = {v["key"] for v in body["verdicts"]}
    assert verdict_keys == {"dpf", "injectors", "battery"}


def test_upload_of_a_high_soot_log_reports_a_critical_dpf(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    """The Golf runs an active P2002: a clogged DPF must read as critical."""
    car = make_car()
    csv_text = "Time,DPF soot mass (g),Distance since DPF regeneration (km)\n0,26.5,480\n"
    body = _upload(client, auth_headers, car["id"], content=csv_text).json()

    dpf = next(v for v in body["verdicts"] if v["key"] == "dpf")
    assert dpf["level"] == "crit"


def test_upload_rejects_non_csv_415(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = _upload(
        client,
        auth_headers,
        car["id"],
        content=b"\xff\xd8\xff",
        filename="photo.jpg",
        content_type="image/jpeg",
    )
    assert response.status_code == 415


def test_upload_rejects_unparsable_csv_422(
    client: TestClient, auth_headers: dict, make_car
) -> None:
    car = make_car()
    response = _upload(client, auth_headers, car["id"], content="alpha,beta\n1,2\n")
    assert response.status_code == 422


def test_upload_oversized_413(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car()
    response = _upload(
        client, auth_headers, car["id"], content=b"x" * (20 * 1024 * 1024 + 1)
    )
    assert response.status_code == 413


def test_upload_to_another_users_car_404(
    client: TestClient, auth_headers: dict, make_user, make_car
) -> None:
    car = make_car()
    other = make_user(email="other@example.com")
    assert _upload(client, other, car["id"]).status_code == 404


def test_list_sessions_only_returns_own_car(
    client: TestClient, auth_headers: dict, make_user, make_car
) -> None:
    car = make_car()
    _upload(client, auth_headers, car["id"])

    listed = client.get(f"/api/cars/{car['id']}/obd", headers=auth_headers)
    assert listed.status_code == 200
    assert len(listed.json()) == 1

    other = make_user(email="other@example.com")
    assert client.get(f"/api/cars/{car['id']}/obd", headers=other).status_code == 404


def test_get_session_detail(client: TestClient, auth_headers: dict, make_car) -> None:
    car = make_car()
    session_id = _upload(client, auth_headers, car["id"]).json()["session"]["id"]

    response = client.get(f"/api/obd/{session_id}", headers=auth_headers)
    assert response.status_code == 200
    body = response.json()
    assert body["session"]["id"] == session_id
    assert len(body["metrics"]) == 8
    assert len(body["verdicts"]) == 3


def test_get_session_of_another_user_404(
    client: TestClient, auth_headers: dict, make_user, make_car
) -> None:
    car = make_car()
    session_id = _upload(client, auth_headers, car["id"]).json()["session"]["id"]
    other = make_user(email="other@example.com")
    assert client.get(f"/api/obd/{session_id}", headers=other).status_code == 404


def test_delete_session_removes_its_metrics(
    client: TestClient, auth_headers: dict, make_car, db_session_factory
) -> None:
    from app.models import ObdMetric

    car = make_car()
    session_id = _upload(client, auth_headers, car["id"]).json()["session"]["id"]

    response = client.delete(f"/api/obd/{session_id}", headers=auth_headers)
    assert response.status_code == 204

    assert client.get(f"/api/obd/{session_id}", headers=auth_headers).status_code == 404
    with db_session_factory() as db:
        assert db.query(ObdMetric).filter_by(session_id=session_id).count() == 0


def test_delete_session_of_another_user_404(
    client: TestClient, auth_headers: dict, make_user, make_car
) -> None:
    car = make_car()
    session_id = _upload(client, auth_headers, car["id"]).json()["session"]["id"]
    other = make_user(email="other@example.com")
    assert client.delete(f"/api/obd/{session_id}", headers=other).status_code == 404
