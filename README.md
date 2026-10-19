# CNC Program Analyzer v1.1.0

Local CNC G-code analysis and process-sheet generation for setup verification.

This release is built around a simple workflow:

1. Drop in a text-based CNC program.
2. Optionally drop in the existing Excel job packet (`.xls`, `.xlsx`, or `.xlsm`).
3. Review/edit job information and the Tool List in the browser.
4. Review the generated process steps and warnings.
5. Export an iPad-friendly Excel workbook.

The application is read-only with respect to CNC programs and uploaded job packets. It creates a new report; it does not modify the originals.

## Major v1.1 changes

- Imports job information from the shop job packet when available:
  - Customer
  - Part number
  - Part name
  - Part revision
  - Program number
  - Machine
  - Operation
- Imports the job packet **Tool List**.
- Provides an editable Tool List in the browser before export.
- Generates a compact **Process Sheet** as the first Excel tab.
- Process Sheet `Tool Description` cells are formulas that look up the editable Tool List tab. If the physical tool assigned to a tool number changes later, editing the Tool List updates the Process Sheet automatically.
- Embeds the Chicago White Metal Casting logo in the generated workbook.
- Separates physical tool descriptions from program feature comments such as `MILL FRONT EDGE` or `BORE WALL CORNER`.
- Reads program tool-declaration blocks such as `(T1 6MM ENDMILL H1 D1)`.
- Flags tools used by the program but missing from a program declaration block.
- Validates D registers only when the Tool List explicitly states allowed D register(s); it no longer assumes `T7` must use `D7`.
- Normalizes unusual legacy DNC line endings so displayed source line numbers remain useful.
- Keeps technical parser data in separate troubleshooting tabs rather than crowding the setup view.

## Generated workbook

The export contains:

1. **Process Sheet** — primary setup/iPad view
2. **Tool List** — editable source of tool descriptions and tool metadata
3. **Warnings** — parser and job-packet validation findings
4. **Summary** — job and analysis overview
5. **Technical Details** — full parser detail
6. **Tool Summary** — tool-level usage summary

### Process Sheet columns

- Step
- Tool
- Tool Description
- Process / Feature
- Qty
- WCS
- Offsets / Comp
- Lines
- Notes

RPM, feed, Z depth, R plane, Q peck, cycle code, and raw block counts stay in **Technical Details** instead of the primary setup sheet.

## Tool-description behavior

Tool descriptions use the following practical hierarchy:

1. Uploaded job-packet Tool List (preferred source of truth)
2. Tool declaration in the CNC program
3. Tool-description comment recognized before that tool begins machining
4. Manual edit in the browser / exported Tool List

In the exported workbook, the Process Sheet does **not** freeze the description as text. It uses an internal lookup formula against the Tool List tab. The workbook reserves Tool List rows for tools 1–60 so descriptions can be changed later without regenerating the analysis.

If a tool number has no matching Tool List entry, the Process Sheet shows `⚠ TOOL NOT FOUND`.

## Supported CNC behavior

The parser is strongest with Fanuc-style / generic ISO G-code and currently understands:

- `T` selection and `M6` changes, including next-tool preloading
- Program tool declarations
- G54–G59
- G54.1 P extended work offsets
- G43 / H length compensation
- G40 / G41 / G42 and D registers
- G73 and G81–G89 canned cycles
- Modal G1/G2/G3 cutting motion
- Canned-cycle location counts
- Compensated milling-pass counts
- Feature comments and setup notes
- RPM, feed, Z, R and Q values for Technical Details
- Macro/subprogram detection warnings

The analyzer does **not** execute macros or simulate the CNC control.

## macOS

From the project folder:

```bash
chmod +x run_mac.command
./run_mac.command
```

The v1.1 launcher has a new dependency marker, so it will install/update the added Excel job-packet reader the first time this version runs.

## Windows

Double-click:

```text
run_windows.bat
```

## CLI

Analyze only:

```bash
python main.py part.nc
```

Analyze with a job packet:

```bash
python main.py part.nc --job-packet "Production Job Packet.xlsm"
```

Export Excel:

```bash
python main.py part.nc --job-packet "Production Job Packet.xlsm" --excel analysis.xlsx
```

## Privacy / GitHub

Real employer CNC programs and job packets should stay out of the repository unless sharing them is explicitly authorized. The included `.gitignore` excludes `samples/`, `work_samples/`, and `private/` for that reason.

## Verification warning

This is a setup and verification aid. It is not a substitute for program prove-out, machine-state verification, workholding verification, tooling verification, or review by qualified personnel before production machining.
