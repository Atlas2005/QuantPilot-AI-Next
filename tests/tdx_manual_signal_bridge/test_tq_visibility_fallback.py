from __future__ import annotations

from typing import Any

import pytest

import quantpilot_core.tdx_manual_signal_bridge.tq_visibility as module
from quantpilot_core.tdx_manual_signal_bridge.tq_visibility import (
    LiveTQVisibilityPublisher,
    TQVisibilityContractError,
    build_transition_warning_payloads,
    publish_experience_plan_visibility,
    publish_plan_to_installed_tq,
    publish_transition_warnings,
)


class _VisibilityApi:
    def __init__(self) -> None:
        self.block_calls: list[tuple[str, list[str]]] = []
        self.message_calls: list[str] = []
        self.warn_calls: list[dict[str, str]] = []

    def send_user_block(self, block_name: str, stock_list: list[str]):
        self.block_calls.append((block_name, stock_list))
        return {"ErrorId": 0, "Msg": "ok"}

    def send_message(self, message: str):
        self.message_calls.append(message)
        return '{"ErrorId":"0","Msg":"ok"}'

    def send_warn(
        self,
        stock_code: str,
        timestamp: str,
        price: str,
        state: str,
        reason: str,
    ):
        self.warn_calls.append(
            {
                "stock_code": stock_code,
                "timestamp": timestamp,
                "price": price,
                "state": state,
                "reason": reason,
            }
        )
        return {"ErrorId": "0", "Msg": "ok"}


def _plan() -> dict[str, Any]:
    return {
        "schema_version": "tdx_next_day_experience_plan_v1",
        "target_session": "2026-08-04",
        "candidates": [
            {
                "symbol": "SZ000002",
                "candidate_rank": 2,
                "deepseek_stance": "bullish",
            },
            {
                "symbol": "000001.SZ",
                "candidate_rank": 5,
                "deepseek_stance": "neutral",
            },
        ],
    }


def _signal(state: str = "ENTRY", **overrides: Any) -> dict[str, Any]:
    value = {
        "schema_version": "tdx_prediction_signal_v1",
        "signal_id": f"signal-{state}",
        "symbol": "000002.SZ",
        "timestamp": "2026-08-04T10:00:00+08:00",
        "state": state,
        "decision_price": 10.12,
        "candidate_rank": 2,
        "deepseek_stance": "bullish",
    }
    value.update(overrides)
    return value


def test_after_close_plan_uses_existing_order_for_user_block_and_message() -> None:
    api = _VisibilityApi()

    report = publish_experience_plan_visibility(_plan(), api=api, block_name="QP体验")

    assert api.block_calls == [("QP体验", ["000002.SZ", "000001.SZ"])]
    assert "2:000002.SZ:bullish" in api.message_calls[0]
    assert report["status"] == "candidate_block_published"
    assert report["full_provenance"] == "existing_experience_plan_and_json_csv"
    assert report["broker_or_order_api_calls"] is False


def test_warning_payloads_filter_hold_and_include_rank_stance_state_and_provenance() -> None:
    payloads = build_transition_warning_payloads(
        [_signal("ENTRY"), _signal("HOLD"), _signal("INVALIDATED")]
    )

    assert [payload["state"] for payload in payloads] == ["ENTRY", "INVALIDATED"]
    assert "rank=2" in payloads[0]["reason"]
    assert "DeepSeek=bullish" in payloads[0]["reason"]
    assert "买/ENTRY" in payloads[0]["reason"]
    assert "latest_prediction.json/csv" in payloads[0]["reason"]


def test_warning_api_receives_supported_keyword_contract() -> None:
    api = _VisibilityApi()

    report = publish_transition_warnings(
        [_signal("ENTRY"), _signal("WEAKENING")],
        api=api,
    )

    assert report["warning_count"] == 2
    assert [call["state"] for call in api.warn_calls] == ["ENTRY", "WEAKENING"]
    assert all(call["stock_code"] == "000002.SZ" for call in api.warn_calls)


def test_warning_fallback_runs_when_overlay_transport_fails_and_deduplicates(monkeypatch) -> None:
    api = _VisibilityApi()
    publisher = LiveTQVisibilityPublisher(api=api)
    monkeypatch.setattr(
        module,
        "publish_to_tq",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("overlay unavailable")),
    )
    signal = _signal("EXIT")

    first = publisher([signal])
    second = publisher([signal])

    assert first["overlay_error"]["error_type"] == "RuntimeError"
    assert first["warning_fallback"]["warning_count"] == 1
    assert second["warning_fallback"]["warning_count"] == 0
    assert len(api.warn_calls) == 1
    assert first["ordinary_chart_overlay_status"] == "pending_windows_visual_confirmation"


def test_historical_baseline_does_not_emit_stale_warning_and_next_transition_does(
    monkeypatch,
) -> None:
    api = _VisibilityApi()
    publisher = LiveTQVisibilityPublisher(api=api)
    monkeypatch.setattr(
        module,
        "publish_to_tq",
        lambda *_args, **_kwargs: {"transport_accepted": True},
    )
    historical = _signal("ENTRY")
    live = _signal("EXIT")

    baseline = publisher.publish_baseline([historical])
    current = publisher([historical, live])

    assert baseline["historical_baseline"] is True
    assert baseline["warning_fallback"]["warning_count"] == 0
    assert baseline["warning_fallback"]["suppressed_historical_transition_count"] == 1
    assert current["warning_fallback"]["warning_count"] == 1
    assert [call["state"] for call in api.warn_calls] == ["EXIT"]


def test_unknown_required_public_api_parameter_is_not_guessed() -> None:
    class _UnknownApi:
        def send_user_block(self, mystery):
            return None

        def send_message(self, message):
            return None

    with pytest.raises(TQVisibilityContractError, match="unsupported required"):
        publish_experience_plan_visibility(_plan(), api=_UnknownApi())


def test_opaque_positional_visibility_signature_is_not_called() -> None:
    class _OpaqueApi:
        def send_user_block(self, *args):
            raise AssertionError("opaque signature must not be guessed")

        def send_message(self, message):
            return None

    with pytest.raises(TQVisibilityContractError, match="opaque positional-only"):
        publish_experience_plan_visibility(_plan(), api=_OpaqueApi())


def test_optional_message_contract_failure_does_not_undo_candidate_block() -> None:
    class _BlockOnlyApi:
        def __init__(self) -> None:
            self.calls = []

        def send_user_block(self, block_name, stock_list):
            self.calls.append((block_name, stock_list))
            return {"ErrorId": 0}

        def send_message(self, unsupported_required_parameter):
            return None

    api = _BlockOnlyApi()

    report = publish_experience_plan_visibility(_plan(), api=api)

    assert api.calls == [("QP体验", ["000002.SZ", "000001.SZ"])]
    assert report["send_user_block"]["succeeded"] is True
    assert report["send_message"]["succeeded"] is False
    assert report["send_message"]["error_type"] == "TQVisibilityContractError"


def test_after_close_installed_adapter_uses_one_owned_lifecycle(
    tmp_path, monkeypatch
) -> None:
    class _InstalledApi(_VisibilityApi):
        def __init__(self) -> None:
            super().__init__()
            self.initialize_calls = []
            self.close_count = 0

        def initialize(self, path):
            self.initialize_calls.append(path)

        def close(self):
            self.close_count += 1

    api = _InstalledApi()
    module_path = tmp_path / "tqcenter.py"
    module_path.write_text("# local adapter fixture\n", encoding="utf-8")
    import quantpilot_core.tdx_manual_signal_bridge.tq_display_smoke as smoke

    monkeypatch.setattr(
        smoke,
        "load_installed_tqcenter",
        lambda _path: (object(), api, module_path),
    )
    monkeypatch.setattr(
        smoke,
        "inspect_tqcenter_api",
        lambda _api, _path: {
            "module_path": str(module_path),
            "module_sha256": "a" * 64,
            "functions": {
                "send_user_block": {"available": True, "signature": "(block_name, stock_list)"},
                "send_message": {"available": True, "signature": "(message)"},
            },
        },
    )

    report = publish_plan_to_installed_tq(
        _plan(),
        tdx_user_dir=tmp_path,
        initialize_path=__file__,
    )

    assert len(api.initialize_calls) == 1
    assert api.close_count == 1
    assert report["symbols"] == ["000002.SZ", "000001.SZ"]
    assert report["api_signatures"]["send_user_block"] == "(block_name, stock_list)"
