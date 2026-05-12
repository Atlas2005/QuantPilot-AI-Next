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
    "import tradingagents",
    "from tradingagents",
    "import langgraph",
    "from langgraph",
    "import autogen",
    "from autogen",
    "import crewai",
    "from crewai",
    "submit_order(",
    "place_order(",
    "send_order(",
    "execute_order(",
    "enable_live_trading(",
    "connect_broker(",
]


def test_src_does_not_contain_forbidden_scope_patterns() -> None:
    violations: list[str] = []

    for path in SRC_ROOT.rglob("*.py"):
        text = path.read_text(encoding="utf-8").lower()
        for pattern in FORBIDDEN_PATTERNS:
            if pattern in text:
                violations.append(f"{path.relative_to(SRC_ROOT)}: {pattern}")

    assert violations == []

