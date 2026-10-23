"""Versioned prompts for learner-level adaptation and factuality review."""

PROMPT_VERSION = "2026-10-23.1"

LEVEL_INSTRUCTIONS = {
    "Beginner": (
        "Use short sentences, common everyday words, and explain unavoidable technical terms briefly. "
        "Keep every key fact, number, name, relationship, and necessary technical term. Keep detail, but explain it plainly."
    ),
    "Intermediate": (
        "Use clear sentences of moderate length and familiar academic vocabulary. Briefly explain less common terms. "
        "Keep all key facts, numbers, names, relationships, necessary technical terms, and supporting detail."
    ),
    "Advanced": (
        "Use concise, precise academic language and preserve technical vocabulary. You may combine related ideas, "
        "but keep the full meaning, key facts, numbers, names, qualifications, and important detail."
    ),
}


def simplification_prompt(original_text: str, level: str, feedback: str = "") -> str:
    instruction = LEVEL_INSTRUCTIONS[level]
    retry = f"\nCorrect these issues from the previous attempt: {feedback}" if feedback else ""
    return (
        "Rewrite the source for the requested learner level. Do not add facts or remove important qualifications. "
        "Return only the rewritten text, with no heading or commentary.\n\n"
        f"Learner level: {level}\nInstructions: {instruction}{retry}\n\n"
        f"Source text:\n{original_text}"
    )


def verification_prompt(original_text: str, simplified_text: str) -> str:
    return (
        "Compare the simplified text with the source. Decide whether every factual claim in the simplified text is "
        "supported by the source and whether the important meaning is preserved. Treat any added or contradicted fact "
        "as a failure. Return a JSON object with exactly these keys: "
        '"supported" (boolean), "meaning_preserved" (boolean), "unsupported_claims" (array of short strings), '
        '"omissions" (array of short strings), "explanation" (short string). Do not infer facts from outside knowledge.\n\n'
        f"SOURCE:\n{original_text}\n\nSIMPLIFIED:\n{simplified_text}"
    )
