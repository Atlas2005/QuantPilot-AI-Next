from __future__ import annotations

from quantpilot_core.cost_after_fill_profitability import (
    AShareCostModel,
    CostAfterFillRequest,
    CostAfterFillSide,
    CostAfterFillStatus,
    build_cost_after_fill_report,
    evaluate_cost_after_fill,
)


def request(**overrides: object) -> CostAfterFillRequest:
    values = {
        "source_order_id": "fill-001",
        "symbol": "600000",
        "side": CostAfterFillSide.BUY,
        "requested_quantity": 1000,
        "filled_quantity": 1000,
        "reference_price": 10.0,
        "fill_price": 10.0,
        "entry_price": 10.0,
        "exit_price": 10.5,
        "cost_model": AShareCostModel(
            broker_commission_rate=0.0003,
            minimum_commission=None,
            stamp_duty_sell_rate=0.0005,
            exchange_handling_fee_rate=0.0000341,
            securities_management_fee_rate=0.00002,
            transfer_fee_rate=0.0,
            regulatory_fee_rate=0.0,
        ),
        "evidence_refs": ("fixture:fill",),
    }
    values.update(overrides)
    return CostAfterFillRequest(**values)


def issue_codes(result) -> tuple[str, ...]:
    return tuple(issue.code for issue in result.issues)


def warning_codes(result) -> tuple[str, ...]:
    return tuple(warning.code for warning in result.warnings)


def test_buy_only_fill_cost_calculation() -> None:
    result = evaluate_cost_after_fill(request(entry_price=None, exit_price=None))

    assert result.status == CostAfterFillStatus.EVALUATED.value
    assert result.gross_notional == 10_000.0
    assert result.cost_breakdown.broker_commission == 3.0
    assert result.cost_breakdown.exchange_handling_fee == 0.341
    assert result.cost_breakdown.securities_management_fee == 0.2
    assert result.cost_breakdown.stamp_duty == 0.0
    assert result.cost_breakdown.total_cost == 3.541
    assert result.net_pnl_after_cost is None


def test_sell_side_stamp_duty() -> None:
    result = evaluate_cost_after_fill(request(side=CostAfterFillSide.SELL))

    assert result.cost_breakdown.stamp_duty == 5.0
    assert result.cost_breakdown.total_cost == 8.541


def test_commission_minimum() -> None:
    result = evaluate_cost_after_fill(
        request(
            filled_quantity=100,
            requested_quantity=100,
            cost_model=AShareCostModel(
                broker_commission_rate=0.0003,
                minimum_commission=5.0,
                stamp_duty_sell_rate=0.0005,
                exchange_handling_fee_rate=0.0000341,
                securities_management_fee_rate=0.00002,
                transfer_fee_rate=0.0,
                regulatory_fee_rate=0.0,
            ),
        )
    )

    assert result.gross_notional == 1000.0
    assert result.cost_breakdown.broker_commission == 5.0


def test_partial_fill_unfilled_quantity_and_notional() -> None:
    result = evaluate_cost_after_fill(request(requested_quantity=1000, filled_quantity=600))

    assert result.gross_notional == 6000.0
    assert result.unfilled_quantity == 400
    assert result.unfilled_notional == 4000.0


def test_slippage_cost_from_simulated_fill_vs_reference_price() -> None:
    buy = evaluate_cost_after_fill(request(fill_price=10.02))
    sell = evaluate_cost_after_fill(request(side=CostAfterFillSide.SELL, fill_price=9.98))

    assert buy.cost_breakdown.slippage_cost == 20.0
    assert sell.cost_breakdown.slippage_cost == 20.0


def test_net_pnl_after_fill() -> None:
    result = evaluate_cost_after_fill(request())

    assert result.gross_pnl == 500.0
    assert result.net_pnl_after_cost == 496.459
    assert result.net_return_after_fill == 0.0496459
    assert result.cost_drag == 3.541
    assert result.cost_drag_rate == 0.0003541


def test_missing_price_inputs_are_advisory_not_global_blockers() -> None:
    result = evaluate_cost_after_fill(request(entry_price=None, exit_price=None))
    report = build_cost_after_fill_report((request(entry_price=None, exit_price=None),))

    assert result.status == CostAfterFillStatus.EVALUATED.value
    assert result.missing_pnl_inputs is True
    assert "missing_pnl_inputs" in warning_codes(result)
    assert result.issues == ()
    assert report.evaluated_count == 1
    assert report.rejected_count == 0
    assert report.summary["cost_after_fill"]["profitability_gate"] is False
    assert report.summary["cost_after_fill"]["net_pnl_after_cost_total"] is None


def test_malformed_negative_price_or_quantity_is_rejected_locally() -> None:
    negative_price = evaluate_cost_after_fill(request(fill_price=-1.0))
    negative_quantity = evaluate_cost_after_fill(request(filled_quantity=-100))
    report = build_cost_after_fill_report((request(), request(fill_price=-1.0)))

    assert negative_price.status == CostAfterFillStatus.REJECTED.value
    assert "invalid_fill_price" in issue_codes(negative_price)
    assert negative_quantity.status == CostAfterFillStatus.REJECTED.value
    assert "negative_filled_quantity" in issue_codes(negative_quantity)
    assert report.evaluated_count == 1
    assert report.rejected_count == 1
