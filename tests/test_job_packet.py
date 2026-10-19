from io import BytesIO

from openpyxl import Workbook

from cnc_analyzer.job_packet import read_job_packet_bytes


def _packet_bytes():
    wb = Workbook()
    de = wb.active
    de.title = "DATA ENTRY"
    values = {
        "A7": "CUSTOMER:", "B7": "Datex Ohmeda",
        "A8": "PART NAME:", "B8": "Handle Frame",
        "A9": "PART NUMBER:", "B9": "1100-3105-000",
        "A10": "REVISION:", "B10": "Rev 108",
        "A11": "PROGRAM # / PALLET 1", "B11": "O4105",
        "A14": "OPERATION # :", "B14": "ALL",
        "A15": "MACHINE #", "B15": "#123",
    }
    for cell, value in values.items():
        de[cell] = value

    tools = wb.create_sheet("TOOL LIST")
    tools["A5"] = "TOOL #"
    tools["B5"] = "DESCRIPTION (SIZE)"
    tools["F5"] = "HOLDER TYPE"
    tools["G5"] = "TOOL PROJECTION"
    tools["H5"] = "TOOL LENGTH MEASURE (H) VALUE"
    tools["J5"] = "CUTTER R (D) VALUE"
    tools["K5"] = "SPECIAL INSTRUCTIONS"
    tools["A6"] = 1
    tools["B6"] = '1/2" Special Form Mill'
    tools["F6"] = "SOLID"
    tools["G6"] = "Flute"
    tools["H6"] = 5.6674
    tools["J6"] = "D1, D11"
    tools["K6"] = "25MM LOC"

    output = BytesIO()
    wb.save(output)
    return output.getvalue()


def test_reads_job_info_and_tool_list_from_excel_packet():
    packet = read_job_packet_bytes(_packet_bytes(), "packet.xlsx")
    assert packet.job_info.customer == "Datex Ohmeda"
    assert packet.job_info.part_name == "Handle Frame"
    assert packet.job_info.program_number == "O4105"
    assert packet.job_info.machine == "#123"
    assert packet.tools[0].tool_number == 1
    assert packet.tools[0].description == '1/2" Special Form Mill'
    assert packet.tools[0].d_value == "D1, D11"
