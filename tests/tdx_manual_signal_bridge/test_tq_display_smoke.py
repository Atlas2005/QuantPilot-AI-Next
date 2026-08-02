from __future__ import annotations

import json
from pathlib import Path

import pytest

from quantpilot_core.tdx_manual_signal_bridge.tq_display_smoke import (
    MINIMAL_FORMULA,
    build_minimal_smoke_payload,
    build_official_shape_smoke_payload,
    build_quantpilot_smoke_payload,
    inspect_tqcenter_api,
    minute_timestamps,
    run_tq_display_smoke,
)


class _FakeTQ:
    def __init__(self, responses: list[object] | None = None) -> None:
        self.responses = list(
            responses
            or [
                '{"ErrorId":"0","Msg":"发送TQ数据成功","run_id":"1"}',
                {"ErrorId": 0, "Msg": "发送TQ数据成功", "run_id": 2},
                {"ErrorId": "0", "Msg": "发送TQ数据成功", "run_id": "3"},
            ]
        )
        self.initialize_calls: list[str] = []
        self.send_calls: list[dict[str, object]] = []
        self.close_count = 0

    def initialize(self, path: str) -> None:
        self.initialize_calls.append(path)

    def send_bt_data(self, **kwargs):
        self.send_calls.append(kwargs)
        return self.responses.pop(0)

    def close(self) -> None:
        self.close_count += 1


def test_non_square_minimal_is_three_timestamp_rows_by_two_string_columns() -> None:
    timestamps = minute_timestamps("20260731144000")
    payload = build_minimal_smoke_payload("SZ000001", timestamps)

    assert payload == {
        "stock_code": "000001.SZ",
        "time_list": ["20260731144000", "20260731144100", "20260731144200"],
        "data_list": [["11.51", "11.61"], ["11.52", "11.62"], ["11.53", "11.63"]],
        "count": 3,
    }
    assert MINIMAL_FORMULA == "T1:SIGNALS_TQ(1,0);\nT2:SIGNALS_TQ(2,0);"


def test_exact_official_shape_is_two_rows_by_six_string_columns() -> None:
    payload = build_official_shape_smoke_payload(
        "000001.SZ",
        minute_timestamps("20260731144000"),
    )

    assert payload["count"] == 2
    assert payload["data_list"] == [
        ["1", "143.41", "200", "0", "0", "0"],
        ["0", "0", "0", "1", "143.48", "200"],
    ]


def test_quantpilot_payload_is_seven_rows_by_sixteen_string_columns() -> None:
    payload = build_quantpilot_smoke_payload(
        "000001.SZ",
        minute_timestamps("20260731144000"),
    )

    assert payload["count"] == 7
    assert len(payload["data_list"]) == 7
    assert {len(row) for row in payload["data_list"]} == {16}
    assert [row[1] for row in payload["data_list"]] == ["0", "0", "1", "2", "3", "4", "5"]
    assert [row[6] for row in payload["data_list"]][2:] == ["9.90"] * 5
    assert [row[8] for row in payload["data_list"]][2:] == ["9.70"] * 5
    assert [row[9] for row in payload["data_list"]][2:] == ["10.60"] * 5
    assert all(isinstance(value, str) for row in payload["data_list"] for value in row)


def test_smoke_sends_all_official_row_major_shapes_in_one_lifecycle(tmp_path: Path) -> None:
    module_path = tmp_path / "tqcenter.py"
    module_path.write_text("# exact installed adapter fixture\n", encoding="utf-8")
    api = _FakeTQ()
    ready: list[dict[str, object]] = []
    sleeps: list[float] = []

    result = run_tq_display_smoke(
        api,
        module_path=module_path,
        symbol="000001.SZ",
        timestamps=minute_timestamps("20260731144000"),
        initialize_path=__file__,
        hold_seconds=30,
        sleeper=sleeps.append,
        ready_callback=lambda value: ready.append(dict(value)),
    )

    assert len(api.initialize_calls) == 1
    assert len(api.send_calls) == 3
    assert [call["count"] for call in api.send_calls] == [3, 2, 7]
    assert api.close_count == 1
    assert sleeps == [30.0]
    assert ready[0]["visual_confirmation_required"] is True
    assert result["ordinary_chart_overlay_proven"] is False
    assert result["status"] == "transport_accepted_pending_visual_confirmation"
    assert result["formula_set_data_info_called"] is False
    assert result["exec_to_tdx_called"] is False
    assert result["run_id_reused_as_input"] is False
    assert result["minimal_transport_response"]["run_id"] == "1"
    assert result["official_shape_transport_response"]["run_id"] == 2
    assert result["quantpilot_transport_response"]["run_id"] == "3"


def test_non_square_probe_isolated_report_uses_only_three_selected_timestamps(
    tmp_path: Path,
) -> None:
    module_path = tmp_path / "tqcenter.py"
    module_path.write_text("# exact installed adapter fixture\n", encoding="utf-8")
    api = _FakeTQ(responses=[{"ErrorId": 0, "run_id": 9}])

    result = run_tq_display_smoke(
        api,
        module_path=module_path,
        symbol="000001.SZ",
        timestamps=minute_timestamps("20260731140000"),
        initialize_path=__file__,
        probe="non-square",
    )

    assert len(api.send_calls) == 1
    assert result["selected_probes"] == ["non-square"]
    assert result["timestamps"] == [
        "20260731140000",
        "20260731140100",
        "20260731140200",
    ]
    assert result["protocol_assertions"] == {
        "data_orientation": "row_major_by_timestamp",
        "count_equals_timestamp_count": True,
        "all_transmitted_scalars_are_numeric_strings": True,
    }


def test_smoke_closes_after_rejected_minimal_payload(tmp_path: Path) -> None:
    module_path = tmp_path / "tqcenter.py"
    module_path.write_text("# fixture\n", encoding="utf-8")
    api = _FakeTQ(responses=['{"ErrorId":"8","Msg":"rejected"}'])

    with pytest.raises(RuntimeError, match="non-square send_bt_data call failed"):
        run_tq_display_smoke(
            api,
            module_path=module_path,
            symbol="000001.SZ",
            timestamps=minute_timestamps("20260731144000"),
            initialize_path=__file__,
        )

    assert len(api.send_calls) == 1
    assert api.close_count == 1


def test_api_audit_records_exact_file_hash_and_signatures(tmp_path: Path) -> None:
    module_path = tmp_path / "tqcenter.py"
    module_path.write_text("# installed source\n", encoding="utf-8")
    audit = inspect_tqcenter_api(_FakeTQ(), module_path)

    assert audit["module_path"] == str(module_path.resolve())
    assert len(audit["module_sha256"]) == 64
    assert audit["functions"]["send_bt_data"]["available"] is True
    assert audit["functions"]["send_bt_data"]["signature"] == "(**kwargs)"
    assert audit["functions"]["formula_set_data_info"] == {"available": False}
    json.dumps(audit)


@pytest.mark.parametrize("start", ["20260731144001", "2026-07-31 14:40:00"])
def test_minute_timestamps_rejects_wrong_protocol_format(start: str) -> None:
    with pytest.raises(ValueError):
        minute_timestamps(start)
