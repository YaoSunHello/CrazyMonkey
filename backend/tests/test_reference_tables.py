"""Every workbook caller gets the same complete, normalized table schema."""

import pytest
from openpyxl import Workbook

from app.reference.tables import from_workbook, load_tables


SPEC = {
    "project_codes": {
        "sheet": "Project Code Report",
        "columns": ["Project Code", "New Project Code"],
    }
}


def workbook_path(tmp_path, headers):
    path = tmp_path / "reference.xlsx"
    book = Workbook()
    sheet = book.active
    sheet.title = "Project Code Report "
    sheet.append(headers)
    sheet.append(["FIRST", "SECOND", "IGNORED"][:len(headers)])
    book.save(path)
    book.close()
    return path


@pytest.mark.parametrize("loader", ["from_workbook", "load_tables"])
def test_partial_required_columns_are_rejected_by_every_loader(tmp_path, loader):
    path = workbook_path(tmp_path, ["Project Code"])
    with pytest.raises(ValueError, match="missing required columns: New Project Code"):
        if loader == "from_workbook":
            from_workbook(path, SPEC)
        else:
            load_tables({"tables": SPEC, "workbook": {"location": str(path)}})


def test_complete_columns_keep_normalized_matching_and_drop_unrequested_data(tmp_path):
    path = workbook_path(tmp_path, [" project code ", "NEW PROJECT CODE ", "Unused"])
    table = from_workbook(path, SPEC)["project_codes"]
    assert table.columns == ["project code", "NEW PROJECT CODE"]
    assert table.rows == [{"project code": "FIRST", "NEW PROJECT CODE": "SECOND"}]
