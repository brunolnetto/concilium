# P14-D — end-to-end Skill 04 scope-closure acceptance

Issue: #14. Stack position: follows merged P14-A/P14-B/P14-C; PR #145 registers P14-D in the formal execution DAG.

## Acceptance gaps covered

- A CERTIFIED Skill 04 run with an explicit, audited physical productivity graph extends beyond nominal duration when practicability reduces weekly output, closes exact physical scope Σq = Q, and keeps the final week partial rather than overproducing.
- A positive physical rate does not override a finite project calendar: when the available horizon cannot deliver Q, the real Skill 04 gate rejects the schedule, clears the canonical schedule, and reports the exact residual and horizon.
- Both fixtures exercise run_cronograma with the real catalog productivity structure, not an isolated closure helper.

## Authority boundary

Passing these schedule fixtures is only evidence for P14 physical schedule scope. It does not create a financial or project GO certificate. Issue #14 remains open until all five original acceptance criteria are evidenced; CI is intentionally disabled by the maintainer and these new tests have not been executed on the current head.
