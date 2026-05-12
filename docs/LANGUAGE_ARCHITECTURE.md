# Language Architecture

QuantPilot-AI 2.0 is Python-first, not Python-only.

## Preferred Roles

Python:
: orchestration, research workflows, adapters, contracts, validation tools, and agent tooling.

SQL / DuckDB:
: local analytics and reproducible tabular queries.

Parquet / Arrow:
: storage and interchange formats.

Polars:
: performance-oriented local data processing when justified.

C# / LEAN:
: possible external engine integration candidate, not something to rewrite.

TypeScript / React:
: possible dashboard and product UI later.

Rust / C++:
: only for proven bottlenecks after measurement.

## Constraint

Polyglot readiness must not become premature complexity.

