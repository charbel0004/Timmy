# Document classification / AI read vs edit permissions

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

| Files / data class | Authority | Runtime AI view | Runtime AI edit | Backend/human capability |
|---|---|---|---|---|
| `system/MAIN_SYSTEM.md`, `actions/ACT-*.md`, `shared/*`, `evaluators/*` | Versioned prompt governance in reviewed Git | **Read** selected prompt files through trusted loader | **NEVER** | NK/CN prompt maintainer edits Git after review |
| `manifest.json`, `contracts/*.json`, `integration/*` | Engineering contract via reviewed Git | Manifest may be consulted by backend; model sees only selected read-only instructions | **NEVER** | CN updates wiring/schema and commits |
| `docs/policies/session_policy_contract_v1.0.md` and v1.1 addendum | NK-approved policy; backend locked active version authoritative | Selected redacted approved policy excerpt only | **NEVER** | Separate human governance/versioned policy update; no runtime model write capability |
| Hours policy | Under configuration; rates/thresholds pending | Read locked role list and open-parameter notice | **NEVER** | NK/AJ confirm; CN activates versioned backend config |
| Approved planning worksheet & external report authority | External source owners | Read **verified summarized** status/plan/cutoff only, after authorization | **NEVER** | Source system remains authority; backend imports versioned evidence |
| Source staff directory, verified name mappings, payment destinations | Restricted identity/payee owners | **NO** real names, map keys or payment IDs; receive pseudonyms only | **NEVER** | Restricted trusted backend and designated reviewers; auditable lookup |
| Original timesheet files and source rows | Immutable evidence | **NO** raw file/rows; redacted minimal fields with evidence refs | **NEVER** | Backend parses and stores privately; human can append accepted corrections |
| Header/role/staff alias proposals | Model suggestion | Read sanitized candidate list; propose | Not persistent | Authorized human confirms; backend saves audited alias mapping |
| Audit and issue histories | Backend append-only | Read only bounded redacted events relevant to authorized action | **NEVER** | Backend appends events; authorized human may resolve issue with own event |
| Entitlements/groups/allocations, batch approval, settlement | Deterministic financial ledger + human/external authority | Read redacted explanations and recorded results only | **NEVER** | Backend transactions after precise authorization and evidence |
| Qwen narrative/explanations | Ephemeral generated content | Generate proposed structured JSON/prose | May generate draft **only**, not update authoritative data | Backend validates citations/shape and decides whether to persist a report narrative |
| Synthetic fixtures / test report authority | Isolated testing | Read redacted fixtures only | **NEVER** in prod | CN controls tests; synthetic outcomes cannot support live settlement |

**No AI self-modification:** Model may not edit policy, instructions, registry, permissions, guard logic or knowledge base in response to a prompt. A human Git edit does not mean runtime AI has write access. All user-facing UI review decisions are rendered and signed by application code.
