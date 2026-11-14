# Staff identity, masking, and role/header aliases

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

Staff registry authoritative verified identifier is the primary join; original bilingual names are restricted. Alias suggestions may account for spelling/transliteration variations (Mohammad/Mohammed/Mohamad), articles (Khoury/El Khoury), middle or paternal names, accents and script variants. Similarity is a **candidate hint only**, never verified identity or payee selection.

Exact previously human-confirmed aliases may be reused if scoped to the same authoritative source and stable staff record and remain valid. On new/mismatched/missing ID, show authorized reviewer restricted candidate list; AI sees only opaque candidate IDs and short non-identifying reasons. Human explicitly confirms/refuses; backend stores mapping version, source value digest/restricted original, reviewer ID, timestamps, evidence and audit event. Never show names to Qwen even when asking to compare; deterministic backend generates similarity candidates over restricted names.

Canonical session roles are TRAINER and LOGISTIC; approved aliases include Trainer, Facilitator, ميسّر, مدرّب; Logistic, Logistics, لوجستيات. Hours-based roles: DRIVER, TRAINER, LOGISTIC, ADMINISTRATOR, DATA_ENTRY, FIELD_TEAM. New role labels may be suggested for canonical mapping by user; until human confirmed the record is flagged. Role mapping is **not** policy modification. Do not create new canonical roles from raw labels.

Header alias handling: original source headers remain in preserved evidence; model may suggest a field mapping only to a backend-allowlisted canonical field; unknown or contradictory headers go to confirmation. Confirmed mapping saves source signature (project/source type/version), original header digest, canonical field, reviewer/version/audit; no unreviewed model-based write.
