from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cnc_analyzer.context import contextual_warnings, merge_tool_lists
from cnc_analyzer.excel_exporter import build_excel_report
from cnc_analyzer.fileio import read_program_file
from cnc_analyzer.job_packet import read_job_packet_bytes
from cnc_analyzer.models import JobInfo, JobPacketData
from cnc_analyzer.parser import analyze_program
from cnc_analyzer.reporting import process_sheet_rows, warning_rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze a text-based CNC program.")
    parser.add_argument("file", type=Path, help="CNC program path")
    parser.add_argument("--job-packet", type=Path, help="Optional .xls/.xlsx/.xlsm job packet")
    parser.add_argument("--excel", type=Path, help="Optional output .xlsx path")
    args = parser.parse_args()

    try:
        text = read_program_file(args.file)
        result = analyze_program(text, args.file.name)
        packet = JobPacketData()
        if args.job_packet:
            packet = read_job_packet_bytes(args.job_packet.read_bytes(), args.job_packet.name)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    job_info = packet.job_info if args.job_packet else JobInfo()
    if not job_info.program_number:
        job_info.program_number = result.program_name
    tools = merge_tool_lists(result, packet.tools)
    warnings = contextual_warnings(result, tools, job_info, packet_supplied=bool(args.job_packet))

    print(f"Program: {result.program_name}")
    print(f"Lines: {result.line_count}")
    print(f"Tool changes: {len(result.tool_changes)}")
    print(f"Unique tools: {result.unique_tools}")
    print(f"Process steps: {len(result.sequences)}")
    print(f"Canned-cycle locations: {result.canned_cycle_locations}")
    print()

    for row in process_sheet_rows(result, tools):
        print(
            f"{row['Step']:>2}  {row['Tool']:<4}  {str(row['Process / Feature']):<32} "
            f"qty={str(row['Qty']):<3}  WCS={str(row['WCS']):<10} "
            f"offsets={str(row['Offsets / Comp']):<14} lines={row['Lines']}"
        )

    if warnings:
        print("\nWarnings / notices:")
        for warning in warning_rows(warnings):
            print(f"- [{warning['Severity']}] line {warning['Line'] or '-'} {warning['Code']}: {warning['Message']}")

    if args.excel:
        output = args.excel
        if output.suffix.lower() != ".xlsx":
            output = output.with_suffix(".xlsx")
        output.write_bytes(build_excel_report(result, job_info=job_info, tools=tools, warnings=warnings))
        print(f"\nExcel report: {output}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
