from pathlib import Path


SRC_ROOT = Path(__file__).resolve().parents[2] / "src"

FORBIDDEN_PATTERNS = [
    "import akshare",
    "from akshare",
    "import baostock",
    "from baostock",
    "import tushare",
    "from tushare",
    "import qlib",
    "from qlib",
    "import vectorbt",
    "from vectorbt",
    "import backtrader",
    "from backtrader",
    "import rqalpha",
    "from rqalpha",
    "import lean",
    "from lean",
    "import openbb",
    "from openbb",
    "import pandera",
    "from pandera",
    "import great_expectations",
    "from great_expectations",
    "import polars",
    "from polars",
    "import duckdb",
    "from duckdb",
    "import pyarrow",
    "from pyarrow",
    "import tradingagents",
    "from tradingagents",
    "import langgraph",
    "from langgraph",
    "import autogen",
    "from autogen",
    "import crewai",
    "from crewai",
    "import openai",
    "from openai",
    "import scrapling",
    "from scrapling",
    "akshare.",
    "baostock.",
    "tushare.",
    "qlib.",
    "vectorbt.",
    "backtrader.",
    "rqalpha.",
    "openbb.",
    "pandera.",
    "great_expectations.",
    "polars.",
    "duckdb.",
    "pyarrow.",
    "langgraph.",
    "autogen.",
    "crewai.",
    "submit_order(",
    "place_order(",
    "send_order(",
    "execute_order(",
    "enable_live_trading(",
    "connect_broker(",
    "requests.",
    "urllib.request",
    "http.client",
    "api_key",
    "access_token",
]


def test_src_does_not_contain_forbidden_scope_patterns() -> None:
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        relative = path.relative_to(SRC_ROOT)
        text = path.read_text(encoding="utf-8").lower()
        for pattern in FORBIDDEN_PATTERNS:
            if relative.parts[:2] in {
                ("quantpilot_core", "vectorbt_replay_adapter"),
                ("quantpilot_core", "vectorbt_replay_comparison"),
                ("quantpilot_core", "vectorbt_old_chain_metrics_comparison"),
                ("quantpilot_core", "provider_vectorbt_replay"),
                ("quantpilot_core", "vectorbt_integration"),
            } and pattern in {
                "import vectorbt",
                "from vectorbt",
                "vectorbt.",
            }:
                continue
            if pattern in text:
                violations.append(f"{relative}: {pattern}")

    assert violations == []


def test_non_legacy_src_does_not_import_legacy_provider_replay_defaults() -> None:
    allowed_prefixes = {
        ("quantpilot_core", "real_provider_mixed_etf_paper_replay"),
        ("quantpilot_core", "vectorbt_old_chain_metrics_comparison"),
    }
    forbidden_fragments = (
        "build_provider_mixed_etf_replay_report",
        "replay_provider_mixed_etf_sample(",
        "replay_provider_mixed_etf_sample,",
    )
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        relative = path.relative_to(SRC_ROOT)
        if relative.parts[:2] in allowed_prefixes:
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{relative}: {fragment}")

    assert violations == []


def test_non_legacy_src_does_not_call_legacy_daily_replay_defaults() -> None:
    allowed_prefixes = {
        ("quantpilot_core", "daily_paper_trading_loop_tradability_metrics"),
        ("quantpilot_core", "mixed_stock_etf_daily_paper_evaluation"),
        ("quantpilot_core", "real_provider_mixed_etf_paper_replay"),
        ("quantpilot_core", "vectorbt_old_chain_metrics_comparison"),
    }
    forbidden_fragments = (
        "build_daily_paper_trading_loop_report",
        "build_mixed_stock_etf_comparison_report",
    )
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        relative = path.relative_to(SRC_ROOT)
        if relative.parts[:2] in allowed_prefixes:
            continue
        text = path.read_text(encoding="utf-8")
        for fragment in forbidden_fragments:
            if fragment in text:
                violations.append(f"{relative}: {fragment}")

    assert violations == []
