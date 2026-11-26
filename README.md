# adaptive-educational-text-simplifier
Adaptive Educational Text Simplification using LLMs — a research prototype for learner-level adaptation, meaning preservation, and factuality evaluation.

## Streamlit user interface

The UI lives in `app.py`, `ui/` and `services/`. It currently runs on clearly labeled **mock data**
(invented example output, not produced by an AI model). The only file that talks to the
simplification backend is `services/backend_adapter.py`.

Set up and run (Windows PowerShell, from the project folder):

```bash
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python -m streamlit run app.py
```

Then open http://localhost:8501 in a browser. Run the tests with `.venv\Scripts\python -m pytest`.

To use the real backend, copy `.env.example` to `.env` (it is ignored by Git), fill in `GEMINI_API_KEY`
and `SIMPLIFIER_BACKEND_MODULE=pipeline.api`, then choose "Real backend" in the sidebar. The app reads
`.env` automatically; a variable already set in the terminal wins over the file. Never put API keys in
source files or Git, and never share the `.env` file.

Saving quota in real-backend mode:
- Retries share one budget of three requests per run, and the two Gemini review calls are skipped when a
  local check has already failed. A best-case run makes 4 requests; the worst case makes 8.
- "Reuse saved results" (sidebar) returns an earlier verified result for the same text and level without
  any new requests. The embedding of the source text is also reused.
- If Gemini's quota stops a run before any text exists, "Show demo data if the quota runs out" shows
  clearly labelled demo data instead of an empty result. Real text is never replaced by demo data.
