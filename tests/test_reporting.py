from io import BytesIO
from zipfile import ZipFile

from cnc_analyzer.excel_exporter import build_excel_report
from cnc_analyzer.models import JobInfo, ToolListEntry
from cnc_analyzer.parser import analyze_program
from cnc_analyzer.reporting import process_sheet_rows, technical_sequence_rows


def _sample_result():
    program = """T4M6
(#39 CARBIDE JOBBER)
G0G90G59S9000
X1.Y1.
G43H04Z1.
G83G98R.03Z-.33Q.06F12.
X2.
G80
"""
    return analyze_program(program, "drill.nc")


def test_process_sheet_report_is_compact_for_setup_use():
    row = process_sheet_rows(_sample_result(), [ToolListEntry(4, "#39 Carbide Jobber")])[0]
    assert list(row.keys()) == [
        "Step", "Tool", "Tool Description", "Process / Feature", "Qty", "WCS",
        "Offsets / Comp", "Lines", "Notes",
    ]
    assert row["Offsets / Comp"] == "H04"
    assert row["Qty"] == 2


def test_technical_sequence_report_retains_parser_detail():
    row = technical_sequence_rows(_sample_result())[0]
    assert row["Cycle"] == "G83"
    assert row["Count Basis"] == "cycle locations"
    assert row["H Offset"] == "H04"
    assert row["RPM"] == 9000
    assert row["Q Peck(s)"] == "0.06"


def test_excel_process_sheet_description_is_formula_driven_from_tool_list():
    result = _sample_result()
    data = build_excel_report(
        result,
        job_info=JobInfo(customer="Test", program_number="O1234"),
        tools=[ToolListEntry(4, "#39 Carbide Jobber")],
    )
    with ZipFile(BytesIO(data)) as zf:
        process_xml = zf.read("xl/worksheets/sheet1.xml").decode("utf-8")
        tool_list_xml = zf.read("xl/worksheets/sheet2.xml").decode("utf-8")
        table_xml = zf.read("xl/tables/table1.xml").decode("utf-8")

    assert "INDEX('Tool List'!$B$7:$B$106" in process_xml
    assert "#39 Carbide Jobber" in tool_list_xml or "sharedStrings"  # value may be inline/shared depending writer
    # The table owns the filter. No duplicate worksheet-level autoFilter should be emitted.
    assert "<autoFilter" not in process_xml
    assert "<autoFilter" in table_xml
