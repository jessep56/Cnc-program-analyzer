from cnc_analyzer.parser import analyze_program


def test_preloaded_tool_does_not_replace_current_tool_description():
    program = """T2
M6
T3
(1/2 CARBIDE EM)
G0G90G55S8000
G43H02Z1.0
G1Z-.05F10.
X1.0
T3
M6
T4
(1/4 SPOT DRILL)
G0G90G55
G43H03Z1.
G81R.03Z-.05F9.
X1.
G80
"""
    result = analyze_program(program, "test.nc")
    assert [c.tool_number for c in result.tool_changes] == [2, 3]
    assert next(t for t in result.tool_summaries if t.tool_number == 2).description == "1/2 CARBIDE EM"
    assert next(t for t in result.tool_summaries if t.tool_number == 3).description == "1/4 SPOT DRILL"


def test_program_tool_declaration_is_source_for_description_and_feature_does_not_overwrite_it():
    program = """O4041
(T1 6MM ENDMILL H1 D1)
(T2 1/8 ENDMILL H2 D2)
(MILL FRONT EDGE)
T1M6
G54
G43H1Z1.
G1Z-.1
X1.
(BORE WALL CORNER)
G81Z-.2R.1F2.
G80
"""
    result = analyze_program(program, "O4041")
    assert result.declared_tools[0].description == "6MM ENDMILL"
    assert next(t for t in result.tool_summaries if t.tool_number == 1).description == "6MM ENDMILL"
    assert any(s.feature == "BORE WALL CORNER" for s in result.sequences)
    assert all(s.description != "BORE WALL CORNER" for s in result.sequences)


def test_canned_cycle_counts_first_location_and_modal_xy_blocks():
    program = """T4M6
(#39 CARBIDE JOBBER)
G0G90G59S9000
X1.Y1.
G43H04Z1.
G83G98R.03Z-.33Q.06F12.
X2.
Y2.
X3.Y3.
G80
"""
    result = analyze_program(program, "drill.nc")
    cycles = [s for s in result.sequences if s.cycle == "G83"]
    assert len(cycles) == 1
    assert cycles[0].quantity == 4
    assert cycles[0].work_offset == "G59"
    assert cycles[0].h_offset == "H04"


def test_extended_work_offset_and_same_tool_multiple_cycles():
    program = """T9M6
G0G90G58
G43H09Z1.
G83R-.1Z-.5Q.1F4.
G80
G0G90G54.1P11
G83R-.2Z-.6Q.1F4.
G80
"""
    result = analyze_program(program, "extended.nc")
    cycles = [s for s in result.sequences if s.cycle == "G83"]
    assert [s.work_offset for s in cycles] == ["G58", "G54.1 P11"]
    assert [s.quantity for s in cycles] == [1, 1]


def test_feature_comments_split_milling_sequences():
    program = """(T1 1/2 ENDMILL H1 D1)
(T2 1/4 ENDMILL H2 D2)
T1M6
G54
G43H1Z1.
(MILL FRONT EDGE)
G1Z-.1
X1.
(MILL FRONT PADDLE)
G1Z-.2
X2.
"""
    result = analyze_program(program, "features.nc")
    milling = [s for s in result.sequences if s.tool_number == 1]
    assert [s.feature for s in milling] == ["MILL FRONT EDGE", "MILL FRONT PADDLE"]


def test_h_mismatch_is_flagged_but_d_number_is_not_assumed_to_match_tool():
    program = """T6M6
G0G90G54
G43H05Z1.
G1Z-.1F10.
G41D07X1.
G40
"""
    result = analyze_program(program, "mismatch.nc")
    codes = {w.code for w in result.warnings}
    assert "H_TOOL_MISMATCH" in codes
    assert "D_TOOL_MISMATCH" not in codes


def test_tool_used_but_missing_from_program_declaration_block_is_flagged():
    program = """(T1 1/2 ENDMILL H1)
(T2 1/4 DRILL H2)
T3M6
G54
G43H3Z1.
G81Z-.1R.1
G80
"""
    result = analyze_program(program, "declared.nc")
    warning = next(w for w in result.warnings if w.code == "TOOL_NOT_DECLARED")
    assert warning.tool_number == 3


def test_final_loaded_tool_without_machining_is_info():
    program = """T1M6
G0G90G54
G43H01Z1.
G1Z-.1
X1.
T2M6
M30
"""
    result = analyze_program(program, "final.nc")
    warnings = [w for w in result.warnings if w.code == "TOOL_LOADED_NO_MACHINING"]
    assert len(warnings) == 1
    assert warnings[0].tool_number == 2
