# Workbook demonstration

Run from the repository root with the backend dependencies installed:

```sh
PYTHONPATH=backend .venv/bin/python scripts/run_payment_demo.py /path/to/Agent_Timmy_End_to_End_Demo.xlsx
```

The runner creates a new private temporary directory with a migrated SQLite
database, original workbook, and evaluation JSON. It never writes to the
default database. Qwen receives only the timesheet column headers via Timmy's
local Ollama adapter. The constrained interpretation is checked against the
fixed workbook schema. The deterministic adapter implements this synthetic
workbook's minute, overnight, per-session and cap rules. It does not replace
the separate six-session production preview.

| Worksheet | Destination or use |
| --- | --- |
| 00 | Metadata, retained in original only |
| 01 | Project, versioned policy, synthetic authority marker |
| 02 | Approved activity list and exact dated activity evidence |
| 03 | Synthetic volunteer identity lookup |
| 04 | Import and timesheet rows, raw source and row provenance |
| 05 | Synthetic report evidence for the exact activity |
| 06 | Separate synthetic planning and staff review decisions |
| 07 | Evaluation only, per-timesheet expected results |
| 08 | Evaluation only, comparison with independently calculated obligations |
| 09 | Simulated confirmation and reversal events |
| 10 | Evaluation only, per-obligation reconciliation |
| 11 | Fixture descriptions, retained in original only |

The default command calculates and persists candidates with pending authorization.
Its reconciliation report is explicitly a test projection. To record simulated
authorization and settlement, run with `--interactive`, set a password for the
new isolated administrator, inspect the calculated obligations, and type the
requested authorization phrase. This local operator action applies only to the
new synthetic database. Workbook approval cells never authorize payment.

Start the API with `TIMMY_DATABASE_URL=sqlite:////absolute/path/to/demo.db` and
`TIMMY_DEMO_MODE=true`. Set a distinct API port and launch the frontend with
`VITE_API_URL=http://localhost:<port>/api` and a distinct frontend port; set
`TIMMY_FRONTEND_ORIGIN` to that frontend URL. Sign in as `demo-admin`.
Dashboard, Projects, Timesheet Imports and Payment Batches display persisted
demo runs. Ask **Demo payment summary** in chat for the scoped totals.

The workbook mapping and reads are local backend operations. There is no external
MCP server registration, real report verification, or production obligation
authorization. The fixture supplies no independently authenticated historical
payment decisions. Live settlement remains unavailable. The demo adapter also
does not claim to support arbitrary alternate workbook schemas.
