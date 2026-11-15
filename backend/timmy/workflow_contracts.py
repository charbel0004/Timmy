"""Explicit contracts for every declared workflow step; absence is never success."""
CONTRACTS = {
 'verify_intake': ('Original files, access and checksum', 'Verified source receipt', 'Upload accessible originals', 'available'),
 'check_planning': ('Confirmed mapping, source-issued activity code, approved code contract, planning evidence', 'Verified planning receipt', 'Confirm project mappings; register source activities; obtain planning.verify review', 'guarded_handler_available'),
 'check_reports': ('Registered activity, approved Excel register designation, declared provenance and sufficient consistent validation evidence', 'Frozen cutoff with coordinator-declared provenance recorded explicitly', 'Designate the reporting register, confirm its mapping and official-export declaration in chat, and resolve report evidence findings', 'designated_excel_register_and_provenance_required'),
 'select_timesheets': ('Verified planning, staff and report receipts', 'Source-linked eligible claim selection', 'Complete each evidence review before selecting eligible claims', 'guarded_handler_available'),
 'validate_activity': ('Eligible claims and applicable fixed project policy', 'Deterministic rule outcomes and immutable source references', 'Execute session coverage or hourly rules on verified claims; resolve ambiguous source values', 'guarded_handler_available'),
 'resolve_discrepancies': ('Recorded rule outcomes and an approved resolution rule', 'Applied deterministic correction or human review receipt', 'Review each finding against its source; never infer an unauthorized correction', 'guarded_handler_available'),
 'show_discrepancies': ('Accessible stored receipts or source diagnostics', 'Grouped findings with unexecuted stages identified', 'Read the current stored workflow; source previews remain provisional', 'available'),
 'prepare_payment_request': ('Verified planning/staff/report evidence and deterministic eligible units', 'Immutable unapproved payment draft', 'Review draft lines; a scoped payments.allocate human verifies destinations and allocations, then a payments.approve human approves the exact final snapshot', 'guarded_handler_available'),
 'export_payment_request': ('Explicit authorized approval matching the unchanged exact batch snapshot', 'Downloadable payment instruction file for manual sending', 'Obtain the exact-batch human decision; export only the approved snapshot', 'guarded_handler_available'),
 'receive_payment_report': ('Owned original payment-return upload', 'Unverified received-return receipt', 'Upload payment return through the typed payment_return intake', 'available'),
 'reconcile_payments': ('Trusted returned status and exact exported batch references', 'Matched, partial, unknown or disputed balances', 'Configure a trusted return provider and match each external reference; never infer settlement', 'finance_return_contract_required'),
 'map_payments': ('Verified batch mapping and authoritative returned references', 'Source-linked reconciliation mapping', 'Review unknown or conflicting external references', 'finance_return_contract_required'),
 'archive_payment_evidence': ('Reconciled immutable evidence manifest', 'Archived original/evidence references', 'Retain original return and approved batch with verified reconciliation receipts', 'finance_return_contract_required'),
 'raise_payment_issues': ('Reconciliation findings with original references', 'Reviewable payment exceptions and recommended actions', 'Assign unresolved or disputed returns for authorized review', 'finance_return_contract_required'),
}


TRIGGERS = {
 'analyze_intake': 'Analyze or Import after uploading originals; upload alone does not start validation.',
 'process_activity': 'Process or Validate in shared chat. Confirming mappings or evidence resumes this same goal.',
 'weekly_cycle': 'Run weekly, or Process the documents and prepare a payment request. Human confirmations resume the original goal. The separate Monday 04:00 Asia/Beirut scheduler remains off by default and uses the legacy project runner.',
 'prepare_payment': 'Prepare a payment request. All evidence prerequisites are checked even when preparation is requested directly.',
 'show_issues': 'Show flags or Show discrepancies. This reads findings without resolving or approving them.',
 'resolve_issues': 'Resolve discrepancies. Remaining findings or missing authority require review; the request cannot invent corrections.',
 'payment_return': 'Reconcile or Payment report with a typed payment_return original. Settlement remains blocked pending an approved finance-return source contract.',
}


def catalog():
    from .workflows import knowledge
    result=[]
    for workflow in knowledge().workflows:
        steps=[]
        for name in workflow.steps:
            prerequisites, outcome, action, availability = CONTRACTS[name]
            steps.append(dict(step=name, prerequisites=prerequisites, expected_outcome=outcome,
                              next_action=action, availability=availability))
        result.append(dict(id=workflow.id, label=workflow.label, trigger_pattern=workflow.trigger_pattern,
                           instructions=workflow.instructions, trigger=TRIGGERS[workflow.id],
                           execution_path='legacy_project_runner' if workflow.id=='payment_return' else 'shared_chat_excel',
                           steps=steps))
    return result
