# Module Governance Policy

Every major module must follow this lifecycle.

## A. ChatGPT-Led Module Kickoff Review

Before Codex implementation, ChatGPT must professionally review:

- why this module should be done now
- whether it serves the final profitability goal
- upstream dependencies
- downstream consumers
- interface boundaries
- conflict with existing modules
- current GitHub/open-source alternatives
- adopt / wrap / borrow architecture / defer / avoid decision
- implementation boundary
- success criteria
- prohibited scope
- next-module impact

## B. Codex Implementation

Codex implements only the scoped task from the ChatGPT-approved prompt.

## C. Validation

Codex runs the required local validation and summarizes outputs.

## D. ChatGPT-Led Module Closure Review

After implementation, ChatGPT reviews:

- whether the module logic was correct
- whether the step sequence was efficient
- whether there was over-engineering
- whether there was unnecessary custom code
- whether newer or better GitHub solutions should replace it
- whether the module should remain core, adapter, fixture, guardrail, or be deprecated
- whether it increases or decreases future profitability probability
- whether the next module plan must change

## E. Next Module Readiness Review

Before starting the next module, ChatGPT checks:

- upstream/downstream consistency
- roadmap impact
- open-source refresh needs
- risks created by the previous module

## Codex Limitation

Codex documents this governance structure but must not pretend to be the strategic reviewer.

