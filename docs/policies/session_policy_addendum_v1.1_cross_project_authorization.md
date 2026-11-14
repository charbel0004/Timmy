# Agent Timmy — Session Policy Addendum v1.1: Cross-Project One-Off Authorization

**Decision authority:** NK | **Date:** 2026-11-14 | **Status:** Approved policy clarification; implement alongside `docs/policies/session_policy_contract_v1.0.md`. This addendum supersedes any suggestion in that contract that cross-project credit pooling can form/export automatically. It does not remove session coverage, validation or financial approval gates.

## Locked scope
One payable group comprises exactly **three distinct eligible staff-session credits** from the **same verified staff identity and same approved session policy identity** at USD **25.00**. Within one project, credits may span session-role (Trainer/Logistic), activity, date, and week. Across different projects, combining credits into one group is **not automatic** even if they share staff and policy.

## One-off cross-project authorization
For a group proposal with source credits from multiple projects:
1. Preserve the exact 3 source-credit IDs, project IDs, verified staff ID, stable policy ID, policy version references, their report-validation evidence, snapshot hash and candidate USD25 total.
2. Flag `CROSS_PROJECT_APPROVAL_MISSING` and ask a backend-authorized human reviewer to approve **that exact group once** or decline. Model cannot click/authorize.
3. On approve, persist reviewer identity, permission scope, decision, time, snapshot hash, source projects, approved group ID and append-only audit. A changed credit/member/policy invalidates that authorization; it is NEVER reusable for other groups.
4. On decline, preserve credits and **keep project pools separate**; within each project credits become a payment group only upon reaching its own threshold of three eligible credits. Do not mark a previously proposed cross-project group paid or consume its credits.
5. On authorized cross-project grouping, require an explicit separately authorized **budget-line cost allocation** across originating project/budget references, totaling exactly USD25.00, before final instruction export. Neither AI nor system invents an equal/proportional split; unknown allocations block export.
6. Separate exact immutable batch human approval remains mandatory even after cross-project authorization. Reconciliation and settlement require returned authoritative external evidence.

## Invariants and testing
- Same-policy, same-staff only; cross-policy never; mixed policy-version compatibility unresolved, so hold pending review.
- One source credit can be consumed by only one committed payment group. Proposed groups do not double-lock credits or permanently strand them; use transactional unique membership and deterministic selection.
- Test 2 credits Project A + 1 Project B: no exportable group without one-off approval and approved USD25 budget attribution; human decline leaves 2+1 project-local balances; after A receives another eligible credit, A-only USD25 group can form.
- Test replay: previous approval cannot authorize a new group; changed credit IDs invalidate hash/approval; payment-batch human approval is a distinct subsequent gate.

**AI permissions:** READ approved summarized policy only; may explain and request a human decision; cannot create/activate/edit policy, approve cross-project pairing, allocate budget, approve batch or export.
