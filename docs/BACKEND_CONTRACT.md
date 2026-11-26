# Backend contract

## Public entry point

Set `SIMPLIFIER_BACKEND_MODULE=pipeline.api`. The UI calls
`pipeline.api.simplify_text(original_text: str, level: str) -> dict`.
The function returns the agreed result keys: `original_text`,
`simplified_text`, `level`, `verification_status`, `verification_details`,
`metrics`, `attempts`, and `errors`. It does not intentionally expose provider
exceptions or credentials.

`level` must exactly match `Beginner`, `Intermediate`, or `Advanced`. Beginner
uses short sentences and common vocabulary. Intermediate uses moderate
sentence length and familiar academic words. Advanced uses concise academic
wording while retaining technical terms. Every level is instructed to retain
facts, names, numbers, qualifications, and necessary detail, and none may add
definitions, examples, or background that the source does not state (the
factuality review treats any added fact as a failure).

The current UI rejects input longer than 20,000 characters. The backend uses
the same default limit through `SIMPLIFIER_MAX_INPUT_CHARS`. The UI timeout is
180 seconds. Each backend request defaults to a 15-second timeout, bounded at
15 seconds. The worst case is three generation requests (the first try plus at
most two retries of any kind), three verification requests and two embedding
requests (one per text), eight requests in all, about 120 seconds, plus pauses
between retries (1 to 2 seconds for temporary errors, up to 21 seconds once for
a short per-minute quota wait). End-to-end time depends on network and model
availability. A best-case run makes four requests: one generation, one
verification and two embeddings. The embedding of the source text is kept in
memory and reused for later levels and re-runs of the same text, so those
need only one embedding request.

## Metrics

- `readability_score`: Flesch Reading Ease, `206.835 - 1.015 × (words / sentences) - 84.6 × (syllables / words)`. The scale is conventionally about 0–100; higher means easier. Syllables are estimated with a lightweight English spelling heuristic.
- `semantic_similarity`: cosine similarity between Gemini text embeddings (each text is embedded in its own request, because `gemini-embedding-2-preview` merges a list of texts into one vector), rescaled to 0–1 using `(cosine + 1) / 2`. It indicates textual similarity only; it does not prove factual correctness. If embedding computation fails, the value is `None`.
- Word counts use a Unicode-aware word-token regular expression. A metric that cannot be computed is `None`.

## Verification and retries

Verification combines preservation checks for detected numbers, capitalized
names and hyphenated terms; an output-length sanity check; a "Simplification
effect" check; and a second Gemini review for unsupported claims and meaning
omissions. The simplification check is deterministic: for Beginner the output
must raise the Flesch Reading Ease by at least 5 points or shorten the average
sentence by at least 20%; for Intermediate, 2 points or 10%. Sources that
already score 70 (Beginner) or 60 (Intermediate) or higher pass automatically,
and Advanced has no target. The explanation shows the before and after
readability and sentence length. The thresholds live in
`SIMPLIFICATION_TARGETS` in `pipeline/verification.py` and are research
settings to tune. These are automated
signals, not a guarantee of factual truth. A skipped review is `NOT RUN` and
cannot produce overall `PASS`.

The two Gemini review checks are skipped (reported as `NOT RUN`, with the reason
"Skipped to save quota") when a local check has already failed, because the
result will be rejected anyway. The overall status is still `FAIL`.

`attempts` is the number of generation requests started by the pipeline.
Provider SDK retries are disabled so one pipeline attempt maps to one provider
request. Verification and embedding requests do not count. All retries, for any
reason, share one budget: at most `SIMPLIFIER_MAX_ATTEMPTS` generation requests
(default 3, so the first try plus two retries; range 1–5), and `attempts` never
exceeds it. A failed verification prompts another generation with feedback. A
transient error (timeout or HTTP 5xx) is retried after a short pause. A
rate-limit (HTTP 429) error is retried once, but only when Google asks for a
wait of 20 seconds or less; a longer wait or a daily quota is reported at once,
with the number of seconds or "try again tomorrow" in the message. An error that
is retried and then recovers is not reported in `errors`.

## Configuration

- `GEMINI_API_KEY`: required Gemini API key.
- `GEMINI_MODEL`: generation and verification model; defaults to `gemini-3.8-flash`.
- `GEMINI_EMBEDDING_MODEL`: embedding model; defaults to `gemini-embedding-2-preview`.
- `SIMPLIFIER_MAX_ATTEMPTS`: generation limit, defaults to 3.
- `SIMPLIFIER_MAX_INPUT_CHARS`: input limit, defaults to 20,000.
- `GEMINI_TIMEOUT_SECONDS`: provider request timeout, defaults to 15 seconds (maximum 15).
- `SIMPLIFIER_BACKEND_MODULE`: set to `pipeline.api` in the UI environment.

Set secrets only in the environment; `.env.example` contains variable names
without values. Model and prompt version are written to logs for reproducibility.
Google's current Gemini API pricing page says free-tier content may be used to
improve Google products. Avoid sending sensitive or confidential source text
through a free-tier key.
