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
    def __init__(
        self,
        *,
        create_response: object = None,
        block_response: object = None,
        message_response: object = None,
    ) -> None:
        self.create_response = (
            {"ErrorId": 0, "Msg": "ok"}
            if create_response is None
            else create_response
        )
        self.block_response = (
            {"ErrorId": 0, "Msg": "ok"}
            if block_response is None
            else block_response
        )
        self.message_response = (
            '{"ErrorId":"0","Msg":"ok"}'
            if message_response is None
            else message_response
        )
        self.call_order: list[str] = []
        self.create_calls: list[tuple[str, str]] = []
        self.block_calls: list[tuple[str, list[str], bool]] = []
        self.message_calls: list[str] = []
        self.warn_calls: list[dict[str, str]] = []

    def create_sector(self, block_code: str, block_name: str):
        self.call_order.append("create_sector")
        self.create_calls.append((block_code, block_name))
        return self.create_response

    def send_user_block(self, block_code: str, stocks: list[str], show: bool):
        self.call_order.append("send_user_block")
        self.block_calls.append((block_code, stocks, show))
        return self.block_response

    def send_message(self, message: str):
        self.call_order.append("send_message")
        self.message_calls.append(message)
        return self.message_response

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

    report = publish_experience_plan_visibility(_plan(), api=api)

    assert api.call_order[:2] == ["create_sector", "send_user_block"]
    assert api.create_calls == [("QPTY", "QP候选")]
    assert api.block_calls == [("QPTY", ["000002.SZ", "000001.SZ"], True)]
    assert "2:000002.SZ:bullish" in api.message_calls[0]
    assert report["status"] == "candidate_block_published"
    assert report["block_code"] == "QPTY"
    assert report["block_name"] == "QP候选"
    assert report["published_symbols"] == ["000002.SZ", "000001.SZ"]
    assert report["visibility_success"] is True
    assert report["sector_create_response"]["accepted"] is True
    assert report["user_block_response"]["accepted"] is True
    assert report["message_response"]["accepted"] is True
    assert report["full_provenance"] == "existing_experience_plan_and_json_csv"
    assert report["broker_or_order_api_calls"] is False


def test_real_send_message_msg_str_signature_is_bound_by_keyword() -> None:
    class _MsgStrApi(_VisibilityApi):
        def __init__(self) -> None:
            super().__init__()
            self.msg_str_calls = []

        def send_message(self, msg_str: str):
            self.call_order.append("send_message")
            self.msg_str_calls.append(msg_str)
            return {"ErrorId": 0, "Msg": "ok"}

    api = _MsgStrApi()
    report = publish_experience_plan_visibility(_plan(), api=api)
    assert len(api.msg_str_calls) == 1
    assert "000002.SZ" in api.msg_str_calls[0]
    assert report["send_message"]["argument_names"] == ["msg_str"]
    assert report["send_message"]["succeeded"] is True
    assert report["visibility_success"] is True


def test_custom_block_code_name_and_show_are_separate_and_configurable() -> None:
    api = _VisibilityApi()

    report = publish_experience_plan_visibility(
        _plan(),
        api=api,
        block_code="QPX1",
        block_name="量化候选",
        show=False,
    )

    assert api.create_calls == [("QPX1", "量化候选")]
    assert api.block_calls == [("QPX1", ["000002.SZ", "000001.SZ"], False)]
    assert all(call[0] != "量化候选" for call in api.block_calls)
    assert report["block_code"] == "QPX1"
    assert report["block_name"] == "量化候选"
    assert report["show"] is False


@pytest.mark.parametrize(
    ("create_response", "block_response", "failed_stage"),
    [
        ({}, {"ErrorId": 0}, "sector"),
        ({"ErrorId": 9, "Msg": "create failed"}, {"ErrorId": 0}, "sector"),
        ({"ErrorId": 0}, {}, "block"),
        ({"ErrorId": 0}, {"ErrorId": 8, "Msg": "block failed"}, "block"),
    ],
)
def test_empty_or_nonzero_sector_and_block_responses_fail_visibility(
    create_response,
    block_response,
    failed_stage,
) -> None:
    api = _VisibilityApi(
        create_response=create_response,
        block_response=block_response,
    )

    report = publish_experience_plan_visibility(_plan(), api=api)

    assert report["visibility_success"] is False
    assert report["status"] == "candidate_block_publish_failed"
    assert report["published_symbols"] == []
    if failed_stage == "sector":
        assert api.block_calls == []
        assert report["sector_create_response"]["accepted"] is not True
    else:
        assert api.block_calls
        assert report["user_block_response"]["accepted"] is not True


def test_explicit_already_existing_sector_continues_only_when_publication_works() -> None:
    usable = _VisibilityApi(
        create_response={"ErrorId": 12, "Msg": "板块已存在"},
        block_response={"ErrorId": 0, "Msg": "ok"},
    )
    unusable = _VisibilityApi(
        create_response={"ErrorId": 12, "Msg": "板块已存在"},
        block_response={"ErrorId": 13, "Msg": "unknown block"},
    )

    usable_report = publish_experience_plan_visibility(_plan(), api=usable)
    unusable_report = publish_experience_plan_visibility(_plan(), api=unusable)

    assert usable_report["sector_already_existed"] is True
    assert usable_report["sector_usable"] is True
    assert usable_report["visibility_success"] is True
    assert unusable_report["sector_already_existed"] is True
    assert unusable_report["sector_usable"] is False
    assert unusable_report["visibility_success"] is False


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
        def create_sector(self, block_code, block_name):
            return {"ErrorId": 0}

        def send_user_block(self, mystery):
            return None

        def send_message(self, message):
            return None

    with pytest.raises(TQVisibilityContractError, match="unsupported required"):
        publish_experience_plan_visibility(_plan(), api=_UnknownApi())


def test_opaque_positional_visibility_signature_is_not_called() -> None:
    class _OpaqueApi:
        def create_sector(self, block_code, block_name):
            return {"ErrorId": 0}

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

        def create_sector(self, block_code, block_name):
            return {"ErrorId": 0}

        def send_user_block(self, block_code, stocks, show):
            self.calls.append((block_code, stocks, show))
            return {"ErrorId": 0}

        def send_message(self, unsupported_required_parameter):
            return None

    api = _BlockOnlyApi()

    report = publish_experience_plan_visibility(_plan(), api=api)

    assert api.calls == [("QPTY", ["000002.SZ", "000001.SZ"], True)]
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
                "create_sector": {"available": True, "signature": "(block_code, block_name)"},
                "send_user_block": {"available": True, "signature": "(block_code, stocks, show)"},
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
    assert report["api_signatures"]["send_user_block"] == "(block_code, stocks, show)"
