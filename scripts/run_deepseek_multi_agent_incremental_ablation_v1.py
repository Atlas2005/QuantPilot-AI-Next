#!/usr/bin/env python
"""Manual, offline-by-default PR122 multi-agent incremental ablation."""
from __future__ import annotations
import argparse, json, subprocess
from pathlib import Path
from quantpilot_core.evaluation.deepseek_multi_agent_incremental_ablation import IncrementalAblationConfig, LIVE_REQUEST_HARD_LIMIT, build_live_evidence, run_deepseek_multi_agent_incremental_ablation_v1
from quantpilot_core.quant_firm.deepseek_advisory import create_live_structured_evidence_client

def _parser():
    p=argparse.ArgumentParser(); p.add_argument("--pr121-artifact",required=True); p.add_argument("--advisory-cache-dir",default=".cache/quantpilot_deepseek_multi_agent_incremental"); p.add_argument("--artifact-path",default="artifacts/deepseek_multi_agent_incremental_ablation/latest_report.json"); p.add_argument("--report-path",default=".cache/quantpilot_deepseek_multi_agent_incremental/latest_report.json"); p.add_argument("--single-agent-role",default="investment_committee"); p.add_argument("--multi-agent-roles",default="research_desk,information_desk,backtest_desk,portfolio_desk,execution_simulation_desk"); p.add_argument("--max-live-requests",type=int,default=0); p.add_argument("--live",action="store_true"); p.add_argument("--pricing-metadata-path"); return p
def _ignored(path): return subprocess.run(["git","check-ignore","-q",str(path)],capture_output=True).returncode==0
def main(argv=None, *, client=None):
    a=_parser().parse_args(argv); cache=Path(a.advisory_cache_dir); pricing=json.loads(Path(a.pricing_metadata_path).read_text()) if a.pricing_metadata_path else None
    config=IncrementalAblationConfig(pr121_artifact=a.pr121_artifact,advisory_evidence=cache/"advisory_outputs.json",single_agent_role=a.single_agent_role,multi_agent_roles=tuple(x for x in a.multi_agent_roles.split(",") if x),pricing_metadata=pricing,artifact_path=a.artifact_path)
    mode="offline_replay"
    if a.live:
        if not 1<=a.max_live_requests<=LIVE_REQUEST_HARD_LIMIT: raise SystemExit(f"--live --max-live-requests must be 1..{LIVE_REQUEST_HARD_LIMIT}")
        if not all(_ignored(x) for x in (cache,a.artifact_path,a.report_path)): raise SystemExit("--live refuses non-gitignored cache/output paths")
        evidence=build_live_evidence(config,client or create_live_structured_evidence_client(),cache,a.max_live_requests); cache.mkdir(parents=True,exist_ok=True); (cache/"advisory_outputs.json").write_text(json.dumps(evidence,sort_keys=True)); mode="live_evidence_then_replay"
    report=run_deepseek_multi_agent_incremental_ablation_v1(config,mode=mode)
    summary={"mode":report.mode,"common_fold_count":len(report.common_folds),"usage":report.usage,"recommendation":report.recommendation,"artifact_path":report.artifact_path}; Path(a.report_path).parent.mkdir(parents=True,exist_ok=True);Path(a.report_path).write_text(json.dumps(summary,sort_keys=True,indent=2)+"\n");print(json.dumps(summary,sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
