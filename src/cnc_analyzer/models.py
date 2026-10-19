from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class WarningItem:
    severity: str
    code: str
    message: str
    line_number: Optional[int] = None
    tool_number: Optional[int] = None


@dataclass
class ToolChange:
    line_number: int
    tool_number: int


@dataclass
class ProgramToolDeclaration:
    tool_number: int
    description: str = ""
    h_offsets: list[str] = field(default_factory=list)
    d_offsets: list[str] = field(default_factory=list)
    line_number: Optional[int] = None


@dataclass
class SequenceRecord:
    sequence_number: int = 0
    tool_number: Optional[int] = None
    description: str = ""
    operation: str = ""
    feature: str = ""
    cycle: str = ""
    quantity: int = 0
    count_basis: str = ""
    work_offset: str = ""
    h_offset: str = ""
    d_offset: str = ""
    cutter_comp: str = ""
    spindle_speed: Optional[float] = None
    feed_values: list[float] = field(default_factory=list)
    z_values: list[float] = field(default_factory=list)
    r_values: list[float] = field(default_factory=list)
    q_values: list[float] = field(default_factory=list)
    start_line: int = 0
    end_line: int = 0
    notes: list[str] = field(default_factory=list)
    cutting_blocks: int = 0
    comp_engagements: int = 0


@dataclass
class ToolSummary:
    tool_number: int
    description: str = ""
    tool_changes: int = 0
    sequences: int = 0
    cycle_locations: int = 0
    work_offsets: list[str] = field(default_factory=list)
    h_offsets: list[str] = field(default_factory=list)
    d_offsets: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    features: list[str] = field(default_factory=list)


@dataclass
class JobInfo:
    customer: str = ""
    part_number: str = ""
    part_name: str = ""
    part_revision: str = ""
    program_number: str = ""
    machine: str = ""
    operation: str = ""
    automation_notes: str = ""


@dataclass
class ToolListEntry:
    tool_number: int
    description: str = ""
    holder_type: str = ""
    projection: str = ""
    h_measure: str = ""
    d_value: str = ""
    special_instructions: str = ""
    source: str = ""


@dataclass
class JobPacketData:
    job_info: JobInfo = field(default_factory=JobInfo)
    tools: list[ToolListEntry] = field(default_factory=list)
    source_filename: str = ""


@dataclass
class AnalysisResult:
    filename: str
    program_name: str
    line_count: int
    tool_changes: list[ToolChange]
    sequences: list[SequenceRecord]
    tool_summaries: list[ToolSummary]
    warnings: list[WarningItem]
    declared_tools: list[ProgramToolDeclaration] = field(default_factory=list)
    controller_family: str = "Fanuc-style / generic ISO G-code"

    @property
    def unique_tools(self) -> int:
        return len({change.tool_number for change in self.tool_changes})

    @property
    def canned_cycle_locations(self) -> int:
        return sum(
            seq.quantity
            for seq in self.sequences
            if seq.count_basis == "cycle locations"
        )
