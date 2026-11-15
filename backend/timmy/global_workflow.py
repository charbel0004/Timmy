"""One coordinator-global conversation, separately auditable per-project workflow receipts.

This is the guarded *intake/routing* adapter. It never registers activities,
confirms mappings, validates third-party reports, or releases compensation.
A mixed workbook remains one immutable original; project attribution comes
from source rows and verified reference codes, not the file's storage scope.
"""
from datetime import datetime, timezone
from hashlib import sha256
import json
from time import time

from fastapi import HTTPException
from sqlalchemy import select

from .audit import audit
from .models import WorkflowRun, WorkflowStepReceipt, projects
from .project_discovery import discover_projects, render_project_discovery
from .workflow_graph import execute_graph
from .workflows import knowledge, step_result


def run_global_workflow(db, principal, config, conversation, documents, *, workflow_id, request_id):
    """Execute bounded, truthful LangGraph receipts per authorized project.

    The original workbook's bytes and owner are verified on each request.
    The downstream single-project validation/mapping adapter does NOT yet
    consume these records. Therefore Process and financial steps stay blocked.
    """
    definitions = {item.id: item for item in knowledge().workflows}
    if workflow_id not in definitions:
        raise HTTPException(422, "Unknown stored workflow")
    principal.require("projects:read")
    if workflow_id not in {"analyze_intake", "show_issues"}:
        principal.require("projects:manage")

    from .conversation_workflow import check_integrity  # Avoid import cycle.
    check_integrity(config, documents)
    overview = discover_projects(db, principal, documents)
    project_ids = [p["project_id"] for p in overview["projects"] if p["matched_rows"]]
    if not project_ids:
        return render_project_discovery(overview, processing_requested=True) + (
            "\nPROJECT_ROUTING_REVIEW_REQUIRED: No unambiguously matched project rows."
        )

    note = render_project_discovery(overview, processing_requested=False)
    report = [note, "\n### Actual project-specific workflow receipts"]
    for project_id in sorted(project_ids):
        principal.require("timesheets.view", project_id)
        if db.scalar(select(projects.c.status).where(projects.c.id == project_id)) != "active":
            raise HTTPException(409, "Project became inactive; request a new scope")
        original = sorted((f.id, f.sha256, r.row_count) for f, r in documents)
        fingerprint = sha256(json.dumps({
            "workflow_id": workflow_id, "knowledge": knowledge().version,
            "conversation_id": conversation.id, "actor_id": principal.user.id,
            "project_id": project_id, "sources": original,
            "row_discovery": overview,
        }, sort_keys=True).encode()).hexdigest()
        key = f"global:{conversation.id}:{request_id}:{project_id}"
        existing = db.scalar(select(WorkflowRun).where(
            WorkflowRun.actor_id == principal.user.id,
            WorkflowRun.request_key == key,
        ))
        if existing:
            if existing.fingerprint != fingerprint:
                raise HTTPException(409, "Workflow request identifier was reused with changed evidence")
            report.append(f"- Project {project_id}: existing run #{existing.id}, {existing.status}; "
                          "no steps replayed.")
            continue

        # Only a verified source checksum may complete intake. The row routing
        # is a *proposal*; it is not a confirmed planning or staff authority.
        def evaluate(step):
            if step == "verify_intake":
                return step_result(step, "completed", files=len(documents),
                    project_rows=next(p["matched_rows"] for p in overview["projects"]
                                      if p["project_id"] == project_id),
                    provenance="original_file_sha256_verified",
                    project_mapping="provisional")
            if step == "show_discrepancies":
                return step_result(step, "completed",
                    issue_codes=list(overview["issue_counts"].keys()),
                    evidence_kind="provisional_project_routing")
            # The global source has not yet received a trusted per-project
            # column mapping + source authority decision. In particular never
            # run planning registration on a file with a NULL project owner.
            return step_result(step, "blocked",
                ["MULTI_PROJECT_VALIDATION_ADAPTER_REQUIRED",
                 "PROJECT_SOURCE_MAPPING_CONFIRMATION_REQUIRED"])

        results = execute_graph(definitions[workflow_id].steps, evaluate)
        status = ("blocked" if any(x["status"] == "blocked" for x in results)
                  else "needs_review" if any(x["status"] == "needs_review" for x in results)
                  else "completed")
        run = WorkflowRun(
            actor_id=principal.user.id, project_id=project_id,
            request_key=key, fingerprint=fingerprint, workflow_id=workflow_id,
            knowledge_version=knowledge().version, created_at=int(time()),
            status=status, snapshot={
                "steps": results, "source_ids": [f.id for f, _ in documents],
                "source_sha256": {f.id:f.sha256 for f,_ in documents},
                "source_row_matches": next(p["matched_rows"] for p in overview["projects"]
                                           if p["project_id"] == project_id),
                "project_routing_issues": overview["issue_counts"],
                "project_routing_refs": overview["issue_references"],
                "mapping_authority": "unconfirmed",
                "payment_authority": "none",
                "execution": {"mode": "synchronous",
                              "completed_at": datetime.now(timezone.utc).isoformat()},
            })
        db.add(run)
        db.flush()
        for index, result in enumerate(results):
            db.add(WorkflowStepReceipt(
                run_id=run.id, step_index=index, step_id=result["step"],
                status=result["status"], attempted=bool(result.get("attempted", True)),
                executed=bool(result.get("executed", False)),
                blocked_by=result.get("blocked_by"),
                issue_codes=result["issue_codes"], recorded_at=int(time()),
            ))
        db.flush()
        audit(db, "workflow_run_recorded", principal.user.id,
              resource_type="workflow_run", resource_id=str(run.id),
              outcome=status, trigger=workflow_id)
        report.append(f"- Project {project_id}: {workflow_id} run #{run.id} — {status}.")
        for result in results:
            report.append(f"  - {result['step']}: {result['status']}"
                          + (f" ({', '.join(result['issue_codes'])})"
                             if result["issue_codes"] else ""))
    report.append("No cross-project source registration, identity confirmation, "
                  "report validation, payment eligibility, export or settlement was performed.")
    return "\n".join(report)
