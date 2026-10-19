from __future__ import annotations

from pathlib import Path
import re


TEXT_ENCODINGS = ("utf-8-sig", "utf-8", "cp1252", "latin-1")


def normalize_program_text(text: str) -> str:
    """Normalize machine-export line endings without changing logical program lines."""
    # Some legacy DNC exports use CR CR LF. Python splitlines() treats that as
    # two line breaks, which doubles displayed source line numbers.
    text = re.sub(r"\r+\n|\n\r+", "\n", text)
    text = text.replace("\r", "\n")
    return text


def decode_program_bytes(data: bytes) -> str:
    if not data:
        raise ValueError("The selected file is empty.")

    sample = data[:4096]
    if sample.count(b"\x00") > max(2, len(sample) // 50):
        raise ValueError("This appears to be a binary file, not a text CNC program.")

    for encoding in TEXT_ENCODINGS:
        try:
            return normalize_program_text(data.decode(encoding))
        except UnicodeDecodeError:
            continue

    return normalize_program_text(data.decode("latin-1", errors="replace"))


def read_program_file(path: str | Path) -> str:
    file_path = Path(path)
    if not file_path.is_file():
        raise FileNotFoundError(f"File not found: {file_path}")
    return decode_program_bytes(file_path.read_bytes())
