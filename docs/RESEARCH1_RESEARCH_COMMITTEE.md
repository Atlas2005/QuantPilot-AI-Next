# RESEARCH1 Research Committee

RESEARCH1 adds a deterministic, in-memory research committee that combines INFO2/INFO3 information-agent signals with replay metrics. The output is a securities-firm-style research diagnostic report for offline review.

## Scope

The package lives in `quantpilot_core.research_committee` and exposes:

- `build_research_committee_report`
- `rank_research_candidates`
- `ResearchCommitteeView`
- `ResearchCommitteeReport`
- `ResearchCandidateRanking`
- `ResearchEvidenceBucket`

`build_research_committee_report` consumes supplied `InformationAgentSignal` values plus a mapping, pandas `Series`, or one-row pandas `DataFrame` of replay metrics such as `total_return`, `sharpe`, `sharpe_ratio`, `max_drawdown`, `win_rate`, `turnover`, `trades`, or `trade_count`.

`rank_research_candidates` consumes multiple committee reports or candidate mappings and ranks them by deterministic composite score.

## Deterministic Synthesis

The committee derives:

- bull evidence from positive, accumulation, and expansion information signals plus supportive replay metrics
- bear evidence from negative, distribution, and contraction information signals plus weak replay metrics
- neutral evidence from neutral, mixed, or low-confidence inputs
- conflicts from opposing information signals and mismatches between information score and replay score
- dominant thesis from the strongest evidence bucket
- risk thesis from drawdown, turnover, weak confidence, conflicts, or pressure evidence
- next experiment plan with offline research steps only

The composite score combines information score and replay score deterministically. It is a diagnostic score, not a prediction or profitability claim.

## Registry Tools

The default `ToolRegistry` exposes these RESEARCH1 tools as `PURE_IN_MEMORY`:

- `build_research_committee_report`
- `rank_research_candidates`

## Boundaries

RESEARCH1 is research diagnostics only.

It does not fetch or download external data, call DeepSeek, OpenAI, Anthropic, or any model service, manage tokens or credentials, connect to brokers, create execution paths, run Qlib training or `qrun`, or add live trading integrations.

The report does not provide production readiness, prediction accuracy, or profitability claims. It summarizes only supplied in-memory information signals and replay metrics.

The next experiment plan is limited to non-execution diagnostics, such as extending the replay window, stressing transaction costs, testing capacity sensitivity, comparing alternative signal thresholds, and adding missing information frames.
