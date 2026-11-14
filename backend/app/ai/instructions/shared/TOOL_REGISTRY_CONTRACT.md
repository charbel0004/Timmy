# Capability registry — interfaces, not built tools

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

The `capability` strings in `manifest.json` and the action files are **proposed named backend adapters**. They are not existing LangGraph tools, do not constitute invocation permission, and must be mapped by CN to actual FastAPI/service functions with an explicit human/agent permission matrix. No generic filesystem, shell, SQL, URL fetch, arbitrary network, dynamic code execution, prompt or policy write capability may be exposed to Qwen.

| Capability | Allowed service behavior | Authority |
|---|---|---|
| `source.describe_file` | Bounded file metadata, type, integrity and provenance | Backend |
| `source.read_redacted_rows` | Structured allowlisted excerpt, with source IDs | Backend |
| `planning.read_approved` | Read authoritative planning activity records | Backend |
| `staff.read_masked_directory` | Opaque staff/candidate refs only | Backend |
| `mapping.propose` | Return nonbinding alias/header proposal | AI-assisted |
| `validation.read_findings` | Read deterministic issue and rule results | Backend |
| `activity.read_sessions` | Bounded session occurrence/assignment summaries | Backend |
| `hours.read_entries` | Bounded normalized hour evidence | Backend |
| `reports.read_authority_status` | Read source-backed report version/status | Backend |
| `finance.read_group_proposals` | Read group credits/allocator review metadata | Backend |
| `finance.read_batch_digest` | Read immutable approved batch summary | Backend |
| `payments.read_returns` | Read redacted authoritative external return summaries | Backend |
| `issues.read_timeline` | Read bounded redacted event history | Backend |
| `audit.read_scoped` | Read permissible safe audit event IDs | Backend |

For all *writes* (import staging, mapping confirmation, reviewer decision, report freeze, credits/group creation, allocations, batch approval/export, settlement, audit) the **backend/human UI** owns the transaction. Qwen output is at most a proposal/instruction to the person, not a transaction request that automatically executes.
