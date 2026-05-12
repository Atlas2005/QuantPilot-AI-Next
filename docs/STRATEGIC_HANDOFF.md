# Strategic Handoff

## Role Split

ChatGPT is responsible for professional planning, module kickoff review, open-source alternative assessment, upstream/downstream consistency review, module closure retrospective, and final review before commit.

Codex is responsible for creating files, organizing documentation, running validation commands, and producing concise review packets.

Codex is not the project architect and must not independently decide:

- strategic roadmap changes
- module order
- open-source selection
- trading-readiness judgment
- profitability claims

## Operating Model

ChatGPT provides architecture decisions and approved module prompts.

Codex implements only the scoped planning or implementation task from the ChatGPT-approved prompt.

After each task, Codex updates the review packet, current state, decisions, and next-chat handoff.

