import pytest

from cnc_analyzer.fileio import decode_program_bytes, normalize_program_text


def test_decode_utf8():
    assert decode_program_bytes(b"T1M6\nG54\n") == "T1M6\nG54\n"


def test_reject_binary():
    with pytest.raises(ValueError):
        decode_program_bytes(b"\x00\x00\x00\x00binary")


def test_normalizes_legacy_crcrlf_without_double_line_numbers():
    text = "O1996\r\r\nT1\r\r\nM6\r\r\nG54\r\r\n"
    normalized = normalize_program_text(text)
    assert normalized.splitlines() == ["O1996", "T1", "M6", "G54"]
