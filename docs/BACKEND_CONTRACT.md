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
15 seconds. The worst case is five generation requests (three that return a
response plus two retries of temporary errors), three verification requests,
and two embedding requests (one per text), about 150 seconds, plus 1 to 2
second pauses between retries of temporary errors. End-to-end time depends on
network and model availability.

## Metrics

- `readability_score`: Flesch Reading Ease, `206.835 - 1.015 × (words / sentences) - 84.6 × (syllables / words)`. The scale is conventionally about 0–100; higher means easier. Syllables are estimated with a lightweight English spelling heuristic.
- `semantic_similarity`: cosine similarity between Gemini text embeddings (each text is embedded in its own request, because `gemini-embedding-2-preview` merges a list of texts into one vector), rescaled to 0–1 using `(cosine + 1) / 2`. It indicates textual similarity only; it does not prove factual correctness. If embedding computation fails, the value is `None`.
- Word counts use a Unicode-aware word-token regular expression. A metric that cannot be computed is `None`.

## Verification and retries

Verification combines preservation checks for detected numbers, capitalized
names and hyphenated terms; an output-length sanity check; and a second Gemini
review for unsupported claims and meaning omissions. These are automated
signals, not a guarantee of factual truth. A skipped review is `NOT RUN` and
cannot produce overall `PASS`.

`attempts` is the number of generation requests started by the pipeline.
Provider SDK retries are disabled so one pipeline attempt maps to one provider
request. Verification and embedding requests do not count. The default maximum
is three generation requests that return a response, configurable with
`SIMPLIFIER_MAX_ATTEMPTS` (1–5). A failed verification prompts another
generation with feedback. A transient generation error (timeout, rate limit,
HTTP 5xx) is retried at most twice, with a short pause, and these retries do not
use up the three response attempts, but they are counted in `attempts` because
each one is a started request. `attempts` can therefore exceed the maximum.

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
