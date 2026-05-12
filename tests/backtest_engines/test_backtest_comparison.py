from pathlib import Path

from quantpilot_core.backtest_engines.comparison import (
    load_prototype_comparison,
    summarize_prototype_comparison,
    validate_prototype_comparison,
)


ROOT = Path(__file__).resolve().parents[2]
COMPARISON_PATH = ROOT / "data" / "backtest_engine_candidates" / "prototype_comparison.json"


def test_prototype_comparison_loads_and_validates() -> None:
    records = load_prototype_comparison(COMPARISON_PATH)

    assert validate_prototype_comparison(records) == []


def test_required_engines_exist_and_names_are_unique() -> None:
    records = load_prototype_comparison(COMPARISON_PATH)
    names = [record["engine_name"] for record in records]

    assert len(names) == len(set(names))
    assert {"vectorbt", "Backtrader", "RQAlpha", "Qlib"}.issubset(set(names))


def test_no_engine_is_selected_ready_or_adapter_approved() -> None:
    records = load_prototype_comparison(COMPARISON_PATH)

    for record in records:
        values = {key.lower(): str(value).lower() for key, value in record.items()}
        assert values.get("final_selected") != "true"
        assert values.get("trading_ready") != "true"
        assert values.get("approved_for_adapter") != "true"
        assert "approved_for_adapter true" not in " ".join(values.values())
        assert "trading_ready true" not in " ".join(values.values())


def test_rqalpha_and_qlib_remain_conservative() -> None:
    records = {record["engine_name"]: record for record in load_prototype_comparison(COMPARISON_PATH)}

    assert records["RQAlpha"]["fake_fixture_consumed"] is False
    assert records["Qlib"]["prototype_status"] == "not_run"


def test_summary_reports_current_evidence_buckets() -> None:
    records = load_prototype_comparison(COMPARISON_PATH)
    summary = summarize_prototype_comparison(records)

    assert summary["engine_count"] >= 4
    assert set(summary["toy_success_engines"]) == {"vectorbt", "Backtrader"}
    assert summary["install_import_only_engines"] == ["RQAlpha"]
    assert summary["metadata_only_engines"] == ["Qlib"]
    assert summary["final_selection_made"] is False
    assert summary["adapter_approved"] is False
