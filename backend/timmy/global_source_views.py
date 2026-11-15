"""Read-only views of a mixed workbook for project-specific structural previews.

A view is never a new upload, never source authority, and never a substitute for
approved column mappings. Every retained row preserves its original sheet/row,
file ID, checksum and file name. Unknown/conflicting rows are not silently
turned into approved claims: global discovery reports them separately.
"""
from types import SimpleNamespace

from .column_mappings import ALIASES, normalize_header


def preview_documents_for_project(documents, project_id, project_code):
    if not project_code:
        return []
    result = []
    for file, record in documents:
        sheets = []
        for source_sheet in record.sheets:
            original = source_sheet.get("rows", [])
            if not original:
                continue
            headers = original[0]["values"]
            candidates = [index for index, header in enumerate(headers)
                          if normalize_header(header) in ALIASES["project_code"]]
            if len(candidates) != 1:
                continue  # An ambiguous or missing header needs a human mapping.
            column = candidates[0]
            accepted = [source for source in original[1:]
                        if column < len(source["values"]) and
                        str(source["values"][column] or "").strip() == project_code]
            if not accepted:
                continue
            # Immutable source metadata and original positions are preserved.
            sheets.append({"name": source_sheet["name"],
                           "rows": [original[0], *accepted]})
        if sheets:
            source_view = SimpleNamespace(
                id=file.id, sha256=file.sha256, project_id=project_id,
                original_filename=file.original_filename,
            )
            record_view = SimpleNamespace(
                sheets=sheets, row_count=sum(len(sheet["rows"]) - 1 for sheet in sheets),
            )
            result.append((source_view, record_view))
    return result
