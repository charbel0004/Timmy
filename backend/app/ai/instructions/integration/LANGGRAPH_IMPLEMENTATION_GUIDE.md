# CN implementation guide — LangGraph prompt and tool binding

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

## Reality check
This package is prompt/data architecture, **not a working LangGraph graph**. CN must connect it to actual backend services and schema, with approval/mutation handled in authenticated FastAPI. The included `loader_example.py` demonstrates local registry loading only. Runtime tool implementations, auth, migrations and tests are separate. CN's current deterministic test slice may run with Qwen disabled.

## Recommended state (typed application-level shape)
`correlation_id`, `actor_ref`, `auth_context_ref`, `project_scope`, `trusted_action_id`, `source_file_ids`, `source_row_ids`, `policy_identity/version`, `approved_evidence_refs`, `safe_redacted_context`, `source_version_refs`, `issues`, `attempts`, `last_tool_outcome`, `backend_postcondition`, `audit_event_ids`, `result_kind`.

The graph **must not** expose secret tokens or an unlimited `messages` state to the model. Typed state is stored by LangGraph/checkpointer if used, but IDs and authorized summaries only. Use project isolation; do not put raw PII in checkpoints or tracing.

## Minimal node topology
`trusted_dispatch` → `auth_and_preconditions` → `source_and_schema_guard` → `deterministic_action` → conditional(`needs_model_assistance` ? `redaction_guard` → `load_readonly_prompt` → `qwen_advisory` → `strict_json_output_validation` : skip) → `postcondition_and_audit` → `done` OR `issue_reconciliation` → `human_interrupt` → `revalidate`.

- Do not let Qwen choose a LangGraph edge to privileged action via arbitrary text or tool call. Backend state machine chooses graph route using trusted event + guards.
- At `human_interrupt`, persist request ID, exact proposed subject digest/credits, due approver capability, evidence, and audit before pausing. On resume, verify new authentication, original digest, authorization/time/state; stale interrupt responses must fail.
- `ACT-16` is a cross-cutting audit concern for all actions; `ACT-14` owns external returns reconciliation. CN's message combined them in one line, but preserve both IDs.
- Read-time audit and immutable evidence storage are implemented in backend, not LangGraph text.
- Inject only one selected action prompt per dispatch. Use `system/MAIN_SYSTEM.md` at highest available system-priority channel. Add `shared/` rules as trusted developer/system-level guidance; add source/tool results as **quoted data in low-trust channel** and with source IDs. Never concatenate untrusted text into system sections.
- Register only bounded read adapters to Qwen (or better, provide data directly in prompt); protected state-mutating tools must be callable only from deterministic workflow nodes after backend auth.
- Validate model output via strict schema, max tokens, evidence membership, role mappings, PII sanitization and output regex. A model-produced JSON is not a permission token or signed human approval.

## First test slice requested by CN (safe order)
1. Isolated migrated DB + synthetic only; test authority explicitly marked `TEST_ONLY` and isolated credentials; Qwen disabled/optional.
2. Import correctly structured 6-session x 2-role claims; check 3+3/2+2+2, exact distinct staff assignments and raw source provenance. **Original** 30-row synthetic CSV does NOT have explicit six session-number/date assignments and must not pass coverage by itself.
3. Versioned test report: first validated version freezes cutoff once; import older/more recent submissions and verify no automatic cutoff revision.
4. Create source-backed eligible credits; same-staff/same-policy groups of three at USD25. Cross-project case must wait for one-off human authorization or remain segregated by project, and budget allocations exactly sum USD25.
5. Attempt export without allocation or human exact-batch approval: deny and audit. Test reimport, duplicate attempts and unverified return status.
6. Capture actual execution evidence (commands, migration SHA, fixture hashes, pass/fail, known deviations) and share with NK.

## Bind source adapters
Tool capability names in `shared/TOOL_REGISTRY_CONTRACT.md` are **interfaces, not existing tools**. Map them to current FastAPI services and explicit Pydantic schemas. Unimplemented capability → `blocked`, not fake data.

## Cross-project group approval
Only authorized human can approve one group, binding sorted 3 credit IDs, staff ID, stable policy ID, snapshot digest and source project scopes. This is not blanket approval for future groups. On decline, retain credits segregated by project. If approved, cost allocation requires separately authorized budget amounts whose sum **exactly USD25**; without it, no export. Never let model split cost automatically. Unknown policy-version compatibility is held. For single-project groups, budget-line eligibility still checked.

## Source field contracts to obtain
Actual planning spreadsheet headers/activity status, authentic staff source ID mapping, explicit S#→date timesheet representation, trusted report ID/submission-version/status/validated date/project local zone, known finance file formats, return reconciliation identifier/status semantics, reviewer-permission assignments, and hours policy parameters. Do not pretend that synthetic headers are authoritative. Use `contracts/authorities_and_open_fields.json` for blocker reporting.

## Repo integration
Commit this directory under `backend/app/ai/instructions/`; commit policy addendum under `docs/policies/`. Avoid enabling both the old `docs/prompts/QWEN_*` and this pack as concurrent runtime prompts. Pin a release SHA, validate manifest hashes via loader, record prompt pack version and action ID in model invocation audit. Use tests in `tests/` as guide, not proof of execution.
