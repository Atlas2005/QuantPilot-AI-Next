from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT_PATH = ROOT / ".venv-prototypes" / "rqalpha"
EXPECTED_PYTHON = ENVIRONMENT_PATH / "bin" / "python"
ARTIFACT_DIR = ROOT / "local_artifacts" / "backtest_prototypes" / "rqalpha"
RESULT_PATH = ARTIFACT_DIR / "rqalpha_local_run_result.json"
DEFAULT_BUNDLE_PATH = Path.home() / ".rqalpha" / "bundle"
BUNDLE_PATH_ENV_VAR = "RQALPHA_BUNDLE_PATH"
REQUIRED_BUNDLE_FILES = (
    "future_info.json",
    "instruments.pk",
    "trading_dates.npy",
)
PROVIDER = "rqalpha"
SYMBOL = "000001.XSHE"
START_DATE = "2026-01-02"
END_DATE = "2026-01-06"
ACCOUNT_TYPE = "stock"
INITIAL_CASH = 100_000.0
FREQUENCY = "1d"
RUN_TYPE = "b"
ALLOWED_METRIC_KEYS = (
    "total_return",
    "annualized_return",
    "max_drawdown",
    "sharpe",
    "trade_count",
    "turnover",
)


def _base_result() -> dict[str, Any]:
    return {
        "provider": PROVIDER,
        "environment_path": str(ENVIRONMENT_PATH),
        "python_executable": sys.executable,
        "rqalpha_importable": False,
        "rqalpha_version": None,
        "minimal_local_run_attempted": False,
        "minimal_local_run_succeeded": False,
        "output_metrics_available": False,
        "run_api_attempted": None,
        "symbol": SYMBOL,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "account_type": ACCOUNT_TYPE,
        "initial_cash": INITIAL_CASH,
        "frequency": FREQUENCY,
        "run_type": RUN_TYPE,
        "bundle_path": str(DEFAULT_BUNDLE_PATH),
        "configured_bundle_path": str(DEFAULT_BUNDLE_PATH),
        "resolved_bundle_path": None,
        "bundle_path_source": "default_home",
        "bundle_exists": False,
        "download_required": False,
        "status": "not_started",
        "failure_stage": None,
        "error_type": None,
        "error_message": None,
        "traceback_tail": [],
        "report_keys": [],
        "result_keys": [],
        "explicit_metrics": {},
        "observed_trade_rows": None,
        "warnings": [
            "Manual prototype only. Run with .venv-prototypes/rqalpha/bin/python from the repository root.",
            "Metrics must not be invented; explicit_metrics only copies explicit allowed metric keys from RQAlpha output mappings.",
            "observed_trade_rows is evidence metadata, not a performance metric.",
            "Bundle data must be authorized local data and must not be committed.",
        ],
        "conclusion": "Not run yet.",
    }


def _write_result(result: dict[str, Any]) -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")


def _running_in_expected_environment() -> bool:
    executable = Path(sys.executable)
    try:
        return executable.resolve() == EXPECTED_PYTHON.resolve()
    except OSError:
        return executable == EXPECTED_PYTHON


def _resolve_bundle_path() -> tuple[Path, str, str | None]:
    explicit_path = os.environ.get(BUNDLE_PATH_ENV_VAR)
    if explicit_path:
        path = Path(explicit_path).expanduser()
        if _is_tracked_workspace_path(path):
            return path, "explicit_env", "explicit bundle path must stay outside tracked source"
        return path, "explicit_env", None
    return DEFAULT_BUNDLE_PATH, "default_home", None


def _has_expected_bundle_files(path: Path) -> bool:
    return path.is_dir() and all(
        (path / filename).is_file() for filename in REQUIRED_BUNDLE_FILES
    )


def _resolve_bundle_content_path(configured_path: Path) -> Path | None:
    if _has_expected_bundle_files(configured_path):
        return configured_path

    nested_bundle_path = configured_path / "bundle"
    if _has_expected_bundle_files(nested_bundle_path):
        return nested_bundle_path

    return None


def _is_tracked_workspace_path(path: Path) -> bool:
    try:
        resolved_path = path.resolve()
        resolved_root = ROOT.resolve()
        resolved_external = (ROOT / ".external").resolve()
    except OSError:
        return True
    if resolved_path == resolved_external or resolved_external in resolved_path.parents:
        return False
    return resolved_path == resolved_root or resolved_root in resolved_path.parents


def _record_bundle_status(result: dict[str, Any]) -> bool:
    configured_bundle_path, source, path_error = _resolve_bundle_path()
    result["bundle_path"] = str(configured_bundle_path)
    result["configured_bundle_path"] = str(configured_bundle_path)
    result["bundle_path_source"] = source
    result["bundle_exists"] = False
    if path_error is not None:
        result["status"] = "bundle_authorization_required"
        result["failure_stage"] = "bundle_policy_check"
        result["error_message"] = path_error
        result["conclusion"] = (
            "Refused to use an explicit bundle path inside tracked source. "
            "Use ~/.rqalpha/bundle or an authorized ignored local path."
        )
        return False

    resolved_bundle_path = _resolve_bundle_content_path(configured_bundle_path)
    if resolved_bundle_path is not None:
        result["bundle_path"] = str(resolved_bundle_path)
        result["resolved_bundle_path"] = str(resolved_bundle_path)
        result["bundle_exists"] = True
        return True

    if not configured_bundle_path.exists():
        result["status"] = "data_bundle_required_or_missing"
        result["failure_stage"] = "bundle_check"
        result["download_required"] = True
        result["error_message"] = (
            f"No authorized local RQAlpha bundle found at {configured_bundle_path}."
        )
        result["conclusion"] = (
            "RQAlpha is importable in the isolated environment, but an authorized "
            "local data bundle is required before a real local run can be attempted."
        )
        return False

    result["status"] = "data_bundle_required_or_missing"
    result["failure_stage"] = "bundle_content_check"
    result["error_message"] = (
        f"No valid RQAlpha bundle content directory found at {configured_bundle_path} "
        f"or {configured_bundle_path / 'bundle'}."
    )
    result["conclusion"] = (
        "RQAlpha is importable in the isolated environment, but the configured "
        "bundle path does not contain the expected local bundle files."
    )
    return False


def _tiny_config(bundle_path: Path) -> dict[str, Any]:
    return {
        "base": {
            "start_date": START_DATE,
            "end_date": END_DATE,
            "frequency": FREQUENCY,
            "accounts": {ACCOUNT_TYPE: INITIAL_CASH},
            "run_type": RUN_TYPE,
            "data_bundle_path": str(bundle_path),
        },
        "extra": {
            "context_vars": {
                "target_symbol": SYMBOL,
            },
            "log_level": "error",
        },
        "mod": {
            "sys_analyser": {
                "enabled": True,
                "output_file": str(RESULT_PATH.with_name("rqalpha_raw_report.pkl")),
            },
        },
    }


def _init_strategy(context: Any) -> None:
    context.target_symbol = SYMBOL


def _handle_bar_strategy(context: Any, bar_dict: Any) -> None:
    _ = context
    _ = bar_dict


def _safe_keys(value: Any) -> list[str]:
    if isinstance(value, dict):
        return sorted(str(key) for key in value.keys())
    if hasattr(value, "keys"):
        try:
            return sorted(str(key) for key in value.keys())
        except Exception:
            return []
    return []


def _as_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        converted = value.to_dict()
        if isinstance(converted, dict):
            return converted
    return {}


def _collect_metric_candidates(
    run_output: Any,
) -> tuple[dict[str, Any], int | None, list[str], list[str]]:
    result_mapping = _as_mapping(run_output)
    report = result_mapping.get("report")
    report_mapping = _as_mapping(report)
    candidates: list[dict[str, Any]] = [result_mapping, report_mapping]
    for key in ("summary", "metrics", "portfolio"):
        nested = result_mapping.get(key)
        nested_mapping = _as_mapping(nested)
        if nested_mapping:
            candidates.append(nested_mapping)
    for key in ("summary", "metrics", "portfolio"):
        nested = report_mapping.get(key)
        nested_mapping = _as_mapping(nested)
        if nested_mapping:
            candidates.append(nested_mapping)

    explicit_metrics: dict[str, Any] = {}
    for key in ALLOWED_METRIC_KEYS:
        for candidate in candidates:
            if key in candidate:
                value = candidate[key]
                if isinstance(value, (int, float, str, bool)) or value is None:
                    explicit_metrics[key] = value
                    break

    trades = result_mapping.get("trades") or report_mapping.get("trades")
    observed_trade_rows = len(trades) if isinstance(trades, (list, tuple)) else None

    return (
        explicit_metrics,
        observed_trade_rows,
        _safe_keys(report_mapping),
        _safe_keys(result_mapping),
    )


def _classify_failure(exc: Exception) -> str:
    text = f"{type(exc).__name__}: {exc}".lower()
    if "bundle" in text or "data" in text:
        return "data_bundle_required_or_missing"
    if "config" in text:
        return "config_required_or_invalid"
    return "rqalpha_run_failed"


def _record_exception(result: dict[str, Any], stage: str, exc: Exception) -> None:
    result["status"] = _classify_failure(exc)
    result["failure_stage"] = stage
    result["error_type"] = type(exc).__name__
    result["error_message"] = str(exc)
    result["traceback_tail"] = traceback.format_exc().splitlines()[-8:]
    result["minimal_local_run_succeeded"] = False
    result["output_metrics_available"] = False
    if result["status"] == "data_bundle_required_or_missing":
        result["conclusion"] = (
            "RQAlpha was importable in the isolated environment, but the local run "
            "requires a data bundle or compatible data configuration."
        )
    else:
        result["conclusion"] = "RQAlpha isolated local run attempt failed cleanly."


def main() -> int:
    result = _base_result()

    if not _running_in_expected_environment():
        result["status"] = "wrong_python_environment"
        result["failure_stage"] = "environment_check"
        result["error_message"] = (
            f"Expected {EXPECTED_PYTHON}, got {sys.executable}. "
            "Run this tool only with the isolated prototype interpreter."
        )
        result["conclusion"] = "Refused to run outside the isolated RQAlpha prototype environment."
        _write_result(result)
        return 3

    try:
        import rqalpha  # type: ignore[import-not-found]
    except Exception as exc:
        _record_exception(result, "import", exc)
        result["rqalpha_importable"] = False
        _write_result(result)
        return 2

    result["rqalpha_importable"] = True
    result["rqalpha_version"] = getattr(rqalpha, "__version__", None) or getattr(
        rqalpha, "version", None
    )

    if not _record_bundle_status(result):
        _write_result(result)
        return 0

    run_func = getattr(rqalpha, "run_func", None)
    if run_func is None:
        result["status"] = "run_api_missing"
        result["failure_stage"] = "api_detection"
        result["error_message"] = "RQAlpha run_func entry point was not available."
        result["conclusion"] = "RQAlpha import succeeded, but the expected run API was missing."
        _write_result(result)
        return 1

    result["minimal_local_run_attempted"] = True
    result["run_api_attempted"] = "run_func"

    try:
        run_output = run_func(
            init=_init_strategy,
            handle_bar=_handle_bar_strategy,
            config=_tiny_config(Path(str(result["resolved_bundle_path"]))),
        )
        explicit_metrics, observed_trade_rows, report_keys, result_keys = (
            _collect_metric_candidates(run_output)
        )
        result["minimal_local_run_succeeded"] = True
        result["status"] = "local_run_succeeded"
        result["report_keys"] = report_keys
        result["result_keys"] = result_keys
        result["explicit_metrics"] = explicit_metrics
        result["observed_trade_rows"] = observed_trade_rows
        result["output_metrics_available"] = bool(explicit_metrics)
        if explicit_metrics:
            result["conclusion"] = (
                "RQAlpha isolated local run succeeded and explicit output metrics were captured."
            )
        else:
            result["status"] = "output_metrics_missing"
            result["conclusion"] = (
                "RQAlpha isolated local run returned without explicit allowed metrics."
            )
        _write_result(result)
        return 0
    except Exception as exc:
        _record_exception(result, "run_func", exc)
        _write_result(result)
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
