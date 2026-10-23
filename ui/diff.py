"""Word-level comparison of the original and simplified text, as safe HTML."""

from __future__ import annotations

import difflib
import html


def word_diff_html(original: str, simplified: str) -> tuple[str, str]:
    """Return (original_html, simplified_html) with removed words struck through and added words underlined."""
    before, after = original.split(), simplified.split()
    left: list[str] = []
    right: list[str] = []
    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(a=before, b=after, autojunk=False).get_opcodes():
        removed = html.escape(" ".join(before[a1:a2]))
        added = html.escape(" ".join(after[b1:b2]))
        if tag == "equal":
            left.append(removed)
            right.append(added)
            continue
        if removed:
            left.append(f"<del>{removed}</del>")
        if added:
            right.append(f"<ins>{added}</ins>")
    return " ".join(left), " ".join(right)
