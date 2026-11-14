# Planning activity identity — current integration contract

ACTIVITY-CODE-001 controls: activity codes originate exclusively in the authoritative
planning spreadsheet. Timmy never generates, infers, renumbers or reassigns them.
The earlier planning branch's generated `{ProjectCode}-A-0000` fallback is superseded.

- Validate against an explicitly reviewed project/source format contract; formats
  need not include a project prefix. Missing contracts block registration.
- Every code is globally unique and belongs to exactly one project. Missing codes,
  duplicate source rows, cross-project conflicts and changed names/dates require review.
- Register identity and source lineage only after scoped column review. Registration
  does not approve planning, staff, report authority, eligibility or payment.
- Exact repeated source imports preserve identity and do not duplicate source links.
  Historical generated or uncoded identities remain intact on explicit review hold.
- Timesheets, reports and sidebar records reference the same registered activity ID.
  They cannot create activities. Manual name-only creation is blocked.
- Exact unambiguous reviewed column formats may be reused only within the same
  actor/project. Row values and all authority gates are checked anew each time.
- Legacy report cutoffs are preserved in storage. Runtime use requires a matching
  project/code/activity ID; this integration does not invent historical linkage.
- Project names remain editable. Changing a project code after coded activities
  exist is blocked, preserving existing evidence references.

The integration requires NK/CN signoff on these authority and compatibility changes
before merge. There is no operational source-contract approval UI/API yet; tests
seed synthetic contracts only. See [integration notes](../architecture/planning-activity-registry.md).
