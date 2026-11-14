# Planning registry integration review

This candidate ports the useful registry work from `caae632` and its source-only
code correction from `a2aeaf4` onto current main, preserving main's payment-policy
configuration, instruction pack, LangGraph integration and structural-review links.
No automatic code generator is retained.

## Migration resolution

Main already owns `0014_payment_policy_configuration`. The unmerged development
history used the same revision for different registry tables. This candidate adds
registry schema at **0015** and source authority at **0016**, following main's 0014.
0013 conversation mapping is identical in both histories and is included once.
Health readiness checks target 0016. No operational database was upgraded.

These migrations support the main migration history. A database previously upgraded
on the old development history cannot be identified safely by its revision string
alone. CN must inspect its actual schema and reconcile a copied database first;
do not run these migrations blindly over an old branch database. Both migrations
are forward-only. Recovery requires a verified backup and matching prior code.

0015 preserves old activities, file/mapping references and reports, adding nullable
identity/link fields. 0016 holds old codes as `legacy_review_required`, refuses
global collisions before mutation, and adds unique global identity plus explicit
source-format contracts. No legacy code, report cutoff or financial record is
rewritten. No schema merge revision is used to hide duplicate revision IDs.

## Runtime resolution

Main's saved StructuralValidation/review handoff and scope-change invalidation are
preserved. The registry is included in run/validation fingerprints. Planning is
registered before claims; exact reviewed formats can be reused within actor/project.
Weekly preflight blocks unknown mappings and invalid planning. Source bytes remain
immutable and SHA checked. Duplicate codes within a source batch now fail atomically.

Sidebar and snapshots carry the same activity identity; report cutoff reads require
consistent activity/project/code linkage. Legacy identity and unlinked reports are
held for review. Planning identity registration never authorizes financial eligibility.
Missing report/financial adapters retain their existing explicit blockers. Current
main's workflow instructions are extended instead of replaced with the older branch.

## Review boundary and validation

This PR must remain draft until NK/CN/domain-owner approves the changed source
identity authority, legacy report handling and manual-creation restriction, per the
consolidation assignment's mandatory merge gates. Source-format contracts have no
operational provisioning UI/API; no real contract is guessed or activated.

The final PR description and consolidation report record freshly executed backend,
frontend and disposable populated-upgrade results. Historical test reports are not
used as current evidence. This candidate is not a deployed or production-ready feature.
