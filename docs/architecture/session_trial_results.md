# Isolated session-policy trial

Migration 0007 adds nine session_trial tables for source bytes and digests,
row lineage, occurrence and assignment keys, report versions and cutoff
references, credits, groups and links. Existing tables are preserved.
The fixture runner uses a fresh temporary SQLite database and is outside the
application API. Its report events, staff IDs and policy seed are synthetic.

| Contract | Implementation | Test evidence |
| --- | --- | --- |
| §§1–2 occurrence order, day patterns, distinct staff and role coverage | session_rules.coverage and occurrence/assignment constraints | Focused tests and A/B fixtures passed |
| §3 completeness and report gate | Fixture trial | A/B validated through trusted test events, C complete with report pending |
| §4 version-specific cutoff | Trial report versions and first-validation reference | B cutoff remained July 12 after resubmission; late claims blocked |
| §3 credit grouping and remainder | session_pool.pool_credits | Expected synthetic pools matched; 10 groups total, zero on retry |
| §5 raw evidence and issues | Fixture sources, row lineage and coverage checks | 30 staging rows blocked; 11 of 12 negative fixtures matched |
| §§3 and 6 authorization and accounting | Trial export_blockers | Cross-project synthetic pools returned allocation and batch approval blockers |

BAD-11 provides a different staff ID from the existing S3 Trainer. That is
a competing claim; an exact duplicate would repeat the same verified staff ID.
The supplied fixture files were kept unchanged.

Run from the repository root with an environment containing backend dependencies:

    PYTHONPATH=backend python scripts/session_fixture_trial.py /path/to/Agent_Timmy_Corrected_Test_CSVs
    PYTHONPATH=backend python -m pytest -q backend/tests

Both ran in an isolated copy. The fixture trial completed with one reported
expectation mismatch and pytest reported 59 passed. The live database was
not migrated. The full S-T/DB-S matrix is outstanding. Application upload,
review, allocation authorization, exact-batch approval, export, external
reconciliation, and UI integration still need their production contracts.
Hours-based calculation regression coverage requires an implemented hours
calculation service.
