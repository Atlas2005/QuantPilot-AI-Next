"""PIT-safe offline/live DeepSeek multi-agent incremental-value replay."""
from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Mapping, Protocol

from quantpilot_core.deepseek_multi_agent.runtime_contracts import TokenEstimate
from quantpilot_core.deepseek_multi_agent.runtime_router import DEFAULT_MODEL_PRICES, estimate_model_call_cost_usd
from quantpilot_core.information_agents.contracts import InformationAgentRole, InformationAgentSignal, InformationDirection, InformationHorizon
from quantpilot_core.research_committee import build_research_committee_report

DEFAULT_MULTI_AGENT_ROLES = ("research_desk", "information_desk", "backtest_desk", "portfolio_desk", "execution_simulation_desk")
DEFAULT_DEEPSEEK_MULTI_AGENT_INCREMENTAL_ABLATION_ARTIFACT_PATH = Path("artifacts/deepseek_multi_agent_incremental_ablation/latest_report.json")
SCHEMA_VERSION = "deepseek_multi_agent_incremental_v2"
LIVE_REQUEST_HARD_LIMIT = 50


class StructuredEvidenceClient(Protocol):
    def __call__(self, request: Mapping[str, Any]) -> Mapping[str, Any]: ...


@dataclass(frozen=True)
class AdvisoryResult:
    """Public structured-result shape retained for callers constructing fixtures."""
    role: str
    candidate_scores: Mapping[str, float]
    preferred_candidate: str | None = None
    confidence: float = 0.0
    abstain: bool = False


@dataclass(frozen=True)
class RecommendationThresholds:
    minimum_completed_folds: int = 3
    minimum_positive_excess_fold_ratio: float = .5
    minimum_compounded_net_excess: float = 0.0
    maximum_drawdown: float = -.30
    maximum_fallback_ratio: float = 0.0
    maximum_invalid_output_ratio: float = 0.0


@dataclass(frozen=True)
class IncrementalAblationConfig:
    pr121_artifact: str | Path | Mapping[str, Any]
    advisory_evidence: str | Path | Mapping[str, Any] | None = None
    baseline_candidate_id: str = "dynamic_selector"
    single_agent_role: str = "investment_committee"
    multi_agent_roles: tuple[str, ...] = DEFAULT_MULTI_AGENT_ROLES
    initial_cash: float = 1_000_000.0
    allowed_adjustment_ranges: Mapping[str, tuple[float, float]] = field(default_factory=lambda: {"target_position_count": (1, 50), "reserve_cash_weight": (0., .5), "max_position_weight": (.01, 1.), "turnover_penalty": (0., 10.)})
    pricing_metadata: Mapping[str, Any] | None = None
    recommendation_thresholds: RecommendationThresholds = field(default_factory=RecommendationThresholds)
    artifact_path: str | Path | None = None


@dataclass(frozen=True)
class IncrementalAblationReport:
    mode: str; pr121_artifact_digest: str; common_folds: tuple[Mapping[str, Any], ...]
    decision_packets: tuple[Mapping[str, Any], ...]; role_outputs: Mapping[str, Mapping[str, Mapping[str, Any]]]
    decisions: Mapping[str, tuple[Mapping[str, Any], ...]]; arm_metrics: Mapping[str, Mapping[str, Any]]
    pairwise_deltas: Mapping[str, Mapping[str, Mapping[str, Any]]]; usage: Mapping[str, Any]
    recommendation: str; recommendation_reason: str; committee_provenance: str
    artifact_path: str | None = None


class LiveStructuredEvidenceProducer:
    """Bounded fold/role producer.  The injected client is the only I/O boundary."""
    def __init__(self, client: StructuredEvidenceClient, cache_dir: str | Path, max_live_requests: int, config: IncrementalAblationConfig) -> None:
        if not 1 <= max_live_requests <= LIVE_REQUEST_HARD_LIMIT: raise ValueError(f"max_live_requests must be 1..{LIVE_REQUEST_HARD_LIMIT}")
        self.client, self.cache_dir, self.limit, self.config = client, Path(cache_dir), max_live_requests, config
        self.calls = 0

    def generate(self, packets: tuple[Mapping[str, Any], ...], roles: tuple[str, ...]) -> Mapping[str, Mapping[str, Mapping[str, Any]]]:
        tasks = [(packet, role) for packet in packets for role in roles]
        uncached = [(packet, role) for packet, role in tasks if not self._cache_path(packet, role).exists()]
        if len(uncached) > self.limit: raise ValueError(f"live request plan exceeds cap before call 1: required={len(uncached)} allowed={self.limit}")
        output: dict[str, dict[str, Mapping[str, Any]]] = {}
        for packet, role in tasks:
            cached = self._read(packet, role)
            if cached is not None:
                output.setdefault(packet["fold_id"], {})[role] = {**cached, "cache_status": "project_cache_hit", "live_call_attempted": False}; continue
            self.calls += 1
            started = time.monotonic(); response: Mapping[str, Any] | None = None
            try: response = self.client(self._request(packet, role))
            except Exception as exc: raw = {"unavailable_reason": f"client_error:{type(exc).__name__}"}
            else: raw = self._parse_response(response)
            raw.update(self._metadata(packet, role, response, time.monotonic() - started))
            self._atomic_write(packet, role, raw)
            output.setdefault(packet["fold_id"], {})[role] = raw
        return output

    def _request(self, packet, role):
        model = "deepseek-v4-pro" if role in {"investment_committee", "research_desk", "portfolio_desk"} else "deepseek-v4-flash"
        prompt = json.dumps({"packet": packet, "role": role, "contract": {"candidate_scores": "object candidate->finite number", "preferred_candidate": "eligible candidate or null", "confidence": "0..1", "rationale_codes": "array[str]", "parameter_adjustments": "object", "abstain": "bool"}}, sort_keys=True)
        return {"model": model, "reasoning_mode": "medium", "messages": [{"role": "system", "content": "Return only a JSON object. Rank only supplied candidates. Do not execute trades."}, {"role": "user", "content": prompt}]}
    def _parse_response(self, response):
        content = response.get("content") if isinstance(response, Mapping) else None
        if response.get("finish_reason") in {"length", "content_filter"}: return {"unavailable_reason": "truncated_or_filtered_response"}
        if not isinstance(content, str) or not content.strip(): return {"unavailable_reason": "missing_content"}
        try: value = json.loads(content)
        except json.JSONDecodeError: return {"unavailable_reason": "malformed_json"}
        return value if isinstance(value, Mapping) else {"unavailable_reason": "json_not_object"}
    def _metadata(self, packet, role, response, latency):
        usage = (response or {}).get("usage") or {}; hit = int(usage.get("prompt_cache_hit_tokens") or 0); inp = int(usage.get("prompt_tokens") or 0)
        return {"role": role, "packet_digest": packet["packet_digest"], "model": (response or {}).get("model") or self._request(packet, role)["model"], "reasoning_mode": "medium", "prompt_schema_version": SCHEMA_VERSION, "cache_status": "live", "input_tokens": inp, "cache_hit_input_tokens": hit, "input_cache_miss_tokens": int(usage.get("prompt_cache_miss_tokens") or max(0, inp-hit)), "output_tokens": int(usage.get("completion_tokens") or 0), "latency_seconds": round(latency, 6), "live_call_attempted": True, "live_call_succeeded": response is not None, "finish_reason": (response or {}).get("finish_reason"), "physical_request_ordinal": self.calls, "response_digest": _digest((response or {}).get("content"))}
    def _cache_path(self, packet, role): return self.cache_dir / f"{packet['packet_digest']}-{role}-{SCHEMA_VERSION}.json"
    def _read(self, packet, role):
        path = self._cache_path(packet, role)
        try: return json.loads(path.read_text())
        except FileNotFoundError: return None
    def _atomic_write(self, packet, role, value):
        path = self._cache_path(packet, role); path.parent.mkdir(parents=True, exist_ok=True); temp = path.with_suffix(".tmp"); temp.write_text(json.dumps(value, sort_keys=True)); temp.replace(path)


def build_live_evidence(config: IncrementalAblationConfig, client: StructuredEvidenceClient, cache_dir: str | Path, max_live_requests: int) -> Mapping[str, Mapping[str, Mapping[str, Any]]]:
    artifact = _load(config.pr121_artifact); packets = _packets(tuple(artifact.get("common_folds") or ()), artifact.get("per_candidate_fold_metrics") or {})
    roles = tuple(dict.fromkeys((config.single_agent_role, *config.multi_agent_roles)))
    return LiveStructuredEvidenceProducer(client, cache_dir, max_live_requests, config).generate(packets, roles)


def run_deepseek_multi_agent_incremental_ablation_v1(config: IncrementalAblationConfig, *, mode: str = "offline_replay") -> IncrementalAblationReport:
    artifact = _load(config.pr121_artifact); folds = tuple(artifact.get("common_folds") or ()); candidates = artifact.get("per_candidate_fold_metrics") or {}
    packets = _packets(folds, candidates); evidence = _normalise(_load(config.advisory_evidence) if config.advisory_evidence else {})
    outputs = {p["fold_id"]: {r: _validate_output(r, raw, p["candidate_ids"], config, p["packet_digest"]) for r, raw in evidence.get(p["fold_id"], {}).items()} for p in packets}
    baseline = tuple(_decision(str(f["fold_id"]), (next((x.get("selected_candidate") for x in artifact.get("selection_history", ()) if str(x.get("fold_id")) == str(f["fold_id"])), None) or config.baseline_candidate_id), candidates, "non_llm_baseline", "pr121_validation_only_selector") for f in folds)
    decisions = {"non_llm_baseline": baseline, "single_agent": _ai("single_agent", folds, candidates, outputs, (config.single_agent_role,)), "multi_agent_independent": _ai("multi_agent_independent", folds, candidates, outputs, config.multi_agent_roles), "multi_agent_committee": _ai("multi_agent_committee", folds, candidates, outputs, config.multi_agent_roles, True)}
    usage = _usage(outputs, config.pricing_metadata); metrics = {name: _metrics(rows, baseline, config.initial_cash) for name, rows in decisions.items()}
    recommendation, reason = _recommend(metrics, config.recommendation_thresholds)
    report = IncrementalAblationReport(mode, _digest(artifact), folds, packets, outputs, decisions, metrics, {name: {"non_llm_baseline": _delta(metric, metrics["non_llm_baseline"])} for name, metric in metrics.items()}, usage, recommendation, reason, "quantpilot_core.research_committee.build_research_committee_report")
    return _write(report, config.artifact_path)


def _packets(folds, candidates):
    packets=[]
    for fold in folds:
        p={"fold_id":str(fold["fold_id"]), "evidence_timestamp":str(fold.get("validation_end") or fold.get("decision_timestamp")), "test_start":str(fold["test_start"]), "candidate_ids":tuple(sorted(candidates)), "validation_metrics":_validation(candidates, str(fold["fold_id"])), "uses_test_outcomes":False, "supplied_fields":("PR121 validation evidence",), "provenance":"PR121 artifact"}
        p["evidence_before_test"] = p["evidence_timestamp"] < p["test_start"]; p["packet_digest"]=_digest(p); packets.append(p)
    return tuple(packets)
def _validation(candidates, fid): return {name:{k:row.get(k) for k in ("total_return","strategy_excess_return","max_drawdown","turnover","cost_total","rejected_trade_ratio")} for name,rows in candidates.items() for row in rows if str(row.get("fold_id"))==fid and row.get("validation_range")}


def _validate_output(role, raw, eligible, config, digest):
    raw=dict(raw); invalid=raw.get("unavailable_reason"); abstain=raw.get("abstain")
    if not isinstance(abstain, bool): invalid=invalid or "malformed_abstention"
    scores=raw.get("candidate_scores", {}); confidence=raw.get("confidence", 0.0); preferred=raw.get("preferred_candidate")
    if not abstain and not invalid:
        if not isinstance(scores, Mapping) or not scores: invalid="empty_or_malformed_scores"
        elif set(scores)-set(eligible): invalid="candidate_outside_eligible_set"
        elif any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in scores.values()): invalid="nonfinite_or_boolean_score"
        elif len(set(scores.values())) != len(scores): invalid="tied_scores_no_lexical_fallback"
        elif preferred not in eligible: invalid="preferred_candidate_outside_eligible_set"
        elif preferred != max(scores, key=scores.get): invalid="preferred_candidate_inconsistent_with_winner"
    if not isinstance(confidence,(int,float)) or isinstance(confidence,bool) or not 0<=confidence<=1: invalid=invalid or "confidence_out_of_range"
    adjustments, rejected={},{}
    if not isinstance(raw.get("parameter_adjustments",{}), Mapping): invalid=invalid or "malformed_parameter_adjustments"
    else:
        for name,value in raw.get("parameter_adjustments",{}).items():
            bounds=config.allowed_adjustment_ranges.get(name)
            if bounds is None: rejected[name]="unknown_adjustment"; invalid=invalid or "unknown_adjustment"
            elif isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value): rejected[name]="malformed_adjustment"; invalid=invalid or "malformed_adjustment"
            elif not bounds[0] <= value <= bounds[1]: rejected[name]="outside_allowed_range"; invalid=invalid or "outside_allowed_range"
            else: adjustments[name]=float(value)
    if raw.get("live_call_succeeded") and not raw.get("response_digest"): invalid=invalid or "successful_live_without_response_evidence"
    result={**raw,"role":role,"candidate_scores":dict(scores) if isinstance(scores,Mapping) else {},"confidence":float(confidence) if isinstance(confidence,(int,float)) else 0.,"parameter_adjustments":adjustments,"unavailable_reason":str(invalid) if invalid else None,"packet_digest":digest,"adjustment_audit":{"accepted":adjustments,"rejected":rejected},"input_cache_miss_tokens":int(raw.get("input_cache_miss_tokens") or max(0,int(raw.get("input_tokens") or 0)-int(raw.get("cache_hit_input_tokens") or 0)))}
    return result

def _ai(arm, folds, candidates, outputs, roles, committee=False):
    rows=[]
    for fold in folds:
        fid=str(fold["fold_id"]); selected={role:outputs.get(fid,{}).get(role) for role in roles}; missing=[r for r,v in selected.items() if not v or v.get("unavailable_reason")]
        if missing: rows.append(_decision(fid,None,candidates,arm,"unavailable_roles:"+','.join(missing))); continue
        scores={c:sum(v["candidate_scores"][c] for v in selected.values())/len(selected) for c in candidates}
        if committee: scores=_committee(scores)
        rows.append(_decision(fid,max(scores,key=scores.get),candidates,arm,"research_committee_adapter" if committee else "deterministic_distinct_role_mean",scores,selected))
    return tuple(rows)
def _committee(scores):
    outcome={}
    for candidate,score in scores.items():
        signal=InformationAgentSignal(InformationAgentRole.NEWS_IMPACT,candidate,InformationDirection.POSITIVE if score>=0 else InformationDirection.NEGATIVE,max(-1,min(1,score)),min(1,abs(score)),InformationHorizon.SHORT_TERM,"offline",("role_scores",),("advisory_only",))
        report=build_research_committee_report((signal,),{"target":candidate,"total_return":score,"max_drawdown":0,"win_rate":.5,"turnover":0,"trades":1},target=candidate); outcome[candidate]=score+report.composite_score*.001
    return outcome
def _decision(fid,candidate,candidates,arm,reason,scores=None,outputs=None):
    source=next((dict(r) for r in candidates.get(candidate,()) if str(r.get("fold_id"))==fid),None) if candidate else None
    return {**(source or {"fold_id":fid,"status":"unavailable"}),"selected_candidate":candidate,"arm":arm,"selection_reason":reason,"candidate_scores":scores or {},"role_outputs":outputs or {},"uses_test_outcomes":False}
def _metrics(rows,baseline,cash):
    complete=[r for r in rows if r.get("status")=="completed"]; values=lambda k:[float(r[k]) for r in complete if r.get(k)is not None]
    def comp(k):
        result=1.
        for x in values(k): result*=1+x
        return round(result-1,6) if values(k) else None
    api=sum(float(x.get("estimated_api_cost") or 0) for r in rows for x in r.get("role_outputs",{}).values()); base={r["fold_id"]:r.get("selected_candidate") for r in baseline}
    return {"available":bool(complete),"completed_folds":len(complete),"successful_fold_ratio":round(len(complete)/len(rows),6) if rows else 0,"compounded_fold_return":comp("total_return"),"compounded_benchmark_return":comp("benchmark_total_return"),"compounded_excess_return":comp("strategy_excess_return"),"positive_excess_fold_ratio":_ratio(values("strategy_excess_return"),lambda x:x>0),"maximum_drawdown":min(values("max_drawdown"),default=None),"turnover":round(sum(values("turnover")),6),"transaction_cost_total":round(sum(values("cost_total")),6),"estimated_api_cost":round(api,8),"net_return_after_api_cost":None if comp("total_return") is None else round(comp("total_return")-api/cash,8),"net_excess_after_api_cost":None if comp("strategy_excess_return") is None else round(comp("strategy_excess_return")-api/cash,8),"fallback_count":0,"fallback_ratio":0.,"invalid_output_count":sum("invalid" in str(r.get("selection_reason")) for r in rows),"invalid_output_ratio":round(sum("invalid" in str(r.get("selection_reason")) for r in rows)/len(rows),6) if rows else 0.,"decision_change_count_vs_non_llm":sum(r.get("selected_candidate")!=base.get(r["fold_id"]) for r in rows)}
def _usage(outputs,pricing):
    items=[x for roles in outputs.values() for x in roles.values()]
    for x in items:
        source="unavailable"; metadata=pricing or x.get("pricing_metadata")
        if metadata: x["estimated_api_cost"]=float(metadata.get("estimated_api_cost",x.get("estimated_api_cost") or 0)); source="explicit_run_metadata" if pricing else "cached_response_metadata"
        elif x.get("model") in DEFAULT_MODEL_PRICES: x["estimated_api_cost"]=estimate_model_call_cost_usd(x["model"],TokenEstimate(int(x.get("input_tokens")or 0),int(x.get("output_tokens")or 0),int(x.get("cache_hit_input_tokens")or 0)),False); source="runtime_router_estimate"
        x["pricing_source"]=source
    return {"logical_role_evaluations":len(items),"physical_model_calls":sum(bool(x.get("live_call_attempted")) for x in items),"project_cache_hits":sum(x.get("cache_status")=="project_cache_hit" for x in items),"provider_cache_hit_input_tokens":sum(int(x.get("cache_hit_input_tokens")or 0) for x in items),"input_cache_miss_tokens":sum(int(x.get("input_cache_miss_tokens")or 0) for x in items),"output_tokens":sum(int(x.get("output_tokens")or 0) for x in items),"estimated_total_api_cost":round(sum(float(x.get("estimated_api_cost")or 0) for x in items),8)}
def _recommend(metrics,t):
    names=[]
    for name,row in metrics.items():
        if name=="non_llm_baseline":continue
        ok=row["completed_folds"]>=t.minimum_completed_folds and (row["positive_excess_fold_ratio"]or 0)>=t.minimum_positive_excess_fold_ratio and (row["net_excess_after_api_cost"]or -1)<999 and (row["net_excess_after_api_cost"]or -1)>=t.minimum_compounded_net_excess and (row["maximum_drawdown"] is not None and row["maximum_drawdown"]>=t.maximum_drawdown) and row["fallback_ratio"]<=t.maximum_fallback_ratio and row["invalid_output_ratio"]<=t.maximum_invalid_output_ratio
        if ok:names.append(name)
    return (max(names,key=lambda n:metrics[n]["net_excess_after_api_cost"]),"all_evaluation_only_thresholds_met") if names else ("no_ai_arm","evaluation_only_thresholds_not_met")
def _ratio(xs,p):return round(sum(p(x) for x in xs)/len(xs),6) if xs else None
def _delta(a,b):return {k+"_delta":round(a[k]-b[k],8) if a.get(k)is not None and b.get(k)is not None else None for k in ("compounded_fold_return","compounded_excess_return","maximum_drawdown","turnover","transaction_cost_total","net_excess_after_api_cost")}
def _digest(v):return hashlib.sha256(json.dumps(v,default=str,sort_keys=True,separators=(",",":" )).encode()).hexdigest()
def _load(v):return dict(v) if isinstance(v,Mapping) else json.loads(Path(v).read_text())
def _normalise(v):return v.get("folds",v) if isinstance(v,Mapping) else {str(x["fold_id"]):{str(x["role"]):x for x in v}}
def _write(report,path):
    if path is None:return report
    target=Path(path);target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(asdict(report),default=str,sort_keys=True,indent=2)+"\n");return replace(report,artifact_path=str(target))
