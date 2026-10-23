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

To use a real backend later, set the environment variable `SIMPLIFIER_BACKEND_MODULE` to the module
that contains `simplify_text(original_text, level)`, then choose "Real backend" in the sidebar.
Never put API keys in source files or Git.
