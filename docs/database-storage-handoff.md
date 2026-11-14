# CN-DB-01 review handoff

Migration 0003 extends the existing SQLite schema. Existing integer account and
project identifiers remain in place to preserve sessions, memberships and API
contracts. Legacy project codes and audit context are nullable. No project
codes are inferred. New file metadata uses application-generated UUID strings.

| Table | Added columns and constraints |
| --- | --- |
| projects | project_code, nullable unique index |
| stored_files | id (UUID primary key), purpose, original_filename, relative_storage_key (unique), sha256 (64 lowercase hexadecimal characters), size_bytes (positive), mime_type, uploaded_at, project_id and uploaded_by (nullable indexed foreign keys) |
| audit_events | trigger, resource_type, resource_id, outcome, evidence_file_id (nullable indexed foreign key) |

The file metadata table is a persistence foundation. Private filesystem
bootstrap, AGENT_TIMMY_DATA_DIR, atomic writes, integrity verification,
authorized downloads, and append-only evidence enforcement are deferred to
CN-DB-02 and later. The deployment continues to use its configured SQLite URL.
Local SQLite artifacts and proposed runtime directories are excluded by
.gitignore. Store private documents outside Git and public hosting directories
when filesystem integration is added.

Review the migration and constraints before DB-02. The next phase needs
anonymized format examples, authoritative staff identifier mapping and
unmasking permissions. Financial workflow phases require approved monetary
and grouping rules, reviewer authority, and external evidence contracts.
