# Agent Timmy action instructions

The approved session contract and database delta govern the workflow. The
action catalog translates those requirements into prompts, evidence requirements,
verification instructions, and stop codes. Trial entries describe isolated
synthetic behavior. Production authority comes from authenticated backend
services and approved external adapters.

## Prompt sources

| Function | Source |
| --- | --- |
| Conversation and allowed project lookup | backend/timmy/action_prompts.json and chat.py |
| Source column mapping | QWEN_TIMESHEET_MAPPING_SYSTEM.md (AT-AI-001, draft) |
| Grounded issue explanation | QWEN_DISCREPANCY_EXPLANATION_SYSTEM.md (AT-AI-002, draft) |
| Missing-information questions | QWEN_CLARIFICATION_SYSTEM.md (AT-AI-003, draft) |
| Row extraction | backend/timmy/prompts.py |
| Session behavior and physical schema | ../policies/session_policy_contract_v1.0.md and ../architecture/session_policy_database_delta_v1.0.md |

## LangGraph consumption

Use the Python package on the server. Load the catalog once and select a single
action by stable ID. Register tools explicitly in reviewed application code. The
catalog is documentation and prompt data, never an executable tool list.

```python
from timmy.action_catalog import ActionResult, load_catalog

catalog = load_catalog()
actions = {action.id: action for action in catalog.actions}
instruction = actions["ACT-07"].model_dump(mode="json")
result_schema = ActionResult.model_json_schema()
```

Suggested nodes are authenticate, propose, authorize, verify evidence, execute
registered service, verify outcome, persist audit, and summarize. Route unknown
or unavailable actions to a blocker. Only server-resolved actor and project
scope can enter a tool call. Load authoritative records by ID and recheck
authorization before showing any result, including a historical result.

Treat Pydantic validation as a shape check. Backend services must establish
evidence authenticity, scope, policy version, cutoff, postconditions, and
transaction integrity. Construct ActionResult from the service's committed
outcome. Never deserialize a model proposal into an authoritative result.

Pause a workflow for human confirmation when necessary. Resume with a
backend-verified decision bound to the actor, action, evidence version and
exact batch snapshot when applicable. On failure preserve original evidence,
return issue codes, and retry only idempotent operations with bounded attempts.
Keep tokens, raw staff identities, and verified payout destinations outside
model and graph checkpoints.

## NK inputs still required

Confirm planning and timesheet column mappings, approved staff aliases and
source IDs, report validation provenance and local date, compatible policy
versions, cost-attribution authority, approval and separation-of-duties rules,
export format, and external settlement matching rules. Record real-model
evaluation against P-01–P-10 before activating the three draft prompts.

The current chat consumes the catalog's system prompt and project reader
instructions. LangGraph can import the catalog and result schema. No graph
runner or new operational tools are wired into the live application.
