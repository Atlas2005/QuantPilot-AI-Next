"""Technical evaluation helpers for DeepSeek announcement assessment reliability."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from quantpilot_core.announcement_intelligence.contracts import AnnouncementImpactAssessment
from quantpilot_core.announcement_intelligence.research_committee_integration import (
    ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION,
    ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION,
    assess_announcement_event_with_deepseek,
    build_announcement_advisory_payload,
)
from quantpilot_core.quant_firm import DeepSeekAdvisoryAgent, DeepSeekAdvisoryOutput, DeepSeekAdvisoryRole


EVALUATION_ADAPTER_VERSION = "announcement_deepseek_evaluation_adapter_v3"
EVALUATION_CACHE_SCHEMA_VERSION = "announcement_deepseek_evaluation_cache_v3"
DEFAULT_EVALUATION_CACHE_DIR = Path(".cache/quantpilot_announcement_deepseek_evaluation")


@dataclass(frozen=True)
class AnnouncementDeepSeekEvaluationResult:
    """Assessments plus technical reliability/cache counters."""

    assessments: tuple[AnnouncementImpactAssessment, ...]
    report: Mapping[str, Any]


@dataclass(frozen=True)
class _CachedAssessment:
    assessment: AnnouncementImpactAssessment
    used_model: str | None


class _RecordingAdvisoryAgent:
    def __init__(self, agent: Any) -> None:
        self.agent = agent
        self.outputs: list[DeepSeekAdvisoryOutput] = []
        self.failures: list[str] = []

    def advise(self, advisory_input: Any) -> DeepSeekAdvisoryOutput:
        try:
            output = self.agent.advise(advisory_input)
        except Exception as exc:
            self.failures.append(type(exc).__name__)
            raise
        if isinstance(output, DeepSeekAdvisoryOutput):
            self.outputs.append(output)
        return output


def evaluate_announcement_events_with_deepseek(
    events: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | pd.DataFrame,
    *,
    advisory_agent: Any | None = None,
    cache_dir: str | Path = DEFAULT_EVALUATION_CACHE_DIR,
    use_project_cache: bool = True,
) -> AnnouncementDeepSeekEvaluationResult:
    """Run a technical reliability evaluation without calculating future returns."""

    rows = _event_rows(events)
    cache_path = Path(cache_dir)
    assessments: list[AnnouncementImpactAssessment] = []
    selected_models: dict[str, int] = {}
    project_cache_hits = 0
    logical_live_attempts = 0
    live_response_successes = 0
    live_attempt_failures = 0
    schema_valid_live_responses = 0
    schema_invalid_live_responses = 0
    platform_cache_available_responses = 0
    platform_cache_missing_responses = 0
    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0
    cached_input_tokens = 0
    uncached_input_tokens = 0

    base_agent = advisory_agent or DeepSeekAdvisoryAgent()
    recorder = _RecordingAdvisoryAgent(base_agent)
    model_selection_for_cache = _model_selection_for_cache(base_agent)
    live_enabled = _live_enabled(base_agent)
    for row in rows:
        key = _evaluation_cache_key(row, model_selection=model_selection_for_cache)
        cached = _read_cached_assessment(cache_path, key) if use_project_cache else None
        if cached is not None:
            assessments.append(cached.assessment)
            project_cache_hits += 1
            cached_model = cached.used_model or "cached_model_unknown"
            selected_models[cached_model] = selected_models.get(cached_model, 0) + 1
            continue

        delegated_live_attempt = live_enabled and _event_has_available_content(row)
        if delegated_live_attempt:
            logical_live_attempts += 1
        before_outputs = len(recorder.outputs)
        assessment = assess_announcement_event_with_deepseek(row, advisory_agent=recorder)
        assessments.append(assessment)
        new_outputs = recorder.outputs[before_outputs:]
        output = new_outputs[-1] if new_outputs else None
        if output is not None:
            selected_models[output.used_model] = selected_models.get(output.used_model, 0) + 1
        if delegated_live_attempt:
            if output is not None and not output.is_fallback:
                live_response_successes += 1
                if assessment.schema_validation_status == "passed":
                    schema_valid_live_responses += 1
                elif assessment.schema_validation_status == "failed":
                    schema_invalid_live_responses += 1
                usage = _usage_metrics(output.raw_response_usage)
                prompt_tokens += usage["prompt_tokens"]
                completion_tokens += usage["completion_tokens"]
                total_tokens += usage["total_tokens"]
                if usage["platform_cache_metrics_available"]:
                    platform_cache_available_responses += 1
                    cached_input_tokens += usage["cached_input_tokens"]
                    uncached_input_tokens += usage["uncached_input_tokens"]
                else:
                    platform_cache_missing_responses += 1
            else:
                live_attempt_failures += 1

        if use_project_cache and assessment.impact_assessment_source == "model_structured_output":
            used_model = output.used_model if output is not None else str(model_selection_for_cache["model"])
            _write_cached_assessment(cache_path, key, assessment, used_model=used_model)

    report = _build_report(
        assessments,
        event_count=len(rows),
        logical_live_attempt_count=logical_live_attempts,
        live_response_success_count=live_response_successes,
        live_attempt_failure_count=live_attempt_failures,
        schema_valid_live_response_count=schema_valid_live_responses,
        schema_invalid_live_response_count=schema_invalid_live_responses,
        project_event_cache_hit_count=project_cache_hits,
        selected_model_distribution=selected_models,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens if platform_cache_available_responses else None,
        uncached_input_tokens=uncached_input_tokens if platform_cache_available_responses else None,
        platform_cache_available_response_count=platform_cache_available_responses,
        platform_cache_missing_response_count=platform_cache_missing_responses,
    )
    return AnnouncementDeepSeekEvaluationResult(assessments=tuple(assessments), report=report)


def _build_report(
    assessments: list[AnnouncementImpactAssessment],
    *,
    event_count: int,
    logical_live_attempt_count: int,
    live_response_success_count: int,
    live_attempt_failure_count: int,
    schema_valid_live_response_count: int,
    schema_invalid_live_response_count: int,
    project_event_cache_hit_count: int,
    selected_model_distribution: Mapping[str, int],
    prompt_tokens: int,
    completion_tokens: int,
    total_tokens: int,
    cached_input_tokens: int | None,
    uncached_input_tokens: int | None,
    platform_cache_available_response_count: int,
    platform_cache_missing_response_count: int,
) -> Mapping[str, Any]:
    schema_valid = sum(1 for item in assessments if item.schema_validation_status == "passed")
    schema_invalid = sum(1 for item in assessments if item.schema_validation_status == "failed")
    model_derived = sum(1 for item in assessments if item.impact_assessment_source == "model_structured_output")
    keyword_fallback = sum(1 for item in assessments if item.impact_assessment_source == "keyword_fallback")
    unavailable = sum(1 for item in assessments if item.impact_assessment_source == "honest_unavailable_fallback")
    platform_hit_ratio = None
    if cached_input_tokens is not None and uncached_input_tokens is not None:
        denominator = cached_input_tokens + uncached_input_tokens
        platform_hit_ratio = round(cached_input_tokens / denominator, 6) if denominator else None
    platform_response_count = platform_cache_available_response_count + platform_cache_missing_response_count
    return {
        "label": "DeepSeek announcement technical evaluation; not prediction accuracy",
        "metric_descriptions": {
            "logical_live_attempt_count": "Uncached available events delegated to a live-enabled existing DeepSeekAdvisoryAgent; not HTTP retries.",
            "logical_outbound_attempt_count": "One logical advisory delegation for a live-enabled uncached available event; exact SDK HTTP request/retry count is not observed.",
            "observed_http_request_count": "Unavailable because SDK HTTP requests and retries are not instrumented here.",
            "project_event_cache_hit_count": "QuantPilot event-level assessment cache hits before advisory delegation.",
            "platform_input_cache_hit_ratio": "Provider/platform input-token cache ratio from responses that expose cache-token fields.",
        },
        "event_count": event_count,
        "logical_live_attempt_count": logical_live_attempt_count,
        "logical_outbound_attempt_count": logical_live_attempt_count,
        "observed_http_request_count": None,
        "outbound_request_count": None,
        "live_response_success_count": live_response_success_count,
        "api_success_count": live_response_success_count,
        "live_attempt_failure_count": live_attempt_failure_count,
        "api_failure_count": live_attempt_failure_count,
        "live_attempt_accounting_invariant_passed": (
            logical_live_attempt_count == live_response_success_count + live_attempt_failure_count
        ),
        "schema_valid_live_response_count": schema_valid_live_response_count,
        "schema_invalid_live_response_count": schema_invalid_live_response_count,
        "project_event_cache_hit_count": project_event_cache_hit_count,
        "project_cache_hit_count": project_event_cache_hit_count,
        "schema_valid_count": schema_valid,
        "schema_invalid_count": schema_invalid,
        "model_derived_count": model_derived,
        "keyword_fallback_count": keyword_fallback,
        "unavailable_count": unavailable,
        "selected_model_distribution": dict(sorted(selected_model_distribution.items())),
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "cached_input_tokens": cached_input_tokens,
        "uncached_input_tokens": uncached_input_tokens,
        "platform_cached_input_tokens": cached_input_tokens,
        "platform_uncached_input_tokens": uncached_input_tokens,
        "platform_input_cache_hit_ratio": platform_hit_ratio,
        "platform_cache_metrics_available_response_count": platform_cache_available_response_count,
        "platform_cache_metrics_missing_response_count": platform_cache_missing_response_count,
        "platform_cache_metrics_coverage_rate": (
            round(platform_cache_available_response_count / platform_response_count, 6)
            if platform_response_count
            else None
        ),
        "project_event_cache_hit_ratio": round(project_event_cache_hit_count / event_count, 6) if event_count else 0.0,
        "api_success_rate": (
            round(live_response_success_count / logical_live_attempt_count, 6)
            if logical_live_attempt_count
            else None
        ),
        "schema_valid_rate": round(schema_valid / event_count, 6) if event_count else 0.0,
        "schema_valid_live_response_rate": (
            round(schema_valid_live_response_count / live_response_success_count, 6)
            if live_response_success_count
            else None
        ),
        "model_derived_rate": round(model_derived / event_count, 6) if event_count else 0.0,
        "event_level_model_derived_rate": round(model_derived / event_count, 6) if event_count else 0.0,
        "fallback_rate": round((keyword_fallback + unavailable) / event_count, 6) if event_count else 0.0,
        "average_total_tokens_per_successful_live_response": (
            round(total_tokens / live_response_success_count, 6) if live_response_success_count else None
        ),
    }


def _usage_metrics(usage: Mapping[str, Any] | None) -> Mapping[str, int | None]:
    data = dict(usage or {})
    prompt = _int_or_zero(data.get("prompt_tokens") or data.get("input_tokens"))
    completion = _int_or_zero(data.get("completion_tokens") or data.get("output_tokens"))
    total = _int_or_zero(data.get("total_tokens")) or prompt + completion
    cached = _extract_first_int(
        data,
        (
            ("cached_input_tokens",),
            ("cache_hit_input_tokens",),
            ("prompt_cache_hit_tokens",),
            ("input_token_details", "cache_read"),
            ("prompt_tokens_details", "cached_tokens"),
            ("prompt_tokens_details", "cache_hit_tokens"),
        ),
    )
    uncached = _extract_first_int(
        data,
        (
            ("uncached_input_tokens",),
            ("cache_miss_input_tokens",),
            ("prompt_cache_miss_tokens",),
            ("input_token_details", "cache_creation"),
            ("prompt_tokens_details", "uncached_tokens"),
            ("prompt_tokens_details", "cache_miss_tokens"),
        ),
    )
    if uncached is None and cached is not None and prompt >= cached:
        uncached = prompt - cached
    platform_cache_metrics_available = cached is not None and uncached is not None
    return {
        "prompt_tokens": prompt,
        "completion_tokens": completion,
        "total_tokens": total,
        "cached_input_tokens": cached if platform_cache_metrics_available else None,
        "uncached_input_tokens": uncached if platform_cache_metrics_available else None,
        "platform_cache_metrics_available": platform_cache_metrics_available,
    }


def _extract_first_int(data: Mapping[str, Any], paths: tuple[tuple[str, ...], ...]) -> int | None:
    for path in paths:
        current: Any = data
        for key in path:
            if isinstance(current, Mapping):
                current = current.get(key)
            else:
                current = getattr(current, key, None)
        value = _int_or_none(current)
        if value is not None:
            return value
    return None


def _int_or_zero(value: Any) -> int:
    return _int_or_none(value) or 0


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _event_rows(events: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] | pd.DataFrame) -> tuple[Mapping[str, Any], ...]:
    if isinstance(events, pd.DataFrame):
        return tuple(events.to_dict("records"))
    return tuple(dict(item) for item in events)


def _read_cached_assessment(cache_dir: Path, key: str) -> _CachedAssessment | None:
    path = cache_dir / f"{key}.json"
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("cache_schema_version") != EVALUATION_CACHE_SCHEMA_VERSION:
        return None
    return _CachedAssessment(
        assessment=_assessment_from_payload(payload["assessment"]),
        used_model=str(payload.get("used_model") or "") or None,
    )


def _write_cached_assessment(
    cache_dir: Path,
    key: str,
    assessment: AnnouncementImpactAssessment,
    *,
    used_model: str,
) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "cache_schema_version": EVALUATION_CACHE_SCHEMA_VERSION,
        "evaluation_adapter_version": EVALUATION_ADAPTER_VERSION,
        "structured_output_schema_version": ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION,
        "content_quality_policy_version": ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION,
        "used_model": used_model,
        "assessment": asdict(assessment),
    }
    (cache_dir / f"{key}.json").write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _assessment_from_payload(payload: Mapping[str, Any]) -> AnnouncementImpactAssessment:
    data = dict(payload)
    for key in ("concise_evidence", "advisory_evidence_used", "advisory_tool_notes"):
        data[key] = tuple(data.get(key) or ())
    return AnnouncementImpactAssessment(**data)


def _evaluation_cache_key(event: Mapping[str, Any], *, model_selection: Mapping[str, Any] | str) -> str:
    selection = (
        {"model": str(model_selection)}
        if isinstance(model_selection, str)
        else dict(model_selection)
    )
    payload = {
        "cache_schema_version": EVALUATION_CACHE_SCHEMA_VERSION,
        "evaluation_adapter_version": EVALUATION_ADAPTER_VERSION,
        "structured_output_schema_version": ANNOUNCEMENT_STRUCTURED_OUTPUT_SCHEMA_VERSION,
        "content_quality_policy_version": ANNOUNCEMENT_CONTENT_QUALITY_POLICY_VERSION,
        "model_selection": selection,
        "announcement_advisory_payload": build_announcement_advisory_payload(event),
        "content_classifier_version": event.get("content_classifier_version"),
        "content_quality_evidence": event.get("content_quality_evidence"),
        "content_hash": event.get("content_hash"),
        "content_cache_key": event.get("content_cache_key"),
        "content_cache_schema_version": event.get("content_cache_schema_version"),
        "content_truncated": event.get("content_truncated"),
        "max_input_chars": event.get("max_input_chars"),
    }
    encoded = json.dumps(_json_safe(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _model_selection_for_cache(agent: Any) -> Mapping[str, Any]:
    explicit = getattr(agent, "selected_model", None)
    if explicit:
        return {"model": str(explicit), "source": "agent_selected_model"}
    config = getattr(agent, "config", None)
    model_policy = getattr(agent, "model_policy", None)
    selection_for = getattr(model_policy, "selection_for", None)
    if callable(selection_for):
        try:
            selection = selection_for(DeepSeekAdvisoryRole.INFORMATION_DESK, config)
            return {
                "model": str(selection.model),
                "enable_thinking": bool(selection.enable_thinking),
                "reasoning_effort": str(selection.reasoning_effort),
                "warnings": tuple(str(item) for item in selection.warnings),
                "source": "model_policy",
            }
        except Exception:
            pass
    model = getattr(config, "model", None)
    if model:
        return {"model": str(model), "source": "config_model"}
    return {"model": "selected_model_unknown", "source": "unknown"}


def _live_enabled(agent: Any) -> bool:
    config = getattr(agent, "config", None)
    return bool(getattr(config, "enable_live_call", False))


def _event_has_available_content(event: Mapping[str, Any]) -> bool:
    content_source = str(event.get("content_source") or event.get("content_quality_status") or "").strip()
    if content_source == "unavailable":
        return False
    if content_source:
        return True
    return bool(str(event.get("content") or event.get("evidence_text") or event.get("summary") or event.get("title") or "").strip())


def _json_safe(value: Any) -> Any:
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value
