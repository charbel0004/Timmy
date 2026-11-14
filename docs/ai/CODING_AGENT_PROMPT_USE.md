# Coding-agent prompt-use note

The primary coding-agent instructions are:
- `docs/agents/NK_CODING_AGENT_SYSTEM.md` (NK domain coding agent)
- `docs/agents/CN_CODING_AGENT_SYSTEM.md` (CN UI/deployment/fixture coding agent)

Root/scoped `AGENTS.md` files are repository-local instructions that both agents must honor. Send agent a bounded task authorization using `docs/procedures/CODING_AGENT_SESSION.md` **in addition** to the system prompt; a prompt alone is not approval to run tools. If a hosted coding agent's platform conflicts with local instructions, enforce guardrails in that platform's permissions and human review flow.

`QWEN_*.md` files are runtime **application-model prompts**, not code-agent prompts. They must not be repurposed to authorize repository changes or financial actions.
