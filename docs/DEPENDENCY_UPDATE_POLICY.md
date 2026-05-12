# Dependency Update Policy

Dependency update tools such as Renovate or Dependabot may later be used only to open pull requests.

Automatic merge into the main branch is prohibited for high-risk dependencies.

## High-Risk Dependencies

- quant frameworks
- data-source libraries
- agent frameworks
- broker/live trading libraries
- execution-related packages
- market data packages

## Review Requirement

High-risk dependency updates require human and ChatGPT-led review before merge.

Step 0A does not install dependencies or configure dependency automation.

