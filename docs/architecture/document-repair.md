# Spreadsheet intake repair

The prior chat composer kept a browser File array and sent only message text to
the API. There was no document upload route or conversation association. The
local database had zero stored-file records and the configured document
directory was absent. Previously selected files need to be attached again.

Migration 0008 adds document_imports and links it to existing stored_files and
conversations. Conversation deletion clears the association while preserving
project evidence. Intake stores original bytes in .timmy-data/documents by
default. TIMMY_DOCUMENT_ROOT can change this private location. A SHA-256
digest accompanies the file and is verified before authorized download.

The API bounds and parses CSV and XLSX synchronously. Parsed rows retain
sheet and row provenance. A parsed document awaits confirmed mapping. Intake
does not turn spreadsheet text into policy, approved activities, authoritative
reports, validated claims, or financial records.

The chat harness offers one additional structured read operation,
analyze_documents. It reports visible conversation document IDs and row
counts without sending raw cells to Qwen. Audit records are committed alongside
the corresponding chat turn. This is an in-process tool, with MCP transport
and detailed row analysis still pending.

Run with the backend dependencies from requirements.txt, ./scripts/start-api.sh
and npm run dev --prefix frontend. In AI Assistant, open Context, select an
active assigned project, attach CSV/XLSX and send a message. Check the file
link in the composer and the Timesheet Imports page after reopening the chat.

Production mapping confirmation, report authority, session validation workflow,
allocation/approval/export and settlement are outstanding. Keep the isolated
session fixture trial separate from live operational and financial metrics.
