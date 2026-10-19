from __future__ import annotations

import re
from dataclasses import replace
from difflib import SequenceMatcher

from .models import AnalysisResult, JobInfo, ToolListEntry, WarningItem

D_REGISTER_RE = re.compile(r"\bD\s*(\d+)\b", re.I)


def merge_tool_lists(result: AnalysisResult, packet_tools: list[ToolListEntry] | None = None) -> list[ToolListEntry]:
    """Merge tool sources with the job-packet Tool List as the source of truth."""
    merged: dict[int, ToolListEntry] = {}

    declarations = {d.tool_number: d for d in result.declared_tools}
    summaries = {t.tool_number: t for t in result.tool_summaries}

    all_tool_numbers = set(summaries) | set(declarations)
    if packet_tools:
        all_tool_numbers |= {t.tool_number for t in packet_tools}

    for tool_number in sorted(all_tool_numbers):
        declaration = declarations.get(tool_number)
        summary = summaries.get(tool_number)
        description = ""
        if declaration and declaration.description:
            description = declaration.description
        elif summary and summary.description:
            description = summary.description
        merged[tool_number] = ToolListEntry(
            tool_number=tool_number,
            description=description,
            source="Program" if description else "",
        )

    # Packet values intentionally win. If a setter changes a tool later, editing the
    # Tool List tab updates the Process Sheet formula without regenerating the report.
    for packet_tool in packet_tools or []:
        merged[packet_tool.tool_number] = replace(packet_tool)

    return [merged[number] for number in sorted(merged)]


def _allowed_d_registers(text: str) -> set[str]:
    return {f"D{int(value):02d}" for value in D_REGISTER_RE.findall(text or "")}


def _normalize_description(text: str) -> str:
    value = text.upper()
    value = value.replace('"', " IN ")
    value = re.sub(r"[^A-Z0-9.]+", " ", value)
    return " ".join(value.split())


def _description_similarity(a: str, b: str) -> float:
    aa = _normalize_description(a)
    bb = _normalize_description(b)
    if not aa or not bb:
        return 1.0
    return SequenceMatcher(None, aa, bb).ratio()


def contextual_warnings(
    result: AnalysisResult,
    tools: list[ToolListEntry] | None = None,
    job_info: JobInfo | None = None,
    *,
    packet_supplied: bool = False,
) -> list[WarningItem]:
    tools = tools or []
    tool_map = {tool.tool_number: tool for tool in tools}
    warnings: list[WarningItem] = []

    # Once the Tool List supplies the description, a missing description in the CNC
    # source is not a problem for the generated process sheet.
    for warning in result.warnings:
        if warning.code == "TOOL_DESCRIPTION_MISSING":
            entry = tool_map.get(warning.tool_number or -1)
            if entry and entry.description:
                continue
        warnings.append(warning)

    used_tools = {seq.tool_number for seq in result.sequences if seq.tool_number is not None}

    if packet_supplied:
        for tool_number in sorted(used_tools):
            entry = tool_map.get(tool_number)
            if not entry:
                warnings.append(WarningItem(
                    severity="Warning",
                    code="TOOL_MISSING_FROM_TOOL_LIST",
                    message=f"T{tool_number} is used in the CNC program but is missing from the job packet Tool List.",
                    tool_number=tool_number,
                ))
            elif not entry.description:
                warnings.append(WarningItem(
                    severity="Warning",
                    code="TOOL_LIST_DESCRIPTION_BLANK",
                    message=f"T{tool_number} is used in the CNC program but its Tool List description is blank.",
                    tool_number=tool_number,
                ))

        for tool in tools:
            if tool.source == "Job Packet" and tool.tool_number not in used_tools:
                warnings.append(WarningItem(
                    severity="Info",
                    code="TOOL_LIST_TOOL_UNUSED",
                    message=f"T{tool.tool_number} is listed on the job packet Tool List but is not used in detected machining.",
                    tool_number=tool.tool_number,
                ))

    # Without a job packet, a program declaration is the best available D-register
    # reference. With a packet, the Tool List takes precedence because shops may
    # intentionally use alternate comps (for example T1 with both D1 and D11).
    if not packet_supplied:
        declaration_map = {d.tool_number: d for d in result.declared_tools}
        for seq in result.sequences:
            if seq.tool_number is None or not seq.d_offset:
                continue
            declaration = declaration_map.get(seq.tool_number)
            if declaration and declaration.d_offsets and seq.d_offset not in declaration.d_offsets:
                warnings.append(WarningItem(
                    severity="Warning",
                    code="D_DECLARATION_MISMATCH",
                    message=(
                        f"T{seq.tool_number} uses {seq.d_offset}, but its program tool declaration lists "
                        f"{', '.join(declaration.d_offsets)}. Verify the cutter compensation register."
                    ),
                    line_number=seq.start_line,
                    tool_number=seq.tool_number,
                ))

    # D registers are not required to match the T number. Validate only when the
    # actual Tool List explicitly states allowed D register(s).
    for seq in result.sequences:
        if seq.tool_number is None or not seq.d_offset:
            continue
        entry = tool_map.get(seq.tool_number)
        if not entry:
            continue
        d_source = " ".join(value for value in (entry.d_value, entry.special_instructions) if value)
        if not d_source:
            continue
        allowed = _allowed_d_registers(d_source)
        if allowed and seq.d_offset not in allowed:
            warnings.append(WarningItem(
                severity="Warning",
                code="D_TOOL_LIST_MISMATCH",
                message=(
                    f"T{seq.tool_number} uses {seq.d_offset}, but the Tool List states "
                    f"{d_source}. Verify the cutter compensation register."
                ),
                line_number=seq.start_line,
                tool_number=seq.tool_number,
            ))

    # Surface only strong description conflicts. Program headers are often shorthand,
    # so mild wording differences are intentionally ignored.
    declaration_map = {d.tool_number: d for d in result.declared_tools}
    if packet_supplied:
        for tool_number, declaration in declaration_map.items():
            entry = tool_map.get(tool_number)
            if not entry or not entry.description or not declaration.description:
                continue
            if _description_similarity(entry.description, declaration.description) < 0.28:
                warnings.append(WarningItem(
                    severity="Info",
                    code="TOOL_DESCRIPTION_CONFLICT",
                    message=(
                        f"T{tool_number} has different descriptions in the program header "
                        f"('{declaration.description}') and Tool List ('{entry.description}'). Review if needed."
                    ),
                    line_number=declaration.line_number,
                    tool_number=tool_number,
                ))

    if job_info and job_info.program_number:
        packet_program = re.sub(r"\s+", "", job_info.program_number.upper())
        parsed_program = re.sub(r"\s+", "", result.program_name.upper())
        if packet_program and parsed_program and packet_program != parsed_program:
            warnings.append(WarningItem(
                severity="Warning",
                code="PROGRAM_NUMBER_MISMATCH",
                message=(
                    f"Job information lists program '{job_info.program_number}', but the CNC file identifies as "
                    f"'{result.program_name}'."
                ),
            ))

    seen: set[tuple[object, ...]] = set()
    deduped: list[WarningItem] = []
    for warning in warnings:
        key = (warning.severity, warning.code, warning.message, warning.line_number, warning.tool_number)
        if key not in seen:
            seen.add(key)
            deduped.append(warning)
    return deduped
