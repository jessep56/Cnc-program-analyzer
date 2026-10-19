from cnc_analyzer.context import contextual_warnings, merge_tool_lists
from cnc_analyzer.models import JobInfo, ToolListEntry
from cnc_analyzer.parser import analyze_program


def _contour_result():
    return analyze_program("""T1M6
G54
G43H1Z1.
G1Z-.1
G41D11X1.
Y1.
G40
""", "contour.nc")


def test_packet_tool_description_overrides_program_description():
    result = analyze_program("""(T1 SHORT DESC H1 D1)
(T2 OTHER TOOL H2)
T1M6
G54
G43H1Z1.
G1X1.
""", "test.nc")
    tools = merge_tool_lists(result, [ToolListEntry(tool_number=1, description="Full Tool List Description", source="Job Packet")])
    assert next(t for t in tools if t.tool_number == 1).description == "Full Tool List Description"


def test_d_register_validated_against_explicit_tool_list_not_tool_number():
    result = _contour_result()
    allowed = [ToolListEntry(tool_number=1, description="Cutter", d_value="D1, D11", source="Job Packet")]
    warnings = contextual_warnings(result, allowed, JobInfo(program_number=result.program_name), packet_supplied=True)
    assert "D_TOOL_LIST_MISMATCH" not in {w.code for w in warnings}

    bad = [ToolListEntry(tool_number=1, description="Cutter", d_value="D1", source="Job Packet")]
    warnings = contextual_warnings(result, bad, JobInfo(program_number=result.program_name), packet_supplied=True)
    assert "D_TOOL_LIST_MISMATCH" in {w.code for w in warnings}


def test_program_number_mismatch_is_flagged():
    result = analyze_program("O4105\nT1M6\nG54\nG43H1Z1\nG1X1\n", "file.nc")
    warnings = contextual_warnings(result, [], JobInfo(program_number="O9999"), packet_supplied=False)
    assert "PROGRAM_NUMBER_MISMATCH" in {w.code for w in warnings}


def test_program_declaration_d_register_is_used_when_no_packet_exists():
    result = analyze_program("""(T1 1/8 ENDMILL H1 D25)
(T2 OTHER TOOL H2)
T1M6
G54
G43H1Z1.
G1Z-.1
G41D26X1.
G40
""", "decl_d.nc")
    tools = merge_tool_lists(result, [])
    warnings = contextual_warnings(result, tools, JobInfo(program_number=result.program_name), packet_supplied=False)
    assert "D_DECLARATION_MISMATCH" in {w.code for w in warnings}
