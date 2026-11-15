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
    def has_project(sheet):
        rows = sheet.get('rows', [])
        if not rows:
            return False
        columns = [i for i, h in enumerate(rows[0]['values'])
                   if normalize_header(h) in ALIASES['project_code']]
        if len(columns) != 1:
            return False
        column = columns[0]
        return any(column < len(row['values']) and str(row['values'][column] or '').strip() == project_code
                   for row in rows[1:])
    project_present = any(has_project(sheet) for _, record in documents for sheet in record.sheets)
    result = []
    for file, record in documents:
        sheets = []
        for source_index, source_sheet in enumerate(record.sheets):
            original = source_sheet.get("rows", [])
            if not original:
                continue
            headers = original[0]["values"]
            candidates = [index for index, header in enumerate(headers)
                          if normalize_header(header) in ALIASES["project_code"]]
            if not candidates and {'staff id', 'status'} <= {normalize_header(h) for h in headers}:
                # A shared reference contributes matching candidates only. It
                # does not certify identity or supply project/payment authority.
                sheets.append({'name': source_sheet['name'], 'rows': original, 'source_sheet_index':source_sheet.get('source_sheet_index',source_index)})
                continue
            if len(candidates) != 1:
                continue  # An ambiguous or missing header needs a human mapping.
            column = candidates[0]
            accepted = [source for source in original[1:]
                        if column < len(source["values"]) and
                        str(source["values"][column] or "").strip() == project_code]
            if not accepted:
                continue
            # Immutable source metadata and original positions are preserved.
            sheets.append({"name": source_sheet["name"], 'source_sheet_index':source_sheet.get('source_sheet_index',source_index),
                           "rows": [original[0], *accepted]})
        if sheets and project_present:
            source_view = SimpleNamespace(
                id=file.id, sha256=file.sha256, project_id=project_id,
                original_filename=file.original_filename,
            )
            record_view = SimpleNamespace(
                sheets=sheets, row_count=sum(len(sheet["rows"]) - 1 for sheet in sheets),
            )
            result.append((source_view, record_view))
    return result
