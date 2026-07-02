from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_PATH = ROOT / "docs" / "R4E_ISOLATED_RQALPHA_DATA_BUNDLE_POLICY_REVIEW.md"
GITIGNORE_PATH = ROOT / ".gitignore"
PYPROJECT_PATH = ROOT / "pyproject.toml"
R4D_SCRIPT_PATH = (
    ROOT / "tools" / "manual_backtest_prototypes" / "rqalpha_local_run_attempt.py"
)


def _doc_text() -> str:
    return DOC_PATH.read_text(encoding="utf-8")


def test_r4e_policy_doc_exists_and_is_review_only() -> None:
    text = _doc_text()

    assert DOC_PATH.exists()
    assert "R4E is a policy and review step" in text
    assert "does not download data" in text
    assert "does not run RQAlpha" in text
    assert "does not add RQAlpha to the main project dependencies" in text


def test_r4e_policy_defines_allowed_bundle_locations() -> None:
    text = _doc_text()

    assert "~/.rqalpha/bundle" in text
    assert "explicit local bundle path" in text
    assert ".external/" in text
    assert "outside tracked source" in text


def test_r4e_policy_requires_ignore_and_no_data_committed_boundary() -> None:
    text = _doc_text()
    gitignore = GITIGNORE_PATH.read_text(encoding="utf-8")

    assert "No bundle" in text
    assert "large data file may be committed" in text
    assert "local_artifacts/" in gitignore
    assert ".external/" in gitignore
    assert ".venv-prototypes/" in gitignore


def test_r4e_policy_warns_about_license_authorization_and_noncommercial_use() -> None:
    text = _doc_text()

    assert "license" in text.lower()
    assert "non-commercial" in text.lower()
    assert "authorization" in text.lower()
    assert "does not approve commercial use" in text


def test_r4e_policy_requires_isolated_env_and_structured_missing_bundle_status() -> None:
    text = _doc_text()

    assert ".venv-prototypes/rqalpha/bin/python" in text
    assert "data_bundle_required_or_missing" in text
    assert "download_required" in text
    assert "bundle_authorization_required" in text
    assert "must not block vectorbt, Qlib, or DeepSeek" in text


def test_r4e_policy_keeps_broker_live_modules_out_of_scope() -> None:
    text = _doc_text().lower()

    for fragment in (
        "broker",
        "live trading",
        "real order execution",
        "mod-ctp",
        "mod-vnpy",
    ):
        assert fragment in text


def test_r4e_handoff_requirements_for_r4f_are_documented() -> None:
    text = _doc_text()

    assert "R4F Handoff Requirements" in text
    assert "documented bundle source and authorization basis" in text
    assert "confirmed default bundle availability" in text
    assert "documented explicit local bundle path" in text
    assert "explicit metrics may only be copied" in text


def test_rqalpha_is_not_added_to_main_required_dependencies() -> None:
    text = PYPROJECT_PATH.read_text(encoding="utf-8").lower()

    assert "rqalpha" not in text


def test_r4d_script_records_missing_bundle_without_download_logic() -> None:
    text = R4D_SCRIPT_PATH.read_text(encoding="utf-8").lower()

    assert "data_bundle_required_or_missing" in text
    assert "download_required" in text
    assert "download_bundle" not in text
    assert "download-bundle" not in text
    assert "requests" not in text
    assert "urllib" not in text
    assert "httpx" not in text
