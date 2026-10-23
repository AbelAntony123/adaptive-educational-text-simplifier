"""Versioned prompts for learner-level adaptation and factuality review."""

PROMPT_VERSION = "2026-10-23.3"

# The factuality review rejects any added fact, so no level asks the model to add
# definitions or explanations; simplification works by shorter sentences and plainer words.
LEVEL_INSTRUCTIONS = {
    "Beginner": (
        "Use short sentences (about 10 to 14 words each) and common everyday words. Split long sentences into several short ones and replace "
        "hard words with simpler words where the meaning stays the same. Keep every key fact, number, name, "
        "relationship, and necessary technical term exactly as the source states it, and keep the text about as "
        "long as the source."
    ),
    "Intermediate": (
        "Use clear sentences of moderate length (about 15 to 20 words each) and familiar academic vocabulary. Replace rare words with more "
        "familiar ones where the meaning stays the same. "
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
        "Rewrite the source for the requested learner level. Do not add facts, definitions, examples, analogies, or "
        "background that the source does not state, and do not remove important qualifications. "
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
