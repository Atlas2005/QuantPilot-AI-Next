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
        text = path.read_text(encoding="utf-8").lower()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"{path.relative_to(SRC_ROOT)}: {pattern}")

    assert violations == []
