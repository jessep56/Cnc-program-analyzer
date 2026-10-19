from __future__ import annotations

from .models import AnalysisResult, SequenceRecord, ToolListEntry, WarningItem


def _offsets_comp(seq: SequenceRecord) -> str:
    parts = [value for value in (seq.h_offset, seq.d_offset, seq.cutter_comp) if value]
    return " / ".join(parts)


def _format_values(values: list[float]) -> str:
    return ", ".join(f"{value:g}" for value in values)


def _display_comment(text: str) -> str:
    text = " ".join((text or "").split())
    if text and text == text.upper():
        return text.title()
    return text


def _process_feature(seq: SequenceRecord) -> str:
    feature = _display_comment(seq.feature)
    if not feature:
        return seq.operation
    upper = feature.upper()
    if upper in {"ROUGH PASS", "FINISH PASS", "ROUGH", "FINISH"}:
        return f"{seq.operation} — {feature}"
    return feature


def _setup_quantity(seq: SequenceRecord) -> int | str:
    # Hole/location counts and compensated pass counts are meaningful to setup.
    # Raw G1/G2/G3 block counts are parser detail, not a useful process-sheet quantity.
    if seq.count_basis in {"cycle locations", "compensated passes"}:
        return seq.quantity
    return ""


def _tool_description_map(tools: list[ToolListEntry] | None) -> dict[int, str]:
    return {tool.tool_number: tool.description for tool in (tools or [])}


def process_sheet_rows(
    result: AnalysisResult,
    tools: list[ToolListEntry] | None = None,
) -> list[dict[str, object]]:
    """Compact setup/operator view designed for iPad and printed job packets."""
    descriptions = _tool_description_map(tools)
    rows: list[dict[str, object]] = []
    for seq in result.sequences:
        rows.append({
            "Step": seq.sequence_number,
            "Tool": f"T{seq.tool_number}" if seq.tool_number is not None else "",
            "Tool Description": descriptions.get(seq.tool_number or -1, seq.description),
            "Process / Feature": _process_feature(seq),
            "Qty": _setup_quantity(seq),
            "WCS": seq.work_offset,
            "Offsets / Comp": _offsets_comp(seq),
            "Lines": f"{seq.start_line}-{seq.end_line}",
            "Notes": "; ".join(seq.notes),
        })
    return rows


# Backward-compatible name for callers from v1.0.x.
def sequence_rows(result: AnalysisResult, tools: list[ToolListEntry] | None = None) -> list[dict[str, object]]:
    return process_sheet_rows(result, tools)


def technical_sequence_rows(result: AnalysisResult) -> list[dict[str, object]]:
    """Full parser detail retained for troubleshooting and validation."""
    rows: list[dict[str, object]] = []
    for seq in result.sequences:
        rows.append({
            "Step": seq.sequence_number,
            "Tool": f"T{seq.tool_number}" if seq.tool_number is not None else "",
            "Program Tool Description": seq.description,
            "Operation": seq.operation,
            "Feature": _display_comment(seq.feature),
            "Cycle": seq.cycle,
            "Qty / Passes": seq.quantity,
            "Count Basis": seq.count_basis,
            "WCS": seq.work_offset,
            "H Offset": seq.h_offset,
            "D Offset": seq.d_offset,
            "Cutter Comp": seq.cutter_comp,
            "RPM": int(seq.spindle_speed) if seq.spindle_speed is not None and float(seq.spindle_speed).is_integer() else (seq.spindle_speed or ""),
            "Feed(s)": _format_values(seq.feed_values),
            "Z Depth(s)": _format_values(seq.z_values),
            "R Plane(s)": _format_values(seq.r_values),
            "Q Peck(s)": _format_values(seq.q_values),
            "Lines": f"{seq.start_line}-{seq.end_line}",
            "Notes": "; ".join(seq.notes),
        })
    return rows


def tool_rows(
    result: AnalysisResult,
    tools: list[ToolListEntry] | None = None,
) -> list[dict[str, object]]:
    descriptions = _tool_description_map(tools)
    return [{
        "Tool": f"T{tool.tool_number}",
        "Description": descriptions.get(tool.tool_number, tool.description),
        "Tool Changes": tool.tool_changes,
        "Sequences": tool.sequences,
        "Cycle Locations": tool.cycle_locations,
        "Work Offsets": ", ".join(tool.work_offsets),
        "H Offsets": ", ".join(tool.h_offsets),
        "D Offsets": ", ".join(tool.d_offsets),
        "Operations": ", ".join(tool.operations),
        "Features": ", ".join(_display_comment(value) for value in tool.features),
    } for tool in result.tool_summaries]


def warning_rows(warnings: AnalysisResult | list[WarningItem]) -> list[dict[str, object]]:
    items = warnings.warnings if isinstance(warnings, AnalysisResult) else warnings
    return [{
        "Severity": warning.severity,
        "Code": warning.code,
        "Line": warning.line_number or "",
        "Tool": f"T{warning.tool_number}" if warning.tool_number is not None else "",
        "Message": warning.message,
    } for warning in items]
