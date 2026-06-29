from quantpilot_core.market_reality import (
    MATURE_EXTERNAL_BOUNDARY_NAMES,
    AccountConstraint,
    CapitalConstraint,
    CostModel,
    DataLatencyAssumption,
    ExecutionConstraint,
    FillSimulation,
    InstrumentTradingProfile,
    OrderDraft,
    OrderSide,
    ProviderFailureAssumption,
    SandboxRejectionReason,
    SandboxResult,
    SandboxScenario,
    SlippageModel,
    TradingCalendarAssumption,
)


def test_contracts_can_be_constructed() -> None:
    scenario = valid_scenario()
    order = valid_order_draft()
    fill = FillSimulation(
        requested_quantity=100,
        filled_quantity=60,
        average_fill_price=10.0,
        partial_fill=True,
        rejected=False,
        rejection_reason=SandboxRejectionReason.NONE,
        notes="Sandbox partial fill assumption only.",
    )
    result = SandboxResult(
        scenario_id=scenario.scenario_id,
        order_draft=order,
        fill_simulation=fill,
        accepted_for_sandbox=True,
        rejection_reasons=(),
        live_execution_claim=False,
        broker_execution_reference=None,
        audit_timestamp="2026-06-29T10:00:00Z",
        external_adapter_boundary="Benchmark against RQAlpha or Backtrader adapters later.",
    )

    assert scenario.instrument.symbol == "600000.SH"
    assert order.side is OrderSide.BUY
    assert fill.partial_fill is True
    assert result.live_execution_claim is False


def test_external_adapter_boundary_candidates_are_named() -> None:
    assert "RQAlpha" in MATURE_EXTERNAL_BOUNDARY_NAMES
    assert "vectorbt" in MATURE_EXTERNAL_BOUNDARY_NAMES
    assert "Backtrader" in MATURE_EXTERNAL_BOUNDARY_NAMES
    assert "exchange_calendars" in MATURE_EXTERNAL_BOUNDARY_NAMES
    assert "empyrical" in MATURE_EXTERNAL_BOUNDARY_NAMES
    assert "quantstats" in MATURE_EXTERNAL_BOUNDARY_NAMES


def test_market_reality_contracts_do_not_reinvent_generic_engines() -> None:
    doc = (SandboxScenario.__doc__ or "") + " " + (
        ExecutionConstraint.__module__ or ""
    )
    contract_doc = __import__(
        "quantpilot_core.market_reality.contracts",
        fromlist=["__doc__"],
    ).__doc__

    combined = f"{doc} {contract_doc}".lower()
    assert "external engines remain adapter boundaries" in combined
    assert "does not implement a full simulator" in combined
    assert "backtest engine" in combined
    assert "risk engine" in combined
    assert "factor" in combined
    assert "market calendar" in combined


def valid_scenario(**overrides: object) -> SandboxScenario:
    values = {
        "scenario_id": "r2_valid_a_share_sandbox",
        "description": "Fixture-only A-share sandbox contract scenario.",
        "instrument": InstrumentTradingProfile(
            symbol="600000.SH",
            market="SSE",
            board="main",
            is_suspended=False,
            st_flag_explicit=True,
            is_st=False,
            delisting_risk_explicit=True,
            has_delisting_risk=False,
            price_limit_up=11.0,
            price_limit_down=9.0,
            t_zero_eligible=False,
            lot_size=100,
            external_adapter_boundary="Instrument metadata may later come from AkShare, Baostock, or RQAlpha adapters.",
        ),
        "execution_constraint": ExecutionConstraint(
            t_plus_one_required=True,
            t_zero_eligible=False,
            lot_size=100,
            lot_size_required=True,
            price_limit_up=11.0,
            price_limit_down=9.0,
            same_day_sell_forbidden=True,
            partial_fill_allowed=True,
            rejected_order_model_required=True,
        ),
        "calendar": TradingCalendarAssumption(
            calendar_name="a_share_fixture_calendar",
            trading_day="2026-06-29",
            is_trading_day=True,
            session_label="regular",
            source="fixture_only",
            external_adapter_boundary="Use exchange_calendars or RQAlpha calendar adapters after review.",
        ),
        "cost_model": CostModel(
            commission_rate=0.0003,
            stamp_duty_rate=0.0005,
            transfer_fee_rate=0.00001,
            minimum_commission=5.0,
            currency="CNY",
            external_adapter_boundary="Compare cost metrics with empyrical or quantstats reporting adapters later.",
        ),
        "slippage_model": SlippageModel(
            model_name="fixed_bps_fixture",
            slippage_bps=5.0,
            liquidity_participation_limit=0.1,
            external_adapter_boundary="Benchmark slippage assumptions against RQAlpha, vectorbt, or Backtrader adapters.",
        ),
        "account_constraint": AccountConstraint(
            account_id="sandbox_account",
            available_cash=100000.0,
            cash_constraint_explicit=True,
            allowed_markets=("SSE", "SZSE"),
            can_trade_a_shares=True,
            can_trade_t_zero_instruments=False,
            permission_notes="Sandbox permissions only.",
        ),
        "capital_constraint": CapitalConstraint(
            max_order_notional=20000.0,
            max_position_notional=50000.0,
            max_cash_usage_ratio=0.2,
            min_cash_reserve=10000.0,
            capital_mode="Capital-Aware Fast Compounding Mode",
        ),
        "data_latency": DataLatencyAssumption(
            provider_name="fixture_provider",
            max_latency_seconds=900,
            timestamp_source="fixture_timestamp",
            timestamp_audit_required=True,
            latency_policy="Reject stale fixture timestamps in later validation.",
        ),
        "provider_failure": ProviderFailureAssumption(
            provider_name="fixture_provider",
            failure_mode="missing_bar",
            fallback_policy="Reject candidate if provider failure cannot be audited.",
            failure_handling_required=True,
        ),
        "external_adapter_boundaries": (
            "RQAlpha adapter boundary",
            "vectorbt benchmark boundary",
            "Backtrader benchmark boundary",
            "exchange_calendars calendar boundary",
        ),
        "timestamp_audit_required": True,
        "no_live_execution": True,
    }
    values.update(overrides)
    return SandboxScenario(**values)


def valid_order_draft(**overrides: object) -> OrderDraft:
    values = {
        "draft_id": "draft_001",
        "symbol": "600000.SH",
        "side": OrderSide.BUY,
        "quantity": 100,
        "limit_price": 10.0,
        "trade_date": "2026-06-29",
        "created_at": "2026-06-29T10:00:00Z",
        "scenario_id": "r2_valid_a_share_sandbox",
        "is_live_order": False,
        "broker_instruction_id": None,
        "sandbox_instruction": "Sandbox feasibility draft for validation only.",
        "external_adapter_boundary": "May be benchmarked against RQAlpha or Backtrader later.",
    }
    values.update(overrides)
    return OrderDraft(**values)
