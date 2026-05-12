# Workflow Automation Policy

The project should avoid screenshot-heavy review workflows.

Every step should maintain:

- `docs/REVIEW_PACKET.md`
- `docs/CURRENT_PROJECT_STATE.md`
- `docs/DECISIONS.md`
- `docs/NEXT_CHAT_HANDOFF.md`

## Review Packet Requirement

`docs/REVIEW_PACKET.md` must be concise and copy-paste friendly. It should include:

- task name
- changed files
- whether `src/` was changed
- whether dependencies changed
- whether packages were installed
- whether market data/API was used
- whether broker/live/order path was created
- validation commands and results
- git status
- risks
- recommended next step

