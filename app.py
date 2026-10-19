from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pandas as pd
import streamlit as st

from cnc_analyzer.context import contextual_warnings, merge_tool_lists
from cnc_analyzer.excel_exporter import build_excel_report
from cnc_analyzer.fileio import decode_program_bytes
from cnc_analyzer.job_packet import read_job_packet_bytes
from cnc_analyzer.models import JobInfo, JobPacketData, ToolListEntry
from cnc_analyzer.parser import analyze_program
from cnc_analyzer.reporting import (
    process_sheet_rows,
    technical_sequence_rows,
    tool_rows,
    warning_rows,
)

st.set_page_config(
    page_title="CNC Program Analyzer",
    page_icon="⚙️",
    layout="wide",
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.3rem; padding-bottom: 2rem; }
        .subtle { color: #667085; font-size: 0.95rem; }
        .hero { padding: 0.5rem 0 0.2rem 0; }
        .hero h1 { margin-bottom: 0.15rem; }
    </style>
    """,
    unsafe_allow_html=True,
)

st.markdown(
    """
    <div class="hero">
      <h1>⚙️ CNC Program Analyzer</h1>
      <div class="subtle">Analyze the CNC program, compare it with an optional job packet Tool List, and export an iPad-friendly process sheet.</div>
    </div>
    """,
    unsafe_allow_html=True,
)

upload_col, packet_col = st.columns(2)
with upload_col:
    uploaded = st.file_uploader(
        "CNC program (required)",
        type=None,
        help="Text-based CNC files such as .NC, .TXT, .CNC, .TAP, .EIA, or extensionless files.",
    )
with packet_col:
    packet_upload = st.file_uploader(
        "Job packet (optional)",
        type=["xls", "xlsx", "xlsm"],
        help="Imports job information and the Tool List. The original workbook is never modified.",
    )

with st.expander("What this version understands", expanded=False):
    st.markdown(
        """
        - Tool selection and M6 tool changes, including next-tool preloading
        - Program tool-declaration blocks such as `(T1 6MM ENDMILL H1 D1)`
        - Separate physical **tool descriptions** from machining **process/feature comments**
        - G54–G59 and extended G54.1 P work offsets
        - G43/H length offsets and G41/G42/D cutter compensation
        - Common canned cycles including G73, G81–G89 and hole/location counts
        - Modal G1/G2/G3 milling moves and compensated pass counts
        - Source line ranges with legacy DNC line-ending normalization
        - Optional `.xls`, `.xlsx`, or `.xlsm` job-packet Tool List import
        - Tool List / program validation, including undeclared tools and explicit D-register checks

        The parser is strongest on Fanuc-style / ISO G-code. Macro/subprogram logic is flagged for manual review rather than simulated.
        """
    )

if uploaded is None:
    st.info("Upload a CNC program to begin. Analysis is read-only and nothing is sent to a machine.")
    st.stop()

try:
    text = decode_program_bytes(uploaded.getvalue())
    result = analyze_program(text, uploaded.name)
except Exception as exc:
    st.error(f"Could not analyze this CNC file: {exc}")
    st.stop()

packet = JobPacketData()
packet_supplied = packet_upload is not None
if packet_upload is not None:
    try:
        packet = read_job_packet_bytes(packet_upload.getvalue(), packet_upload.name)
        st.success(f"Imported job packet: {packet_upload.name} · {len(packet.tools)} Tool List item(s)")
    except Exception as exc:
        st.warning(f"The CNC program was analyzed, but the job packet could not be read: {exc}")
        packet = JobPacketData(source_filename=packet_upload.name)

base_info = packet.job_info
if not base_info.program_number:
    base_info.program_number = result.program_name

context_key = f"{uploaded.name}|{packet_upload.name if packet_upload else 'no-packet'}"

with st.expander("Job information", expanded=True):
    c1, c2, c3, c4 = st.columns(4)
    customer = c1.text_input("Customer", value=base_info.customer, key=f"customer:{context_key}")
    part_number = c2.text_input("Part Number", value=base_info.part_number, key=f"partnum:{context_key}")
    part_name = c3.text_input("Part Name", value=base_info.part_name, key=f"partname:{context_key}")
    part_revision = c4.text_input("Part Revision", value=base_info.part_revision, key=f"partrev:{context_key}")

    c5, c6, c7 = st.columns(3)
    program_number = c5.text_input("Program Number", value=base_info.program_number or result.program_name, key=f"program:{context_key}")
    machine = c6.text_input("Machine", value=base_info.machine, key=f"machine:{context_key}")
    operation = c7.text_input("Operation", value=base_info.operation, key=f"operation:{context_key}")

    automation_notes = st.text_area(
        "Automation / Special Instructions (optional)",
        value=base_info.automation_notes,
        key=f"auto-notes:{context_key}",
        placeholder="Example: Cobot load position, unusual setup requirement, or other setup-only instruction.",
    )

job_info = JobInfo(
    customer=customer,
    part_number=part_number,
    part_name=part_name,
    part_revision=part_revision,
    program_number=program_number,
    machine=machine,
    operation=operation,
    automation_notes=automation_notes,
)

initial_tools = merge_tool_lists(result, packet.tools)
editor_rows = [{
    "Tool #": tool.tool_number,
    "Description": tool.description,
    "Holder Type": tool.holder_type,
    "Projection": tool.projection,
    "H Measure": tool.h_measure,
    "D Value": tool.d_value,
    "Special Instructions": tool.special_instructions,
} for tool in initial_tools]

with st.expander("Editable Tool List", expanded=False):
    st.caption(
        "This is the source of truth for the exported Process Sheet description column. "
        "The Excel Process Sheet uses formulas, so later Tool List description changes update automatically."
    )
    edited_df = st.data_editor(
        pd.DataFrame(editor_rows, columns=[
            "Tool #", "Description", "Holder Type", "Projection", "H Measure", "D Value", "Special Instructions"
        ]),
        width="stretch",
        hide_index=True,
        num_rows="dynamic",
        key=f"tool-editor:{context_key}",
    )

edited_tools: list[ToolListEntry] = []
for row in edited_df.to_dict("records"):
    raw_tool = row.get("Tool #")
    if pd.isna(raw_tool) or str(raw_tool).strip() == "":
        continue
    try:
        tool_number = int(float(raw_tool))
    except (TypeError, ValueError):
        continue

    def clean(value) -> str:
        return "" if pd.isna(value) else str(value).strip()

    original = next((t for t in packet.tools if t.tool_number == tool_number), None)
    edited_tools.append(ToolListEntry(
        tool_number=tool_number,
        description=clean(row.get("Description")),
        holder_type=clean(row.get("Holder Type")),
        projection=clean(row.get("Projection")),
        h_measure=clean(row.get("H Measure")),
        d_value=clean(row.get("D Value")),
        special_instructions=clean(row.get("Special Instructions")),
        source="Job Packet" if original else "Program / Manual",
    ))

warnings = contextual_warnings(
    result,
    edited_tools,
    job_info,
    packet_supplied=packet_supplied,
)

metrics = st.columns(5)
metrics[0].metric("Program", result.program_name)
metrics[1].metric("Tool changes", len(result.tool_changes))
metrics[2].metric("Unique tools", result.unique_tools)
metrics[3].metric("Process steps", len(result.sequences))
metrics[4].metric("Cycle locations", result.canned_cycle_locations)

warning_count = sum(1 for w in warnings if w.severity in {"Warning", "Error"})
if warning_count:
    st.warning(f"{warning_count} warning/error item(s) deserve review. Informational notices are listed separately.")
else:
    st.success("No warning/error conditions were detected with the current program and Tool List context.")

excel_bytes = build_excel_report(
    result,
    job_info=job_info,
    tools=edited_tools,
    warnings=warnings,
)
report_name = f"{Path(uploaded.name).stem}_process_sheet.xlsx"
st.download_button(
    "⬇️ Export Process Sheet workbook",
    data=excel_bytes,
    file_name=report_name,
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    width="content",
)

process_tab, tool_tab, warning_tab, technical_tab, summary_tab, source_tab = st.tabs([
    "Process Sheet", "Tool List", "Warnings", "Technical Details", "Tool Summary", "Source Preview"
])

with process_tab:
    rows = process_sheet_rows(result, edited_tools)
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("No machining sequences were detected.")

with tool_tab:
    if edited_tools:
        st.dataframe(pd.DataFrame([{
            "Tool #": t.tool_number,
            "Description": t.description,
            "Holder Type": t.holder_type,
            "Projection": t.projection,
            "H Measure": t.h_measure,
            "D Value": t.d_value,
            "Special Instructions": t.special_instructions,
        } for t in edited_tools]), width="stretch", hide_index=True)
    else:
        st.info("No tools were identified.")

with warning_tab:
    rows = warning_rows(warnings)
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.success("No warnings or informational notices were generated.")

with technical_tab:
    rows = technical_sequence_rows(result)
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("No machining sequences were detected.")

with summary_tab:
    rows = tool_rows(result, edited_tools)
    if rows:
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    else:
        st.info("No tool changes were detected.")

with source_tab:
    show_lines = st.checkbox("Show line numbers", value=True)
    preview_lines = text.splitlines()
    if show_lines:
        preview = "\n".join(f"{i:>5}  {line}" for i, line in enumerate(preview_lines, start=1))
    else:
        preview = text
    st.code(preview, language=None)

st.caption(
    "Verification aid only. Always verify offsets, tooling, workholding, machine state, and program behavior before running production equipment."
)
