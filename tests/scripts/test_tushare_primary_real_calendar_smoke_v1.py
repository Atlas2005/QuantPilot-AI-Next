from datetime import date, timedelta
import json
from types import SimpleNamespace

import pytest

from scripts.run_tushare_primary_real_calendar_smoke_v1 import _validate_limits, main
from quantpilot_core.real_data_provider import ProviderName


def test_offline_default_makes_no_provider_calls(tmp_path, monkeypatch, capsys):
    output = tmp_path / "report.json"
    monkeypatch.setattr(
        "sys.argv",
        ["run_tushare_primary_real_calendar_smoke_v1.py", "--output", str(output)],
    )
    monkeypatch.setattr(
        "scripts.run_tushare_primary_real_calendar_smoke_v1.TusharePrimaryBaoStockFallbackProvider",
        lambda: (_ for _ in ()).throw(AssertionError("daily provider must not be constructed")),
    )
    monkeypatch.setattr(
        "scripts.run_tushare_primary_real_calendar_smoke_v1.TusharePrimaryBaoStockCalendarProvider",
        lambda: (_ for _ in ()).throw(AssertionError("calendar provider must not be constructed")),
    )

    assert main() == 0

    assert output.exists()
    assert "provider_calls" in output.read_text(encoding="utf-8")
    assert str(output) in capsys.readouterr().out


def test_live_limits_are_enforced():
    start_date = date(2026, 1, 1)
    _validate_limits(("000001.SZ",), start_date, start_date + timedelta(days=44))
    with pytest.raises(SystemExit, match="at most 2 symbols"):
        _validate_limits(("000001.SZ", "000002.SZ", "600000.SH"), date(2026, 1, 1), date(2026, 1, 2))
    with pytest.raises(SystemExit, match="45 calendar days"):
        _validate_limits(("000001.SZ",), start_date, start_date + timedelta(days=45))
    with pytest.raises(SystemExit, match="start-date"):
        _validate_limits(("000001.SZ",), date(2026, 1, 2), date(2026, 1, 1))


def test_live_runner_output_uses_sanitized_attempt_reasons(tmp_path, monkeypatch):
    output = tmp_path / "report.json"
    secret = "secret-token-value"

    class FakeDailyChain:
        def fetch_daily_bars_with_provenance(self, request):
            return SimpleNamespace(
                selected_provider=ProviderName.BAOSTOCK,
                fallback_used=True,
                bars=(),
                attempts=(
                    SimpleNamespace(provider=ProviderName.TUSHARE, status="failed", reason="Tushare daily bar request failed"),
                    SimpleNamespace(provider=ProviderName.BAOSTOCK, status="success", reason="bars:0"),
                ),
            )

    class FakeCalendarChain:
        def fetch_calendar_with_provenance(self, start_date, end_date):
            return SimpleNamespace(
                selected_provider=ProviderName.TUSHARE,
                session_count=0,
                attempts=(SimpleNamespace(provider=ProviderName.TUSHARE, status="success", reason="sessions:0"),),
            )

    monkeypatch.setattr(
        "sys.argv",
        [
            "run_tushare_primary_real_calendar_smoke_v1.py",
            "--live",
            "--output",
            str(output),
        ],
    )
    monkeypatch.setattr(
        "scripts.run_tushare_primary_real_calendar_smoke_v1.TusharePrimaryBaoStockFallbackProvider",
        FakeDailyChain,
    )
    monkeypatch.setattr(
        "scripts.run_tushare_primary_real_calendar_smoke_v1.TusharePrimaryBaoStockCalendarProvider",
        FakeCalendarChain,
    )

    assert main() == 0

    payload = output.read_text(encoding="utf-8")
    assert secret not in payload
    assert json.loads(payload)["symbols"][0]["attempts"][0]["reason"] == "Tushare daily bar request failed"
