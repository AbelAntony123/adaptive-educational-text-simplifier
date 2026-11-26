"""Batch runner: simplify every passage at every level with the real backend and save each result.

Safe to stop and restart. Results are appended to a JSON Lines file one run at a time, a run that
already produced text is skipped next time, and the runner stops early if Gemini keeps failing so it
does not burn quota. No API key is ever printed or saved.

Example (from the project folder):
    .venv\\Scripts\\python experiments\\run_experiments.py --model gemini-3.5-flash-lite --pause 15
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from services.env_file import load_env_file  # noqa: E402

DEFAULT_PASSAGES = ROOT / "experiments" / "passages.json"
DEFAULT_LEVELS = ("Beginner", "Intermediate", "Advanced")
STOP_AFTER_FAILURES = 4  # consecutive runs with no text at all


def load_passages(path: Path) -> list[dict]:
    passages = json.loads(Path(path).read_text(encoding="utf-8"))
    for passage in passages:
        if not {"id", "subject", "text"} <= set(passage):
            raise ValueError(f"Passage is missing id, subject or text: {passage!r}")
    return passages


def plan_runs(passages: list[dict], levels) -> list[tuple[dict, str]]:
    """Every passage at every level, passage by passage (so an early stop still covers all levels of some texts)."""
    return [(passage, level) for passage in passages for level in levels]


def run_key(passage_id: str, level: str, model: str, prompt_version: str) -> str:
    return f"{passage_id}|{level}|{model}|{prompt_version}"


def load_done(path: Path) -> set[str]:
    """Keys of runs that already produced real text. Runs with no text are tried again."""
    done: set[str] = set()
    path = Path(path)
    if not path.exists():
        return done
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("source") == "backend" and str(record.get("simplified_text", "")).strip():
            done.add(record["run_key"])
    return done


def should_stop(recent_had_text: list[bool], limit: int = STOP_AFTER_FAILURES) -> bool:
    """True when the last ``limit`` runs all produced no text."""
    return len(recent_had_text) >= limit and not any(recent_had_text[-limit:])


def build_record(passage: dict, level: str, result: dict, *, model: str, embedding_model: str,
                 prompt_version: str, elapsed: float, requests: dict, original_readability) -> dict:
    return {
        "run_key": run_key(passage["id"], level, model, prompt_version),
        "passage_id": passage["id"],
        "subject": passage["subject"],
        "level": level,
        "model": model,
        "embedding_model": embedding_model,
        "prompt_version": prompt_version,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "elapsed_seconds": round(elapsed, 1),
        "source": result["source"],
        "status": result["verification_status"],
        "attempts": result["attempts"],
        "api_requests": requests,
        "errors": result["errors"],
        "metrics": result["metrics"],
        "original_readability": original_readability,
        "verification_details": result["verification_details"],
        "original_text": result["original_text"],
        "simplified_text": result["simplified_text"],
    }


def _instrument() -> dict:
    """Count real API requests (cache hits are not requests) by wrapping the three Gemini calls."""
    from pipeline import api, llm_client, verification

    counts = {"generate": 0, "verify": 0, "embed": 0}
    generate, verify_text, embed_one = api.generate_text, llm_client.verify_text, llm_client._embed_one

    def counted_generate(*args, **kwargs):
        counts["generate"] += 1
        return generate(*args, **kwargs)

    def counted_verify(*args, **kwargs):
        counts["verify"] += 1
        return verify_text(*args, **kwargs)

    def counted_embed(client, model, text):
        if (model, text) not in llm_client._EMBEDDING_CACHE:
            counts["embed"] += 1
        return embed_one(client, model, text)

    api.generate_text = counted_generate
    verification.verify.__defaults__ = (counted_verify, None)  # the default `verifier` argument
    llm_client._embed_one = counted_embed
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--passages", type=Path, default=DEFAULT_PASSAGES)
    parser.add_argument("--levels", nargs="+", default=list(DEFAULT_LEVELS), choices=DEFAULT_LEVELS)
    parser.add_argument("--model", help="Gemini model for this run only (otherwise GEMINI_MODEL or the default)")
    parser.add_argument("--pause", type=float, default=15.0, help="seconds to wait between runs")
    parser.add_argument("--out", type=Path, help="results file (default: results/experiment_<model>.jsonl)")
    parser.add_argument("--max-runs", type=int, help="stop after this many new runs")
    parser.add_argument("--dry-run", action="store_true", help="print the plan and make no API requests")
    args = parser.parse_args(argv)

    if args.model:
        os.environ["GEMINI_MODEL"] = args.model  # set before the .env file is read, so it wins
    names = load_env_file()
    os.environ.setdefault("SIMPLIFIER_BACKEND_MODULE", "pipeline.api")

    from pipeline.config import get_settings
    from pipeline.evaluation import readability_score
    from pipeline.prompts import PROMPT_VERSION

    settings = get_settings()
    model = settings.model
    out = args.out or ROOT / "results" / f"experiment_{model}.jsonl"
    passages = load_passages(args.passages)
    done = load_done(out)
    todo = [
        (passage, level) for passage, level in plan_runs(passages, args.levels)
        if run_key(passage["id"], level, model, PROMPT_VERSION) not in done
    ]
    if args.max_runs is not None:
        todo = todo[: args.max_runs]

    print(f"Model: {model} | embedding model: {settings.embedding_model} | prompt version: {PROMPT_VERSION}")
    print(f"Settings found in .env (names only): {names}")
    print(f"{len(passages)} passages x {len(args.levels)} levels | already done: {len(done)} | to run now: {len(todo)}")
    print(f"Results file: {out}")
    if args.dry_run or not todo:
        print("Dry run, nothing sent." if args.dry_run else "Nothing left to run.")
        return 0
    if not settings.api_key:
        print("GEMINI_API_KEY is not set (put it in .env or the terminal). Nothing was sent.")
        return 1

    from services.backend_adapter import simplify

    counts = _instrument()
    out.parent.mkdir(parents=True, exist_ok=True)
    recent: list[bool] = []
    for index, (passage, level) in enumerate(todo, start=1):
        before = dict(counts)
        started = time.time()
        result = simplify(passage["text"], level, mode="backend")  # no cache, no demo fallback: real data only
        used = {name: counts[name] - before[name] for name in counts}
        record = build_record(
            passage, level, result, model=model, embedding_model=settings.embedding_model,
            prompt_version=PROMPT_VERSION, elapsed=time.time() - started, requests=used,
            original_readability=readability_score(passage["text"]),
        )
        with out.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        had_text = bool(record["simplified_text"].strip())
        recent.append(had_text)
        codes = ",".join(error["code"] for error in record["errors"]) or "-"
        print(f"[{index}/{len(todo)}] {passage['id']:24} {level:12} status={record['status']:8} "
              f"attempts={record['attempts']} requests={sum(used.values())} errors={codes} ({record['elapsed_seconds']}s)", flush=True)
        if should_stop(recent):
            print(f"Stopping: the last {STOP_AFTER_FAILURES} runs produced no text (Gemini overloaded or out of quota). "
                  "Run the same command later to continue where this stopped.")
            return 2
        if index < len(todo):
            time.sleep(args.pause)
    print("Finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
