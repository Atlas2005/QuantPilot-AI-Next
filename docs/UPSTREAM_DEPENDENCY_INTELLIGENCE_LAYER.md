# Upstream Dependency Intelligence Layer

R1 adds a target layer for monitoring external dependency and upstream risk.

This is a documentation target only. It does not install dependency tooling, configure bots, or fetch external metadata in R1.

## Purpose

The layer should track:

- GitHub maintenance activity
- PyPI release history
- license and commercial-use risk
- security advisories where available
- dependency tree risk
- breaking version changes
- abandoned or renamed projects
- upstream data-provider behavior changes
- broker or execution-adjacent scope creep

## Required Candidate Fields

The R1 integration matrix requires each candidate to include:

- license risk
- maintenance risk
- dependency risk
- isolated prototype requirement
- update policy requirement

## Future Update Policy

High-risk dependency updates should require review before merge, especially for:

- quant frameworks
- data-source libraries
- agent frameworks
- broker/live trading libraries
- execution-related packages
- market data packages

Automatic merge remains prohibited for high-risk dependencies.

## R1 Boundary

R1 records the need for upstream intelligence. It does not perform live upstream checks and does not change project dependencies.
