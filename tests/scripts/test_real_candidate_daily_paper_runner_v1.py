from __future__ import annotations

import json
from pathlib import Path

from scripts.run_real_candidate_daily_paper_v1 import main
import pytest


def test_real_candidate_runner_default_offline_has_no_live_calls(tmp_path: Path, capsys) -> None:
    state = tmp_path / "state.json"
    report = tmp_path / "report.json"

    assert main(["--state-path", str(state), "--report-path", str(report), "--decision-session", "2026-04-03"]) == 0

    stdout = json.loads(capsys.readouterr().out)
    payload = json.loads(report.read_text(encoding="utf-8"))
    assert stdout["status"] == "completed"
    assert payload["candidate_pipeline"]["provenance"]["market"]["network_calls"] == 0
    assert payload["daily_paper_loop"]["advisory_provenance"]["deepseek_live_call"] is False
    assert payload["candidate_pipeline"]["factor_window"]["d_plus_1_excluded_from_factor_calculation"] is True
    assert state.exists()


def test_real_candidate_runner_live_requires_explicit_decision_session(tmp_path: Path) -> None:
    input_path = tmp_path / "input.json"
    input_path.write_text(json.dumps({"symbols": ["600000.SH"]}), encoding="utf-8")

    with pytest.raises(SystemExit):
        main([
            "--live-market-data",
            "--input-json",
            str(input_path),
            "--state-path",
            str(tmp_path / "state.json"),
            "--report-path",
            str(tmp_path / "report.json"),
        ])
