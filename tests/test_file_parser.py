import pytest

from services.file_parser import MAX_FILE_BYTES, FileParseError, parse_uploaded_file


def test_reads_txt_file():
    assert parse_uploaded_file("notes.txt", b"Hello world") == "Hello world"


def test_reads_markdown_file_and_ignores_case():
    assert parse_uploaded_file("NOTES.MD", b"# Title\n\nBody") == "# Title\n\nBody"


def test_strips_utf8_byte_order_mark():
    assert parse_uploaded_file("a.txt", "﻿Hi".encode("utf-8")) == "Hi"


def test_reads_non_ascii_text():
    assert parse_uploaded_file("a.txt", "café".encode("utf-8")) == "café"


@pytest.mark.parametrize("name", ["paper.pdf", "doc.docx", "image.png", "noextension", ""])
def test_unsupported_types_are_rejected(name):
    with pytest.raises(FileParseError, match="not a supported file type"):
        parse_uploaded_file(name, b"data")


def test_empty_file_is_rejected():
    with pytest.raises(FileParseError, match="empty"):
        parse_uploaded_file("a.txt", b"")


def test_whitespace_only_file_is_rejected():
    with pytest.raises(FileParseError, match="whitespace"):
        parse_uploaded_file("a.txt", b"  \n\t ")


def test_oversized_file_is_rejected():
    with pytest.raises(FileParseError, match="too large"):
        parse_uploaded_file("a.txt", b"a" * (MAX_FILE_BYTES + 1))


def test_non_utf8_file_is_rejected():
    with pytest.raises(FileParseError, match="UTF-8"):
        parse_uploaded_file("a.txt", b"\xff\xfe\x00bad")


def test_binary_content_is_rejected():
    with pytest.raises(FileParseError, match="binary"):
        parse_uploaded_file("a.txt", b"abc\x00def")
