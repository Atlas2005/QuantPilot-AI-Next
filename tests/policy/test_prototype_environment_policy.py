from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[2]


def test_prototype_environment_policy_exists() -> None:
    assert (ROOT / "docs" / "PROTOTYPE_ENVIRONMENT_ISOLATION_POLICY.md").exists()


def test_gitignore_includes_prototype_and_artifact_paths() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")

    assert ".venv-prototypes/" in gitignore
    assert "local_artifacts/" in gitignore


def test_pyproject_does_not_include_prototype_frameworks_as_required_dependencies() -> None:
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8").lower()
    forbidden = [
        "backtrader",
        "rqalpha",
        "qlib",
        "lean",
        "vn.py",
        "veighna",
        "nautilustrader",
        "zipline",
        "backtesting.py",
        "\"bt\"",
        "'bt'",
    ]

    for name in forbidden:
        assert name not in pyproject


def test_vectorbt_is_optional_replay_dependency_only() -> None:
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

    assert pyproject["project"]["dependencies"] == []
    replay = pyproject["project"]["optional-dependencies"]["replay"]
    assert any(item.startswith("vectorbt") for item in replay)


def test_helper_scripts_exist() -> None:
    assert (ROOT / "tools" / "prototype_envs" / "create_prototype_env.ps1").exists()
    assert (ROOT / "tools" / "prototype_envs" / "create_prototype_env.sh").exists()


def test_helper_scripts_do_not_install_or_run_prototypes() -> None:
    scripts = [
        ROOT / "tools" / "prototype_envs" / "create_prototype_env.ps1",
        ROOT / "tools" / "prototype_envs" / "create_prototype_env.sh",
    ]
    forbidden_terms = [
        "pip install",
        "conda install",
        "akshare",
        "baostock",
        "tushare",
        "openbb",
        "query_history",
        "stock_zh_a",
        "from_signals",
        "run_backtest",
        "submit_order",
        "live_trading",
    ]

    for script in scripts:
        content = script.read_text(encoding="utf-8").lower()
        for term in forbidden_terms:
            assert term not in content
