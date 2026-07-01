from __future__ import annotations

from pathlib import Path

from quantpilot_core.explicit_fill_simulation_boundary import (
    FillSimulationRequest,
    FillSimulationSide,
    FillSimulationStatus,
    build_fill_simulation_report,
    simulate_fill_boundary,
)


def request(**overrides: object) -> FillSimulationRequest:
    values = {
        "symbol": "600000",
        "side": FillSimulationSide.BUY,
        "requested_quantity": 1000,
        "executable_quantity": 1000,
        "reference_price": 10.0,
        "available_volume": 20_000,
        "max_participation_rate": 0.1,
        "commission_rate": 0.0003,
        "min_commission": 5.0,
        "stamp_duty_rate": 0.0005,
        "slippage_bps": 5.0,
        "asset_type": "stock",
        "evidence_refs": ("fixture:dry-run",),
        "dry_run_accepted": True,
        "source_instruction_id": "proposal-001",
    }
    values.update(overrides)
    return FillSimulationRequest(**values)


def issue_codes(result) -> tuple[str, ...]:
    return tuple(issue.code for issue in result.issues)


def warning_codes(result) -> tuple[str, ...]:
    return tuple(warning.code for warning in result.warnings)


def test_full_buy_fill_when_volume_cap_covers_executable_quantity() -> None:
    result = simulate_fill_boundary(request())

    assert result.accepted is True
    assert result.status == FillSimulationStatus.FULL.value
    assert result.simulated_filled_quantity == 1000
    assert result.unfilled_quantity == 0


def test_partial_buy_fill_when_volume_cap_below_executable_quantity() -> None:
    result = simulate_fill_boundary(request(available_volume=5000, max_participation_rate=0.1))

    assert result.accepted is True
    assert result.status == FillSimulationStatus.PARTIAL.value
    assert result.simulated_filled_quantity == 500
    assert result.unfilled_quantity == 500


def test_no_fill_when_volume_cap_is_zero() -> None:
    result = simulate_fill_boundary(request(available_volume=0))

    assert result.accepted is False
    assert result.status == FillSimulationStatus.NONE.value
    assert result.simulated_filled_quantity == 0


def test_rejected_when_dry_run_accepted_is_false() -> None:
    result = simulate_fill_boundary(request(dry_run_accepted=False))

    assert result.accepted is False
    assert result.status == FillSimulationStatus.REJECTED.value
    assert "dry_run_not_accepted" in issue_codes(result)


def test_rejected_when_executable_quantity_is_zero() -> None:
    result = simulate_fill_boundary(request(executable_quantity=0))

    assert result.accepted is False
    assert result.status == FillSimulationStatus.REJECTED.value
    assert "executable_quantity_missing" in issue_codes(result)


def test_rejected_when_evidence_refs_empty() -> None:
    result = simulate_fill_boundary(request(evidence_refs=()))

    assert result.accepted is False
    assert result.status == FillSimulationStatus.REJECTED.value
    assert "evidence_refs_missing" in issue_codes(result)


def test_rejected_when_reference_price_invalid() -> None:
    result = simulate_fill_boundary(request(reference_price=0.0))

    assert result.accepted is False
    assert result.status == FillSimulationStatus.REJECTED.value
    assert "invalid_reference_price" in issue_codes(result)


def test_missing_available_volume_warns_but_allows_full_fill() -> None:
    result = simulate_fill_boundary(request(available_volume=None))

    assert result.accepted is True
    assert result.status == FillSimulationStatus.FULL.value
    assert result.simulated_filled_quantity == 1000
    assert "available_volume_missing" in warning_codes(result)


def test_buy_slippage_increases_fill_price() -> None:
    result = simulate_fill_boundary(request(side=FillSimulationSide.BUY, slippage_bps=10.0))

    assert result.simulated_fill_price == 10.01


def test_sell_slippage_decreases_fill_price() -> None:
    result = simulate_fill_boundary(request(side=FillSimulationSide.SELL, slippage_bps=10.0))

    assert result.simulated_fill_price == 9.99


def test_stock_sell_includes_stamp_duty() -> None:
    result = simulate_fill_boundary(
        request(side=FillSimulationSide.SELL, asset_type="stock", stamp_duty_rate=0.001, slippage_bps=0.0)
    )

    assert result.cost_breakdown.stamp_duty == 10.0


def test_etf_sell_has_zero_stamp_duty() -> None:
    result = simulate_fill_boundary(
        request(side=FillSimulationSide.SELL, asset_type="etf", stamp_duty_rate=0.001)
    )

    assert result.cost_breakdown.stamp_duty == 0.0


def test_net_cash_impact_is_negative_for_buy_and_positive_for_sell() -> None:
    buy = simulate_fill_boundary(request(side=FillSimulationSide.BUY))
    sell = simulate_fill_boundary(request(side=FillSimulationSide.SELL))

    assert buy.net_cash_impact < 0
    assert sell.net_cash_impact > 0


def test_result_has_no_live_execution_claim() -> None:
    result = build_fill_simulation_report(request())

    assert result.live_execution_claim is False


def test_result_has_no_broker_execution_reference() -> None:
    result = build_fill_simulation_report(request())

    assert result.broker_execution_reference is None


def test_result_has_no_profitability_claim() -> None:
    result = build_fill_simulation_report(request())

    assert result.profitability_claim is False


def test_module_does_not_import_broker_provider_or_network_packages() -> None:
    package_root = Path("src/quantpilot_core/explicit_fill_simulation_boundary")
    source_text = "\n".join(path.read_text() for path in sorted(package_root.glob("*.py"))).lower()

    forbidden_fragments = (
        "import akshare",
        "from akshare",
        "import baostock",
        "from baostock",
        "import tushare",
        "from tushare",
        "import qmt",
        "from qmt",
        "import xtquant",
        "from xtquant",
        "import easytrader",
        "from easytrader",
        "connect_broker(",
        "place_order(",
        "send_order(",
        "submit_order(",
        "execute_order(",
        "requests.",
        "websocket",
        "urllib.request",
    )
    assert not any(fragment in source_text for fragment in forbidden_fragments)
