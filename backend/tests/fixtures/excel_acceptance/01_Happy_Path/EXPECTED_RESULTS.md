# Run 1 · Clean Happy Path

## A. Test identity

- Dataset version `1.0.0` · folder `01_Happy_Path` · inspected GitHub main SHA `df18ad3bd6b9ec8829b2903e1d71d5b2c531f1a8`.
- Purpose: Clean multi-project baseline and independent payment arithmetic.
- All persons, activities, centres-as-assignments, evidence and references are synthetic. No bank details or live payment destinations.
- Primary period September 2026, local zone `Asia/Beirut` (UTC+03:00 on fixture dates). No October records.
- Reset: start a fresh disposable database and isolated document root from the SHA, apply migrations, create the two projects and one coordinator, seed only the trusted fixtures below, then upload the four files. Reset between runs and before re-running independent scenarios. Replay only within the replay test.

## B. Workbook inventory

Data rows exclude header rows. The directory contains eight identities shared by both projects. Original coordinates always refer to the delivered files.

| Workbook | Sheet | Classification | Data rows | Projects | Purpose / expected mapping | Expected authority | SHA-256 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| planning.xlsx | Activities | Approved planning source | 2 | TCD + FOS | Project/code/name → project_code/activity_code/activity_name; approved dates → approved_start_date/approved_end_date; retain approval, evidence ID and centre. | Source-issued fixture values, conditional on the configured approved test contract and reviewed mapping. | a327051d9548fc4cf4623d04ba2e695b25cc974fac4ad7ab679e603f3b18df39 |
| planning.xlsx | Staff reference | Synthetic staff reference | 8 | TCD + FOS | staff_id/status → directory candidate; names and aliases → approved fixture identity lookup only after independent seeding. | Reference only. Test harness must seed and certify identities and aliases independently. | a327051d9548fc4cf4623d04ba2e695b25cc974fac4ad7ab679e603f3b18df39 |
| reporting.xlsx | Report history | External report fixture evidence | 2 | TCD + FOS | Project + activity + report ID/version; submission and validation timestamps, status, evidence ID, coverage. Bind displayed wall times to Asia/Beirut in trusted test provider only. | Workbook claims only. A separately authorized non-production provider must establish provenance and validation. | 64f4f5b9b13addda55f09861507a34f9b77c3f8ffd895a96e16fb8228a62a6f2 |
| timesheets_session.xlsx | Session claims | SESSION timesheet | 12 | TCD (source scope) | Project/code/staff/role/occurrence/date/submission → canonical claims fields; retain name, line ID, count, centre and notes. S1–S6 are explicit. | Source claims only. Reviewed mapping and corroborated identity, planning and reports are required. | 654ec1ab5a90e1fd0e36013ba87cce0feefae0d1d8e0d8fc08a3ef06f803b878 |
| timesheets_hours.xlsx | Shift claims | HOURS timesheet | 6 | FOS (one planted TCD code in Run 2 only) | Project/activity/staff/role/work date → hourly claim context; Clock in/out → local datetimes; retain submission, line ID, break, centre, remarks and material cost centre. Current mapping engine has no HOURS category. | Source claims only. Reviewed mapping and corroborated identity, planning and reports are required. | 620accd6cfe759a4d24d346fbee53bce106dd9fbb507efd1494e6ae0d3a1bbb9 |

## C. Test setup and prerequisites

1. Create one authenticated coordinator administrator for both projects. Seed TCD (Training and Community Development, SESSION) and FOS (Field Operations Support, HOURS) by name, acronym and family. Use no rate editor. Assign reviewed project-scoped permissions and keep the disposable environment offline from external finance endpoints.
2. Seed the controlled eight synthetic `staff_id` values from Staff reference with active status and establish approved aliases through a trusted fixture setup. In Run 2, “Rana Haddad” without a verified ID is intentionally ambiguous between SYN-101 and SYN-103. The approved directory values do not establish trust just by being uploaded. TRAINER and LOGISTIC are distinct session roles. FIELD_SUPPORT and DRIVER are controlled synthetic hourly roles.
3. Install reviewed synthetic PlanningCodeContract records `26-TCD-[0-9]{3}` and `26-FOS-[0-9]{3}`, each scoped to its owning project's ID with source/hash and reviewer. Only APPROVED planning records can release new work. Put any retired record in historical evidence, not the eligible registry.
4. For approved-path provider tests, explicitly configure an isolated ReportProvider under server control. Supply events independently verified against the scenario with original report ID, version, evidence, aware submission/validation timestamps in Asia/Beirut and frozen dates. Run 3 resubmission: feed the submitted v1, then add v1 validation, then v2 submission and validation as successive snapshots; the provider returns one event per version per sync, and the workbook retains each event row. With ordinary uploads only, record authority BLOCKED. Do not seed workbook claims directly as trustworthy just because they display VALIDATED.
5. Use inert synthetic destinations and an isolated export sink only if implemented. Use the same single coordinator for ordinary steps. Test finance approval with an explicitly authorized human click on an exact snapshot via the backend/UI, if available. Raw notes and chat text confer no manual approval. Do not contact a real provider or submit actual instructions.
6. Preserve the original combined workbooks. If using a project-scoped diagnostic projection, separately document each parent digest, original row, transformed date, alias mapping and actor. Projections are optional diagnostics and do not constitute passing the combined import.

- SESSION v1.0 §§2–4 requires six indexed pairs, distinct verified identities, strictly increasing 3+3 or 2+2+2, authoritative report validation and frozen submission cutoff. Three eligible credits of the same verified identity yield one USD 25 group.
- SESSION v1.1 overrides automatic cross-project grouping examples in v1.0. It requires exact one-off group approval plus cost attribution for cross-project SESSION groups. This suite has one SESSION project and does not exercise that pooling case.
- Fixed HOURS v1.0 §§1–2 permits overnight and deducts no breaks. Check the rolling 960 actual-minute limit across all available hourly records for the verified identity, deduplicate overlap, round accepted shifts to 30 min, floor monthly sum to whole hours and cap at 120 h per verified identity/project/month before converting at USD 5/h.
- No exact 15-minute ties are used. The treatment of the cross-month shift is intentionally unresolved. No scenario defines guessed cost allocation or permits automatic truncation for rolling breaches.
- A report claim, computed candidate, approved batch, export, external transfer and reconciliation are distinct states.


## D. Expected record-level results

| Case ID | Workbook | Sheet/row | Project | Staff ID | Activity | Original evidence | Expected outcome | Rule | Human action |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| R1-PLAN | planning.xlsx | Activities!2 | TCD | — | 26-TCD-001 | ورش مهارات التواصل \| Community facilitation; 2026-09-04–2026-09-05; APPROVED; PLN-R1-26-TCD-001 | Register exact source-issued code to its owning project and approved window. | Source integrity and authority | None at row level after authority setup. |
| R1-PLAN | planning.xlsx | Activities!3 | FOS | — | 26-FOS-001 | Field centre logistics and registration desk; 2026-09-08–2026-09-20; APPROVED; PLN-R1-26-FOS-001 | Register exact source-issued code to its owning project and approved window. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!2 | TCD/FOS | SYN-101 | — | Rana Marie Haddad / رنا حداد / Rana El Haddad / Fictitious verified identity | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!3 | TCD/FOS | SYN-102 | — | Karim Daher / كريم ضاهر / Karim El Daher / Fictitious verified identity | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!4 | TCD/FOS | SYN-103 | — | Rana Darine Haddad / رنا دارين حداد /  / Distinct person from SYN-101 | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!5 | TCD/FOS | SYN-104 | — | Léa Nassar / ليا نصار / Lea Nassar / Accent variant | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!6 | TCD/FOS | SYN-105 | — | Nour Karam / نور كرم / Nour El Karam / Fictitious verified identity | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!7 | TCD/FOS | SYN-106 | — | Maya Farah / مايا فرح / Maya El Farah / Fictitious verified identity | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!8 | TCD/FOS | SYN-107 | — | Sami Saad / سامي سعد / Samy Saad / Fictitious verified identity | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REF | planning.xlsx | Staff reference!9 | TCD/FOS | SYN-108 | — | Dima Younes / ديما يونس / Dima Yunes / Fictitious verified identity | Seed this synthetic ID and only approved aliases through a controlled disposable test fixture; name alone is not authority. | Source integrity and authority | None at row level after authority setup. |
| R1-REPORT | reporting.xlsx | Report history!2 | TCD | — | 26-TCD-001 | EXT-26-TCD-001 v1; 2026-09-06T09:30 → VALIDATED / 2026-09-07T12:00; EVID-R1-26-TCD-001-v1-status | Match exact project/code and preserve version; conditional validated cutoff is the submission local date. | Source integrity and authority | None at row level after authority setup. |
| R1-REPORT | reporting.xlsx | Report history!3 | FOS | — | 26-FOS-001 | EXT-26-FOS-001 v1; 2026-09-21T09:00 → VALIDATED / 2026-09-22T14:00; EVID-R1-26-FOS-001-v1-status | Match exact project/code and preserve version; conditional validated cutoff is the submission local date. | Source integrity and authority | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!2 | TCD | SYN-101 | 26-TCD-001 | TCD-1/001; Rana Marie Haddad; TRAINER; S1, 2026-09-04; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!3 | TCD | SYN-102 | 26-TCD-001 | TCD-1/002; Karim Daher; LOGISTIC; S1, 2026-09-04; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!4 | TCD | SYN-101 | 26-TCD-001 | TCD-1/003; رنا حداد; TRAINER; S2, 2026-09-04; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!5 | TCD | SYN-102 | 26-TCD-001 | TCD-1/004; Karim Daher; LOGISTIC; S2, 2026-09-04; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!6 | TCD | SYN-101 | 26-TCD-001 | TCD-1/005; Rana Marie Haddad; TRAINER; S3, 2026-09-04; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!7 | TCD | SYN-102 | 26-TCD-001 | TCD-1/006; Karim Daher; LOGISTIC; S3, 2026-09-04; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!8 | TCD | SYN-101 | 26-TCD-001 | TCD-1/007; Rana Marie Haddad; TRAINER; S4, 2026-09-05; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!9 | TCD | SYN-102 | 26-TCD-001 | TCD-1/008; Karim Daher; LOGISTIC; S4, 2026-09-05; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!10 | TCD | SYN-101 | 26-TCD-001 | TCD-1/009; Rana Marie Haddad; TRAINER; S5, 2026-09-05; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!11 | TCD | SYN-102 | 26-TCD-001 | TCD-1/010; Karim El Daher; LOGISTIC; S5, 2026-09-05; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!12 | TCD | SYN-101 | 26-TCD-001 | TCD-1/011; Rana Marie Haddad; TRAINER; S6, 2026-09-05; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-S01 | timesheets_session.xlsx | Session claims!13 | TCD | SYN-102 | 26-TCD-001 | TCD-1/012; Karim Daher; LOGISTIC; S6, 2026-09-05; count 1 | Pair exact occurrence, date and distinct verified roles; apply activity/report gate. | SESSION §2–4 | None at row level after authority setup. |
| R1-H01 | timesheets_hours.xlsx | Shift claims!2 | FOS | SYN-104 | 26-FOS-001 | FOS-1/001; Lea Nassar; FIELD_SUPPORT; 2026-09-08T08:00 → 2026-09-08T12:20; break —; Shift register attached. | Check actual duration, rolling limit and report; include eligible rounded shift in the project/month pool. | HOURS §1–2 | None at row level after authority setup. |
| R1-H01 | timesheets_hours.xlsx | Shift claims!3 | FOS | SYN-104 | 26-FOS-001 | FOS-1/002; Léa Nassar; FIELD_SUPPORT; 2026-09-09T08:00 → 2026-09-09T12:10; break —; Shift register attached. | Check actual duration, rolling limit and report; include eligible rounded shift in the project/month pool. | HOURS §1–2 | None at row level after authority setup. |
| R1-H02 | timesheets_hours.xlsx | Shift claims!4 | FOS | SYN-105 | 26-FOS-001 | FOS-1/003; Nour Karam; FIELD_SUPPORT; 2026-09-11T09:00 → 2026-09-11T15:00; break 45; Shift register attached. | Check actual duration, rolling limit and report; include eligible rounded shift in the project/month pool. | HOURS §1–2 | None at row level after authority setup. |
| R1-H02 | timesheets_hours.xlsx | Shift claims!5 | FOS | SYN-105 | 26-FOS-001 | FOS-1/004; Nour Karam; FIELD_SUPPORT; 2026-09-14T20:00 → 2026-09-15T04:00; break —; Shift register attached. | Check actual duration, rolling limit and report; include eligible rounded shift in the project/month pool. | HOURS §1–2 | None at row level after authority setup. |
| R1-H03 | timesheets_hours.xlsx | Shift claims!6 | FOS | SYN-106 | 26-FOS-001 | FOS-1/005; Maya Farah; FIELD_SUPPORT; 2026-09-19T10:00 → 2026-09-19T15:50; break —; Shift register attached. | Check actual duration, rolling limit and report; include eligible rounded shift in the project/month pool. | HOURS §1–2 | None at row level after authority setup. |
| R1-H04 | timesheets_hours.xlsx | Shift claims!7 | FOS | SYN-107 | 26-FOS-001 | FOS-1/006; Sami Saad; FIELD_SUPPORT; 2026-09-20T09:00 → 2026-09-20T13:00; break —; Shift register attached. | Check actual duration, rolling limit and report; include eligible rounded shift in the project/month pool. | HOURS §1–2 | None at row level after authority setup. |

## E. Expected issue register

No deliberately planted discrepancies. External authority and exact-batch approval are setup gates.

## F. Expected calculations

These are independent expected business results under the verified-source fixture and required review gates. They are scenario arithmetic rather than observed application outputs.

- TCD SYN-101 and SYN-102 each: 6 accepted role assignments in 3+3 → complete + validated → 6 eligible credits → 2 × USD 25 = **USD 50 each**. Total USD 100; zero residual.
- FOS SYN-104: 260 min → 270 min; 250 min → 240 min; disjoint → 510 min → floor 8 h, cap unchanged → **USD 40**, 30 min expires.
- FOS SYN-105: 360 min including 45-minute break + 480 min overnight; disjoint and unchanged by rounding → 840 min → 14 h → **USD 70**.
- FOS SYN-106: 350 min → 360 min → 6 h → **USD 30**. SYN-107: 240 → 240 min → 4 h → **USD 20**.
- September combined candidate total is USD 260 (TCD USD 100; FOS USD 160), with each policy pool kept separate. Zero exports or settlements.

## G. Expected workflow state

Follow the table top to bottom. Stop affected records at blockers, retain independent valid records where allowed and distinguish provisional structural outputs from actual commits.

| Step | Expected state | Required source evidence | Backend operation | Authority, review or blocker |
| --- | --- | --- | --- | --- |
| Authenticate and resolve TCD + FOS | Ready after setup | Coordinator login, membership, project policy families | Login/project read; row project resolution | Multi-project execution adapter BLOCKED if unavailable. |
| Intake, integrity, classify | Ready per scoped upload | Four hashes and original sheet/row coordinates | Read/parse XLSX, verify stored source hashes; propose classifications | Combined sources may be stored as bytes but execution is scoped and may reject. |
| Review and confirm mapping | Needs review on unfamiliar formats | Exact headers, mapping version and review receipt | Mapping proposal and confirmation; preserve originals | Unsupported report/hourly schemas BLOCKED in current mapping. |
| Planning and identity | Needs reviewed source evidence | Approved code pattern, scoped planning registration, fixture staff authority | Register source activity; resolve verified staff and aliases | Hold missing/unknown/conflicting code and ambiguous person. |
| Report verification | BLOCKED without provider | Authoritative report ID/version, positive validation and frozen cutoff | Trusted server-side sync, then check_reports | Workbook status is insufficient. Pending/rejected never releases financial eligibility. |
| Timesheet selection and validation | Independent valid records may proceed after gates | Reviewed plan, report, roles and claims | Approved selection; SESSION structural validation and HOURS elapsed-time rules | Current authoritative validation/selection adapters may block; provisional preview is not execution. |
| Issues and review | Read committed findings; pause affected records | Exact file/sheet/row and rule, recorded decision | Read existing discrepancy receipt; authorized issue resolution | No fictional issues, stale decisions, or invented correction. |
| Compute candidates | Eligible records only after authority | Accepted assignments/intervals, policy version, grouping ledger, rounding and cap | Deterministic session grouping/hourly candidate calculation | Current prepare-payment adapter BLOCKED; arithmetic below is oracle evidence. |
| Allocate and authorize | Needs exact-batch human approval | Verified destinations, approved cost allocation, immutable hash, actor permission | Persist reviewed allocation and exact-snapshot decision | Change a line and require fresh approval. Missing adapter or authority BLOCKED. |
| Export and reconcile | Unapproved export BLOCKED; settlement separate | Exact current snapshot approval plus trusted external returned evidence | Simulated/disabled export in disposable environment; status reconciled independently | No real transfer, no assumed settlement, and no partial/unknown status treated as settled. |
| Run summary and audit | Read actual committed state | Run/step receipts, actor, inputs, rule and decisions | Read stored receipts in chronological order | Held downstream nodes have attempted/executed false; no inferred tools. |

## H. Expected conversational behavior

Attach/reference all four files together in one coordinator conversation. Perform read-only control prompts independently from processing tests and retain request IDs.

| ID | Exact prompt | Expected meaning and operation |
| --- | --- | --- |
| T01 | Analyze all four uploaded Excel workbooks for both projects. | Identify four files, actual sheet types and both project references; propose mappings. Surface scope or format blockers. |
| T02 | Process the planning activities, reports, and timesheets for both projects. | Request authorized processing for TCD and FOS. Resolve scope; apply policy by project only when executable. |
| T03 | Show me all discrepancies, grouped by project and severity. | Read stored findings; report unrun stages and missing receipts. |
| T04 | حلل ملفات الدوام والتقارير للمشروعين. | Recognize analysis for both projects. Do not imply this executed if alias or workflow support is absent. |
| T05 | Prepare the September payment requests for both projects. | Require eligibility, destination, allocation and immutable exact-batch human approval before export; candidates are provisional. |
| T06 | Review the timesheets, but do not generate or export payments. | Read/review only; negation excludes payment preparation/export. |
| T07 | What have you completed, and what is still blocked? | Read actual committed workflow/step states. |
| T08 | Show which files, policies, and tools you used. | Report observable references only. LangGraph receipt is not an MCP call. |
| A01 | Inspect and check the registers for both projects. | Analysis synonym; propose precise intent if aliases conflict. |
| A02 | راجع الدوام للمشروعين واعرض المشاكل. | Arabic review and show issues; distinguish analysis/write from reading stored findings. |
| A03 | Run process_activity for TCD only. | Explicit workflow ID, TCD scope only, use actual recognized identifier process_activity. |
| A04 | Can you look at it? | Clarify ambiguous object/action; no writes. |
| A05 | What is the FOS project policy? | Read metadata for FOS; no writes or workflow trigger. |
| A06 | Run the monthly-stipend-teleport workflow. | Unknown workflow; report unsupported and take no action. |
| A07 | Do not export any payments. | No export, no approval, no transfer. |
| A08 | اعرض النتائج المخزّنة لمشروع TCD فقط. | Show stored results scoped to TCD; no FOS side effects. |
| A09 | Run show_issues. | Resolve explicit known read workflow or state unsupported syntax, with no fabricated steps. |

## I. Expected audit and observability

- Intake must reference original file SHA, file ID, sheet and physical row. Record each raw value and selected normalized interpretation, project and permanent activity ID.
- Record mapping proposal/version, confirmed inputs and reviewer. Preserve both original overlapping or duplicate source claims, report versions and the first frozen cutoff event.
- Record actor, workflow ID, run ID, request/fingerprint, ordered step, policy/version, issue code, outcome and human-review receipt when applicable. Use the persisted backend operation/execution status, including held steps; never report provisional structural data as a completed validation.
- Financial evidence includes verified identity, source credits or hours, duplicate protection, rounding/cap and excluded quantities, destination and allocation authorization, immutable snapshot hash, exact-batch human decision and separate trusted returned status.
- The future inspector should show actual LangGraph nodes, committed operations and MCP calls only when those calls were observably made. No hidden model reasoning or invented tools.

## J. Current implementation compatibility

Source inspection at the SHA above. No fixture workflow execution was performed to populate this table.

| Requirement | Available now? | Expected actual behavior | Missing work |
| --- | --- | --- | --- |
| Shared multi-project conversation | Partial | Conversation objects can hold attachments, while staged actions and run_workflow require a selected project_id. | Coordinator-wide multi-project execution and scope resolution. |
| Multi-project planning XLSX | No combined registration | A stored file has exactly one project_id; planning_activities rejects rows for the other project. XLSX dates parse as datetime strings, while approved_start_date/end_date must be 10-character ISO strings. | Reviewed per-project projections preserving rows/hashes and conversion to ISO dates, or a scoped multi-project parser. No app changes in this suite. |
| Multi-project reporting XLSX | No | Parsed source only; column_mappings has no report classification. | Report workbook mapping and trustworthy multi-project adapter. |
| External report authority | Partial | report_reconciliation.synchronize supports registered server-side ReportProvider and freezes first validated local date; spreadsheets/chat cannot create authority. ReportEvent has no status enum: missing validated_at represents no validation, and raw UNDER_REVIEW/REJECTED evidence must stay in source. | Controlled fixture provider, independent validation and verified timezone. |
| Staff identity verification | Partial | Directory/structural preview and human review exist. A directory tab or fuzzy name grants no financial identity, and normalized mapping drops noncanonical fields from the projection. | Seed independent verified IDs and aliases; review conflicts/unknowns. |
| Session payment calculation | Partial | Structural and standalone session logic exist; prepare_payment_request requires eligible credit adapter and exact batch approval. | Authoritative eligibility, grouping persistence and allocation/approval/export integration. |
| Hourly payment calculation | Pure candidate function | fixed_hours_policy.py provides deterministic candidate arithmetic; no hourly claim mapping or end-to-end ledger in the workflow. Unresolved issues can suppress an entire person/project/month candidate. | Reviewed mapping, verified claims, budget allocation, approval and export integration. |
| Payment export/settlement | Blocked in current workflow | Exact approval/file and trusted return/reconciliation handlers are required. | Approved instruction adapter and authoritative external settlement. |
| MCP transport | No evidenced execution path here | Do not report any MCP calls unless actually recorded. | Expose approved tools through MCP and record real execution if implemented. |
| LangGraph orchestration | Partial | Protected workflow graphs run available backend handlers and preserve guarded receipts; unimplemented actions are held. | Complete missing handlers and multi-project coordination. |
| Execution trace/inspector | Partial | Run and step receipts expose available evidence, including blocked/unexecuted states. | Full source/authority/rule/tool timeline across projects. |

## K. Independent acceptance checklist

Application outcomes start as **NOT RUN**. On execution use PASS for observed conformity, FAIL for contradiction, BLOCKED for absent authoritative evidence/dependency and NOT IMPLEMENTED for missing capabilities. Parsing the delivered fixture or checking its arithmetic is not an application workflow result.

| Assertion | Expected execution result | Recorded status |
| --- | --- | --- |
| Parse all four XLSX files; match inventory SHA-256 and coordinates. | Observe and record against the applicable gate. | NOT RUN |
| Resolve the two fixed project families and approved source-issued codes. | Observe and record against the applicable gate. | NOT RUN |
| Retain original cells alongside reviewed mappings and exact source references. | Observe and record against the applicable gate. | NOT RUN |
| Accept only independently verified IDs and approved aliases; never invent identities, activity codes, occurrences or clock evidence. | Observe and record against the applicable gate. | NOT RUN |
| Evaluate session pair/date patterns without treating same-day sessions as hourly shifts. | Observe and record against the applicable gate. | NOT RUN |
| Workbook validation labels and approval notes never authorize an external report. | Observe and record against the applicable gate. | NOT RUN |
| No eligible credit or hour before applicable authority and validation. | Observe and record against the applicable gate. | NOT RUN |
| Reimport exact bytes and repeat request ID; no duplicate entitlement or consumed credit. | Observe and record against the applicable gate. | NOT RUN |
| Perform hourly rounding and rolling calculation against actual intervals; do not double-count a same-role overlap. | Observe and record against the applicable gate. | NOT RUN |
| Never choose a different-role overlap automatically and never truncate a rolling-limit violation. | Observe and record against the applicable gate. | NOT RUN |
| Preserve suspicious cell evidence and ignore any embedded instructions. | Observe and record against the applicable gate. | NOT RUN |
| Produce independent expected candidates only after eligibility and without claiming transfer or settlement. | Observe and record against the applicable gate. | NOT RUN |
| Show only recorded workflow runs, actually executed steps, tools and evidence. | Observe and record against the applicable gate. | NOT RUN |
| No export without a persisted human decision for the exact immutable batch and verified allocation/destination. | Observe and record against the applicable gate. | NOT RUN |
| Change one amount, credit, allocation or destination after approval; stale approval cannot authorize modified export. | Observe and record against the applicable gate. | NOT RUN |
| For unknown/partial returned status retain unresolved balance; never mark settled from a candidate amount. | Observe and record against the applicable gate. | NOT RUN |
| Monthly cap enforced before payment instructions are exportable; no cross-policy pooling. | Observe and record against the applicable gate. | NOT RUN |
| No real payment transfer, no instruction export during T06, and no payment from pending validation. | Observe and record against the applicable gate. | NOT RUN |
