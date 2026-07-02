# EXEC1 Execution Candidate Layer

EXEC1 is a deterministic bridge from RESEARCH and signal outputs to execution
intent candidates. It does not connect to external services, place trades, or
block candidates.

Inputs:

- Qlib-style signal scores
- INFO layer scores
- RESEARCH committee output

Output:

- `ExecutionCandidateReport`
- Top-N `ExecutionCandidate` rows

Scoring is a weighted combination of `signal_score`, `info_score`, and
`research_score`. A-share 100-share lot handling is included only as metadata on
each candidate so downstream systems can see the market convention without
EXEC1 performing sizing or enforcement.

