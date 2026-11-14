# CN-provided synthetic source examples — only for fixtures

**Agent Timmy prompt pack:** v1.0 (2026-11-14)  
**Classification:** PROMPT_READ_ONLY; editable by authorized code/prompt maintainers via reviewed Git commit, **not by the runtime AI**.

Inspected CN examples (synthetic; not a real external schema contract):

- `volunteer_directory_synthetic.csv`: `volunteer_id,name_en,name_ar,status` (12 synthetic rows).
- `timesheets_30_realistic.csv`: `submission_id,project_code,volunteer_id,volunteer_name,activity_code,activity_description,activity_date,role,session_count,hours_worked,report_reference,remarks` (30 rows).
- `rate_policies_demo.csv`: `policy_id,project_code,role,basis,sessions_per_block,amount_per_block_usd,remainder_policy,effective_from,policy_status`. Demo rates $25 initially unverified; subsequently NK approved session-family fixed USD25/3, **but the demo CSV itself is not authoritative policy source**.

Source ambiguities in synthetic timesheets: mixed dates, unapproved alias labels, duplicate claim, missing staff ID, negative count, unknown activity, and aggregate session counts with just one activity date. **This file cannot independently validate S1–S6 dates or 12 accepted role assignments.** CN's corrected synthetic fixture needs explicit S-number→work-date evidence and source-verified planning/test-report state. Human-approved alias mappings may recognize Facilitator and Arabic labels as Trainer, Logistics as Logistic; no inference of new canonicals.

**No fabricated 'accepted headers':** CN should configure header mapping only after reviewing real or test-source contracts and explicitly approving aliases. This guide is not permission to hardcode these test headers as the only authoritative source.
