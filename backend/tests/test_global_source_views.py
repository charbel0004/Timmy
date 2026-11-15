"""Source views are read-only, per-row, and retain exact provenance."""
from types import SimpleNamespace

from timmy.global_source_views import preview_documents_for_project


def test_mixed_workbook_projects_are_partitioned_without_mutating_original():
    file = SimpleNamespace(id="file-1", project_id=None, sha256="a"*64,
                           original_filename="planning.xlsx")
    header = {"row": 1, "values": ["Project Code", "Activity Code", "Date"]}
    first = {"row": 2, "values": ["TCD", "TCD-101", "2026-09-01"]}
    second = {"row": 7, "values": ["FOS", "FOS-201", "2026-09-02"]}
    invalid = {"row": 8, "values": ["UNKNOWN", "BAD-999", "2026-09-03"]}
    sheet = {"name": "Mixed", "rows": [header, first, second, invalid]}
    record = SimpleNamespace(sheets=[sheet], row_count=4)
    source = [(file, record)]

    training = preview_documents_for_project(source, 1, "TCD")
    field = preview_documents_for_project(source, 2, "FOS")

    assert len(training) == len(field) == 1
    assert training[0][0].id == field[0][0].id == file.id
    assert training[0][0].sha256 == field[0][0].sha256 == file.sha256
    assert training[0][0].project_id == 1
    assert field[0][0].project_id == 2
    assert training[0][1].sheets[0]["rows"][1]["row"] == 2
    assert field[0][1].sheets[0]["rows"][1]["row"] == 7
    assert training[0][1].row_count == field[0][1].row_count == 1
    assert record.sheets[0]["rows"] == [header, first, second, invalid]
    assert preview_documents_for_project(source, 3, "OTHER") == []


def test_missing_or_ambiguous_project_column_cannot_be_assigned():
    file = SimpleNamespace(id="file-2", project_id=None, sha256="b"*64,
                           original_filename="unknown.csv")
    ambiguous = {"name":"Duplicate","rows":[
        {"row":1,"values":["project_code","Project Code","activity_code"]},
        {"row":2,"values":["TCD","FOS","TCD-001"]},
    ]}
    missing = {"name":"Missing","rows":[
        {"row":1,"values":["activity_code"]},
        {"row":2,"values":["TCD-001"]},
    ]}
    record = SimpleNamespace(sheets=[ambiguous,missing], row_count=4)
    assert preview_documents_for_project([(file,record)], 1, "TCD") == []
