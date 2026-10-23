"""Read uploaded text files (.txt and .md) and report problems clearly."""

from __future__ import annotations

SUPPORTED_EXTENSIONS = (".txt", ".md")
MAX_FILE_BYTES = 1_000_000  # 1 MB


class FileParseError(Exception):
    """Raised with a user-friendly message when a file cannot be used."""


def parse_uploaded_file(filename: str, data: bytes) -> str:
    """Return the text inside an uploaded file or raise FileParseError."""
    name = (filename or "").strip()
    lowered = name.lower()
    if not lowered.endswith(SUPPORTED_EXTENSIONS):
        supported = ", ".join(SUPPORTED_EXTENSIONS)
        raise FileParseError(
            f"'{name or 'This file'}' is not a supported file type. Please upload one of: {supported}."
        )
    if not data:
        raise FileParseError(f"'{name}' is empty.")
    if len(data) > MAX_FILE_BYTES:
        raise FileParseError(
            f"'{name}' is too large ({len(data) / 1_000_000:.1f} MB). The limit is {MAX_FILE_BYTES // 1_000_000} MB."
        )
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise FileParseError(
            f"'{name}' could not be read as UTF-8 text. Please save it as UTF-8 and try again."
        ) from None
    if "\x00" in text:
        raise FileParseError(f"'{name}' looks like a binary file, not plain text.")
    if not text.strip():
        raise FileParseError(f"'{name}' contains only whitespace.")
    return text
