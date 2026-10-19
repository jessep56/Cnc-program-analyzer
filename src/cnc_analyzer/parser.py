from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from .fileio import normalize_program_text
from .models import (
    AnalysisResult,
    ProgramToolDeclaration,
    SequenceRecord,
    ToolChange,
    ToolSummary,
    WarningItem,
)

WORD_RE = re.compile(r"([A-Z])([+-]?(?:\d+(?:\.\d*)?|\.\d+))", re.I)
PAREN_COMMENT_RE = re.compile(r"\(([^)]*)\)")
PROGRAM_RE = re.compile(r"(?:^|\s)O(\d{1,8})(?:\s|$|\()", re.I)
TOOL_DECL_RE = re.compile(r"^\s*T\s*(\d+)\b(.*)$", re.I)
REGISTER_RE = re.compile(r"\b([HD])\s*(\d+(?:\.\d+)?)\b", re.I)

CANNED_CYCLES = {73, 74, 76, 81, 82, 83, 84, 85, 86, 87, 88, 89}
CYCLE_NAMES = {
    73: "High-speed peck drilling",
    74: "Left-hand tapping",
    76: "Fine boring",
    81: "Drilling / spot drilling",
    82: "Drilling with dwell",
    83: "Peck drilling",
    84: "Tapping",
    85: "Boring / reaming",
    86: "Boring",
    87: "Back boring",
    88: "Boring with dwell",
    89: "Boring with dwell",
}

TOOL_DESCRIPTION_KEYWORDS = (
    "DRILL", "REAM", "REAMER", "ENDMILL", "END MILL", " EM", "MILL", "TAP",
    "SPOT", "CHAMFER", "COUNTERSINK", "C'SINK", "CSINK", "CUTTER", "CARBIDE",
    "JOBBER", "INSERT", "BALL", "BULL", "DOVETAIL", "KEYSEAT", "FORM TOOL",
    "CENTER DRILL",
)

FEATURE_PREFIXES = (
    "MILL", "DRILL", "REAM", "TAP", "BORE", "COUNTERBORE", "SPOT", "SPOTDRILL",
    "ROUGH", "FINISH", "PROFILE", "CONTOUR", "POCKET", "CHAMFER", "THREAD",
)
SETUP_NOTE_KEYWORDS = (
    "ADJUST", "INSPECT", "CHECK", "VERIFY", "GRIND", "CLEARANCE", "IMPORTANT",
    "DROP", "RAISE", "LOWER", "OFFSET", "LOC", "MEASURE",
)
METADATA_PREFIXES = (
    "UPDATED", "UPDATE ", "REV ", "REVISION", "DATE ", "CUSTOMER", "PART ",
    "PROGRAM ", "CHRISTIE ", "DATEX ", "ROTATED FOR",
)


def _operation_for_cycle(cycle: int, description: str, feature: str = "") -> str:
    upper = f"{description} {feature}".upper()
    if "REAM" in upper:
        return "Reaming"
    if "SPOT" in upper or "CENTER DRILL" in upper:
        return "Spot drilling"
    if "TAP" in upper:
        return "Tapping"
    if "COUNTERBORE" in upper:
        return "Counterboring"
    if "BORE" in upper or "BORING" in upper:
        return "Boring"
    if "DRILL" in upper or "JOBBER" in upper:
        return "Peck drilling" if cycle in {73, 83} else "Drilling"
    return CYCLE_NAMES.get(cycle, "Canned cycle")


def _ordered_unique(values: Iterable[float]) -> list[float]:
    out: list[float] = []
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _ordered_unique_str(values: Iterable[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        if value and value not in out:
            out.append(value)
    return out


def _fmt_register(prefix: str, value: Optional[float]) -> str:
    if value is None:
        return ""
    as_int = int(value)
    if abs(value - as_int) < 1e-9:
        return f"{prefix}{as_int:02d}"
    return f"{prefix}{value:g}"


def _clean_comment(comment: str) -> str:
    return re.sub(r"\s+", " ", comment.strip())


def _parse_tool_declaration(comment: str, line_number: int) -> ProgramToolDeclaration | None:
    """Parse header comments such as: T1 6MM ENDMILL H1 D1."""
    cleaned = _clean_comment(comment)
    match = TOOL_DECL_RE.match(cleaned)
    if not match:
        return None

    tool_number = int(match.group(1))
    remainder = match.group(2).strip()
    registers = REGISTER_RE.findall(remainder)
    has_tool_language = any(keyword in f" {remainder.upper()}" for keyword in TOOL_DESCRIPTION_KEYWORDS)
    if not registers and not has_tool_language:
        return None

    h_offsets: list[str] = []
    d_offsets: list[str] = []
    for prefix, value in registers:
        formatted = _fmt_register(prefix.upper(), float(value))
        (h_offsets if prefix.upper() == "H" else d_offsets).append(formatted)

    description = REGISTER_RE.sub(" ", remainder)
    description = re.sub(r"\s*,\s*", ", ", description)
    description = re.sub(r"\s+", " ", description).strip(" -,:;")

    return ProgramToolDeclaration(
        tool_number=tool_number,
        description=description,
        h_offsets=_ordered_unique_str(h_offsets),
        d_offsets=_ordered_unique_str(d_offsets),
        line_number=line_number,
    )


def _is_context_tool_description(comment: str) -> bool:
    upper = f" {_clean_comment(comment).upper()}"
    if not upper.strip():
        return False
    if any(upper.strip().startswith(prefix) for prefix in FEATURE_PREFIXES):
        # Action comments such as MILL FRONT EDGE and BORE WALL CORNER describe the feature,
        # not the physical cutter.
        return False
    return any(keyword in upper for keyword in TOOL_DESCRIPTION_KEYWORDS)


def _is_feature_comment(comment: str) -> bool:
    upper = _clean_comment(comment).upper()
    return any(upper.startswith(prefix) for prefix in FEATURE_PREFIXES)


def _is_metadata_comment(comment: str) -> bool:
    upper = _clean_comment(comment).upper()
    return any(upper.startswith(prefix) for prefix in METADATA_PREFIXES)


def _is_setup_note(comment: str) -> bool:
    upper = _clean_comment(comment).upper()
    if any(keyword in upper for keyword in SETUP_NOTE_KEYWORDS):
        return True
    # Keep a date attached to an adjustment/revision note, but avoid turning every date
    # in a program header into a process-sheet note.
    return bool(re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", upper))


def _extract_words(code: str) -> list[tuple[str, float]]:
    return [(letter.upper(), float(value)) for letter, value in WORD_RE.findall(code.upper())]


def _extract_work_offset(words: list[tuple[str, float]]) -> Optional[str]:
    for index, (letter, value) in enumerate(words):
        if letter != "G":
            continue
        if 54 <= value <= 59 and float(value).is_integer():
            return f"G{int(value)}"
        if abs(value - 54.1) < 1e-9:
            p_value = None
            for next_letter, next_value in words[index + 1:]:
                if next_letter == "P":
                    p_value = int(next_value) if float(next_value).is_integer() else next_value
                    break
                if next_letter == "G":
                    break
            if p_value is not None:
                return f"G54.1 P{p_value}"
            return "G54.1"
    return None


def _axis_present(words: list[tuple[str, float]]) -> bool:
    return any(letter in {"X", "Y", "Z", "A", "B", "C"} for letter, _ in words)


def _xy_present(words: list[tuple[str, float]]) -> bool:
    return any(letter in {"X", "Y"} for letter, _ in words)


def _value_for(words: list[tuple[str, float]], letter: str) -> Optional[float]:
    for token_letter, value in reversed(words):
        if token_letter == letter:
            return value
    return None


def _g_values(words: list[tuple[str, float]]) -> list[float]:
    return [value for letter, value in words if letter == "G"]


def _m_values(words: list[tuple[str, float]]) -> list[float]:
    return [value for letter, value in words if letter == "M"]


def _finalize_sequence(seq: Optional[SequenceRecord], sequences: list[SequenceRecord], end_line: int) -> None:
    if seq is None:
        return
    seq.end_line = max(seq.start_line, end_line)
    if seq.count_basis == "compensated passes":
        seq.quantity = seq.comp_engagements
    elif seq.count_basis == "cutting motion blocks":
        seq.quantity = seq.cutting_blocks
    if seq.quantity > 0 or seq.cutting_blocks > 0 or seq.comp_engagements > 0:
        sequences.append(seq)


def _program_name(lines: list[str], filename: str) -> str:
    for raw in lines[:80]:
        cleaned = PAREN_COMMENT_RE.sub(" ", raw)
        match = PROGRAM_RE.search(cleaned)
        if match:
            return f"O{match.group(1)}"
    return Path(filename).stem


def _collect_declarations(lines: list[str]) -> list[ProgramToolDeclaration]:
    declarations: dict[int, ProgramToolDeclaration] = {}
    for line_number, raw_line in enumerate(lines, start=1):
        for comment in PAREN_COMMENT_RE.findall(raw_line):
            declaration = _parse_tool_declaration(comment, line_number)
            if declaration:
                declarations[declaration.tool_number] = declaration
    return list(declarations.values())


def analyze_program(text: str, filename: str = "program.nc") -> AnalysisResult:
    text = normalize_program_text(text)
    lines = text.splitlines()
    tool_changes: list[ToolChange] = []
    sequences: list[SequenceRecord] = []
    warnings: list[WarningItem] = []

    declared_tools = _collect_declarations(lines)
    declaration_map = {d.tool_number: d for d in declared_tools}
    has_declaration_block = len(declared_tools) >= 2

    current_tool: Optional[int] = None
    staged_tool: Optional[int] = None
    active_wcs = ""
    active_h: Optional[float] = None
    active_d: Optional[float] = None
    cutter_comp = ""
    motion_mode: Optional[int] = None
    active_cycle: Optional[int] = None
    active_cycle_seq: Optional[SequenceRecord] = None
    active_mill_seq: Optional[SequenceRecord] = None
    spindle_speed: Optional[float] = None
    feed_rate: Optional[float] = None

    tool_descriptions: dict[int, str] = {
        d.tool_number: d.description for d in declared_tools if d.description
    }
    tool_has_machining: defaultdict[int, bool] = defaultdict(bool)
    first_tool_change_line: dict[int, int] = {}
    pending_feature = ""
    pending_notes: list[str] = []

    program_name = _program_name(lines, filename)

    def finalize_mill(end_line: int) -> None:
        nonlocal active_mill_seq
        if active_mill_seq is not None:
            _finalize_sequence(active_mill_seq, sequences, end_line)
            active_mill_seq = None

    def finalize_cycle(end_line: int) -> None:
        nonlocal active_cycle, active_cycle_seq
        if active_cycle_seq is not None:
            _finalize_sequence(active_cycle_seq, sequences, end_line)
        active_cycle = None
        active_cycle_seq = None

    def start_mill_sequence(line_number: int) -> SequenceRecord:
        nonlocal active_mill_seq, pending_feature, pending_notes
        if active_mill_seq is None:
            active_mill_seq = SequenceRecord(
                tool_number=current_tool,
                description=tool_descriptions.get(current_tool or -1, ""),
                operation="Milling",
                feature=pending_feature,
                count_basis="cutting motion blocks",
                work_offset=active_wcs,
                h_offset=_fmt_register("H", active_h),
                d_offset=_fmt_register("D", active_d),
                cutter_comp=cutter_comp,
                spindle_speed=spindle_speed,
                start_line=line_number,
                notes=pending_notes.copy(),
            )
            pending_feature = ""
            pending_notes = []
        return active_mill_seq

    for line_number, raw_line in enumerate(lines, start=1):
        comments = [_clean_comment(c) for c in PAREN_COMMENT_RE.findall(raw_line) if _clean_comment(c)]
        code = PAREN_COMMENT_RE.sub(" ", raw_line)
        code = code.split(";", 1)[0].upper()
        words = _extract_words(code)
        if not words and not comments:
            continue

        g_values = _g_values(words)
        m_values = _m_values(words)

        if "#" in code or any(abs(g - 65) < 1e-9 for g in g_values) or any(int(m) in {98, 99} for m in m_values):
            warnings.append(WarningItem(
                severity="Warning",
                code="ADVANCED_CONTROL_FLOW",
                message="Macro/subprogram logic detected. Results may be incomplete because macro execution is not simulated.",
                line_number=line_number,
                tool_number=current_tool,
            ))

        for comment in comments:
            if _parse_tool_declaration(comment, line_number):
                continue

            # Only learn an ad-hoc tool description before that tool has started machining.
            # This preserves O4105-style comments while preventing later feature comments
            # (for example BORE WALL CORNER) from overwriting the physical tool description.
            if (
                current_tool is not None
                and not tool_descriptions.get(current_tool)
                and not tool_has_machining[current_tool]
                and _is_context_tool_description(comment)
            ):
                tool_descriptions[current_tool] = comment
                continue

            if _is_feature_comment(comment):
                if active_mill_seq is not None and active_mill_seq.cutting_blocks > 0:
                    finalize_mill(line_number - 1)
                if active_cycle_seq is not None:
                    finalize_cycle(line_number - 1)
                pending_feature = comment
                continue

            if _is_metadata_comment(comment):
                continue

            if _is_setup_note(comment):
                # Date-only comments are kept only when they follow a meaningful note.
                if re.fullmatch(r"\d{1,2}/\d{1,2}/\d{2,4}", comment) and not pending_notes:
                    continue
                pending_notes.append(comment)

        new_wcs = _extract_work_offset(words)
        if new_wcs and new_wcs != active_wcs:
            if active_mill_seq is not None and active_mill_seq.cutting_blocks > 0:
                finalize_mill(line_number - 1)
            if active_cycle_seq is not None:
                finalize_cycle(line_number - 1)
            active_wcs = new_wcs

        s_value = _value_for(words, "S")
        if s_value is not None:
            spindle_speed = s_value
        f_value = _value_for(words, "F")
        if f_value is not None:
            feed_rate = f_value

        # Process words in block order so preloads and T/M6 combinations behave correctly.
        for letter, value in words:
            if letter == "T":
                staged_tool = int(value)
            elif letter == "M" and int(value) == 6:
                if staged_tool is None:
                    warnings.append(WarningItem(
                        severity="Error",
                        code="M6_WITHOUT_TOOL",
                        message="M6 encountered without a preceding/active T selection.",
                        line_number=line_number,
                        tool_number=current_tool,
                    ))
                    continue
                finalize_cycle(line_number - 1)
                finalize_mill(line_number - 1)
                current_tool = staged_tool
                staged_tool = None
                active_h = None
                active_d = None
                cutter_comp = ""
                motion_mode = None
                # Keep a feature heading found immediately before the tool change;
                # many shop programs label the upcoming operation before T/M6.
                pending_notes = []
                tool_changes.append(ToolChange(line_number=line_number, tool_number=current_tool))
                first_tool_change_line.setdefault(current_tool, line_number)

                if has_declaration_block and current_tool not in declaration_map:
                    warnings.append(WarningItem(
                        severity="Warning",
                        code="TOOL_NOT_DECLARED",
                        message=f"T{current_tool} is used in the program but is not listed in the program's tool declaration block.",
                        line_number=line_number,
                        tool_number=current_tool,
                    ))

        h_value = _value_for(words, "H")
        if h_value is not None:
            active_h = h_value
            if current_tool is not None:
                actual_h = _fmt_register("H", h_value)
                declared = declaration_map.get(current_tool)
                if declared and declared.h_offsets and actual_h not in declared.h_offsets:
                    warnings.append(WarningItem(
                        severity="Warning",
                        code="H_DECLARATION_MISMATCH",
                        message=(
                            f"T{current_tool} uses {actual_h}, but its program tool declaration lists "
                            f"{', '.join(declared.h_offsets)}. Verify the length-offset register."
                        ),
                        line_number=line_number,
                        tool_number=current_tool,
                    ))
                elif not declared and not has_declaration_block and int(h_value) != current_tool:
                    warnings.append(WarningItem(
                        severity="Warning",
                        code="H_TOOL_MISMATCH",
                        message=f"Current tool is T{current_tool}, but length offset H{int(h_value):02d} is used. Verify this is intentional.",
                        line_number=line_number,
                        tool_number=current_tool,
                    ))

        d_value = _value_for(words, "D")
        if d_value is not None:
            active_d = d_value

        if any(int(g) == 40 for g in g_values if float(g).is_integer()):
            cutter_comp = ""
        for g in g_values:
            if abs(g - 41) < 1e-9 or abs(g - 42) < 1e-9:
                cutter_comp = f"G{int(g)}"
                if active_d is None:
                    warnings.append(WarningItem(
                        severity="Warning",
                        code="CUTTER_COMP_NO_D",
                        message=f"{cutter_comp} is active but no D register has been detected.",
                        line_number=line_number,
                        tool_number=current_tool,
                    ))
                seq = start_mill_sequence(line_number)
                seq.operation = "Contour milling"
                seq.count_basis = "compensated passes"
                seq.comp_engagements += 1
                seq.cutter_comp = cutter_comp
                seq.d_offset = _fmt_register("D", active_d)

        # Motion group changes terminate an active canned cycle for analysis purposes.
        explicit_motion = None
        for g in g_values:
            if float(g).is_integer() and int(g) in {0, 1, 2, 3}:
                explicit_motion = int(g)
        if explicit_motion is not None:
            motion_mode = explicit_motion
            if active_cycle is not None:
                finalize_cycle(line_number - 1)

        if any(float(g).is_integer() and int(g) == 80 for g in g_values):
            if active_cycle is not None:
                finalize_cycle(line_number - 1)

        cycle_in_block = None
        for g in g_values:
            if float(g).is_integer() and int(g) in CANNED_CYCLES:
                cycle_in_block = int(g)

        if cycle_in_block is not None:
            if active_cycle_seq is not None:
                finalize_cycle(line_number - 1)
            active_cycle = cycle_in_block
            feature = pending_feature
            active_cycle_seq = SequenceRecord(
                tool_number=current_tool,
                description=tool_descriptions.get(current_tool or -1, ""),
                operation=_operation_for_cycle(cycle_in_block, tool_descriptions.get(current_tool or -1, ""), feature),
                feature=feature,
                cycle=f"G{cycle_in_block}",
                quantity=1,
                count_basis="cycle locations",
                work_offset=active_wcs,
                h_offset=_fmt_register("H", active_h),
                spindle_speed=spindle_speed,
                start_line=line_number,
                notes=pending_notes.copy(),
            )
            pending_feature = ""
            pending_notes = []
            if current_tool is not None:
                tool_has_machining[current_tool] = True
            z = _value_for(words, "Z")
            r = _value_for(words, "R")
            q = _value_for(words, "Q")
            f = _value_for(words, "F")
            if z is not None:
                active_cycle_seq.z_values.append(z)
            if r is not None:
                active_cycle_seq.r_values.append(r)
            if q is not None:
                active_cycle_seq.q_values.append(q)
            if f is not None:
                active_cycle_seq.feed_values.append(f)
            continue

        if active_cycle is not None and active_cycle_seq is not None:
            if _xy_present(words):
                active_cycle_seq.quantity += 1
                active_cycle_seq.end_line = line_number
                if current_tool is not None:
                    tool_has_machining[current_tool] = True
            for letter, attr in (("Z", "z_values"), ("R", "r_values"), ("Q", "q_values"), ("F", "feed_values")):
                value = _value_for(words, letter)
                if value is not None:
                    getattr(active_cycle_seq, attr).append(value)
            continue

        # Milling / cutting motion. Modal G1/G2/G3 is respected.
        if current_tool is not None and motion_mode in {1, 2, 3} and _axis_present(words):
            seq = start_mill_sequence(line_number)
            seq.cutting_blocks += 1
            seq.end_line = line_number
            seq.work_offset = active_wcs
            seq.h_offset = _fmt_register("H", active_h)
            seq.spindle_speed = spindle_speed
            if cutter_comp:
                seq.cutter_comp = cutter_comp
                seq.d_offset = _fmt_register("D", active_d)
            if feed_rate is not None:
                seq.feed_values.append(feed_rate)
            z = _value_for(words, "Z")
            if z is not None:
                seq.z_values.append(z)
            tool_has_machining[current_tool] = True

    finalize_cycle(len(lines))
    finalize_mill(len(lines))

    for index, seq in enumerate(sequences, start=1):
        seq.sequence_number = index
        if not seq.description and seq.tool_number is not None:
            seq.description = tool_descriptions.get(seq.tool_number, "")
        seq.feed_values = _ordered_unique(seq.feed_values)
        seq.z_values = _ordered_unique(seq.z_values)
        seq.r_values = _ordered_unique(seq.r_values)
        seq.q_values = _ordered_unique(seq.q_values)
        seq.notes = _ordered_unique_str(seq.notes)

    changed_tools = {tc.tool_number for tc in tool_changes}
    machined_tools = {seq.tool_number for seq in sequences if seq.tool_number is not None}

    for tool_number in sorted(machined_tools):
        if not tool_descriptions.get(tool_number):
            warnings.append(WarningItem(
                severity="Info",
                code="TOOL_DESCRIPTION_MISSING",
                message=f"No tool description was recognized in the CNC program for T{tool_number}. A job-packet Tool List can supply it.",
                tool_number=tool_number,
                line_number=min(
                    [s.start_line for s in sequences if s.tool_number == tool_number]
                    or [first_tool_change_line.get(tool_number, 0)]
                ) or None,
            ))

    if has_declaration_block:
        for declaration in declared_tools:
            if declaration.tool_number not in changed_tools and declaration.tool_number not in machined_tools:
                warnings.append(WarningItem(
                    severity="Info",
                    code="DECLARED_TOOL_UNUSED",
                    message=f"T{declaration.tool_number} is listed in the program tool declaration block but is not used in detected machining.",
                    line_number=declaration.line_number,
                    tool_number=declaration.tool_number,
                ))

    if tool_changes:
        last_change = tool_changes[-1]
        later_sequences = [
            s for s in sequences
            if s.tool_number == last_change.tool_number and s.start_line >= last_change.line_number
        ]
        if not later_sequences:
            warnings.append(WarningItem(
                severity="Info",
                code="TOOL_LOADED_NO_MACHINING",
                message=f"T{last_change.tool_number} is loaded near the end of the program but no machining is detected afterward.",
                line_number=last_change.line_number,
                tool_number=last_change.tool_number,
            ))

    tool_summary_map: dict[int, ToolSummary] = {}
    for tool in sorted(changed_tools | machined_tools):
        summary = ToolSummary(tool_number=tool, description=tool_descriptions.get(tool, ""))
        summary.tool_changes = sum(1 for tc in tool_changes if tc.tool_number == tool)
        for seq in sequences:
            if seq.tool_number != tool:
                continue
            summary.sequences += 1
            if seq.count_basis == "cycle locations":
                summary.cycle_locations += seq.quantity
            if seq.work_offset and seq.work_offset not in summary.work_offsets:
                summary.work_offsets.append(seq.work_offset)
            if seq.h_offset and seq.h_offset not in summary.h_offsets:
                summary.h_offsets.append(seq.h_offset)
            if seq.d_offset and seq.d_offset not in summary.d_offsets:
                summary.d_offsets.append(seq.d_offset)
            if seq.operation and seq.operation not in summary.operations:
                summary.operations.append(seq.operation)
            if seq.feature and seq.feature not in summary.features:
                summary.features.append(seq.feature)
        tool_summary_map[tool] = summary

    seen = set()
    deduped: list[WarningItem] = []
    for warning in warnings:
        key = (warning.severity, warning.code, warning.message, warning.line_number, warning.tool_number)
        if key not in seen:
            seen.add(key)
            deduped.append(warning)

    return AnalysisResult(
        filename=filename,
        program_name=program_name,
        line_count=len(lines),
        tool_changes=tool_changes,
        sequences=sequences,
        tool_summaries=list(tool_summary_map.values()),
        warnings=deduped,
        declared_tools=declared_tools,
    )
