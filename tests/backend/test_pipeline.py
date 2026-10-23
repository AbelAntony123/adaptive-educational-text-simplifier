from __future__ import annotations

import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pipeline import api
from pipeline.evaluation import readability_score, word_count
from pipeline.llm_client import LLMError
from pipeline import llm_client
from pipeline.config import get_settings
from pipeline.prompts import LEVEL_INSTRUCTIONS, simplification_prompt
from pipeline.verification import verify


TEXT = "cells contain 42 parts and help the body function."
SIMPLIFIED = "cells have 42 parts that help the body work."


def passing_checks(original, simplified):
    return [
        {"check": "facts", "status": "PASS", "explanation": "Checked."},
        {"check": "meaning", "status": "PASS", "explanation": "Preserved."},
    ]


class ConfigTests(unittest.TestCase):
    def test_free_tier_default_model_and_ui_safe_timeout(self):
        with patch.dict(os.environ, {}, clear=True):
            settings = get_settings()
        self.assertEqual(settings.model, "gemini-3.8-flash")
        self.assertEqual(settings.embedding_model, "gemini-embedding-2-preview")
        self.assertEqual(settings.timeout_seconds, 15.0)

    def test_request_timeout_cannot_exceed_ui_budget(self):
        with patch.dict(os.environ, {"GEMINI_TIMEOUT_SECONDS": "90"}):
            self.assertEqual(get_settings().timeout_seconds, 15.0)


class PromptTests(unittest.TestCase):
    def test_each_level_has_distinct_instruction(self):
        self.assertEqual(set(LEVEL_INSTRUCTIONS), {"Beginner", "Intermediate", "Advanced"})
        self.assertEqual(len(set(LEVEL_INSTRUCTIONS.values())), 3)
        prompts = {simplification_prompt(TEXT, level) for level in LEVEL_INSTRUCTIONS}
        self.assertEqual(len(prompts), 3)


class MetricTests(unittest.TestCase):
    def test_known_readability_and_word_count(self):
        self.assertEqual(word_count("The cat sat."), 3)
        self.assertAlmostEqual(readability_score("The cat sat."), 119.19, places=2)

    def test_empty_readability_is_none(self):
        self.assertIsNone(readability_score(""))


class VerificationTests(unittest.TestCase):
    def test_verification_pass(self):
        details = verify(TEXT, SIMPLIFIED, verifier=lambda *_: {
            "supported": True,
            "meaning_preserved": True,
            "unsupported_claims": [],
            "omissions": [],
            "explanation": "Supported by source.",
        })
        self.assertTrue(all(item["status"] == "PASS" for item in details))

    def test_verification_fails_for_missing_number_and_claim(self):
        details = verify(TEXT, "cells have parts that help the body work.", verifier=lambda *_: {
            "supported": False,
            "meaning_preserved": False,
            "unsupported_claims": ["new fact"],
            "omissions": ["42 parts"],
            "explanation": "Not supported.",
        })
        self.assertTrue(any(item["status"] == "FAIL" for item in details))

    def test_verification_unavailable_is_not_run(self):
        def unavailable(*_):
            raise LLMError("API_TIMEOUT", "Timed out.")

        details = verify(TEXT, SIMPLIFIED, verifier=unavailable)
        self.assertEqual([item["status"] for item in details[-2:]], ["NOT RUN", "NOT RUN"])


class GeminiClientTests(unittest.TestCase):
    def test_generation_uses_configured_model_and_returns_text(self):
        fake = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text="Readable version."),
        ))
        with patch.object(llm_client, "_client", return_value=fake), patch.dict(os.environ, {"GEMINI_MODEL": "gemini-test"}):
            self.assertEqual(llm_client.generate_text(TEXT, "Beginner"), "Readable version.")

    def test_malformed_verification_json_is_rejected(self):
        fake = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text="not json"),
        ))
        with patch.object(llm_client, "_client", return_value=fake):
            with self.assertRaises(LLMError) as raised:
                llm_client.verify_text(TEXT, SIMPLIFIED)
        self.assertEqual(raised.exception.code, "MODEL_OUTPUT_INVALID")

    def test_malformed_verification_fields_are_rejected(self):
        fake = SimpleNamespace(models=SimpleNamespace(
            generate_content=lambda **kwargs: SimpleNamespace(text='{"supported":true,"meaning_preserved":true}'),
        ))
        with patch.object(llm_client, "_client", return_value=fake):
            with self.assertRaises(LLMError) as raised:
                llm_client.verify_text(TEXT, SIMPLIFIED)
        self.assertEqual(raised.exception.code, "MODEL_OUTPUT_INVALID")

    def test_rate_limit_status_code_is_mapped_without_leaking_provider_text(self):
        error = Exception("private provider response")
        error.code = 429
        mapped = llm_client._safe_provider_error(error)
        self.assertEqual(mapped.code, "RATE_LIMIT")
        self.assertNotIn("private provider response", mapped.public_message)

    def test_embedding_similarity_uses_zero_to_one_scale(self):
        fake = SimpleNamespace(models=SimpleNamespace(
            embed_content=lambda **kwargs: SimpleNamespace(embeddings=[
                SimpleNamespace(values=[1.0, 0.0]), SimpleNamespace(values=[1.0, 0.0]),
            ]),
        ))
        with patch.object(llm_client, "_client", return_value=fake):
            self.assertEqual(llm_client.semantic_similarity(TEXT, SIMPLIFIED), 1.0)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "SIMPLIFIER_MAX_ATTEMPTS": "3"})
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)

    def test_all_levels_return_contract_shape(self):
        for level in LEVEL_INSTRUCTIONS:
            with self.subTest(level=level), patch.object(api, "generate_text", return_value=SIMPLIFIED), patch.object(
                api, "verify", side_effect=passing_checks
            ), patch.object(api, "semantic_similarity", return_value=0.82):
                result = api.simplify_text(TEXT, level)
                self.assertEqual(set(result), {
                    "original_text", "simplified_text", "level", "verification_status",
                    "verification_details", "metrics", "attempts", "errors",
                })
                self.assertEqual(result["verification_status"], "PASS")
                self.assertEqual(result["attempts"], 1)
                self.assertEqual(result["level"], level)
                self.assertEqual(result["metrics"]["semantic_similarity"], 0.82)
                self.assertEqual(result["metrics"]["word_count_original"], word_count(TEXT))
                self.assertIsInstance(result["metrics"]["readability_score"], float)
                self.assertEqual(result["errors"], [])
                self.assertEqual(result["verification_status"], "PASS")
                self.assertTrue(all(set(item) == {"check", "status", "explanation"} for item in result["verification_details"]))
                self.assertTrue(all(item["status"] in api.STATUSES for item in result["verification_details"]))
                self.assertTrue(all(isinstance(item["explanation"], str) for item in result["verification_details"]))
                self.assertEqual(set(result["metrics"]), {
                    "readability_score", "semantic_similarity", "word_count_original", "word_count_simplified",
                })
                self.assertTrue(all(value is None or isinstance(value, (int, float)) for value in result["metrics"].values()))
                self.assertTrue(all(set(error) == {"code", "message"} for error in result["errors"]))

    def test_empty_and_invalid_level(self):
        empty = api.simplify_text("  ", "Beginner")
        invalid = api.simplify_text(TEXT, "beginner")
        self.assertEqual(empty["errors"][0]["code"], "INVALID_INPUT")
        self.assertEqual(invalid["errors"][0]["code"], "INVALID_LEVEL")
        self.assertEqual(empty["attempts"], 0)
        self.assertEqual(invalid["attempts"], 0)

    def test_non_string_input_and_level_keep_result_types(self):
        result = api.simplify_text(None, None)
        self.assertIsInstance(result["original_text"], str)
        self.assertIsInstance(result["level"], str)
        self.assertEqual(result["errors"][0]["code"], "INVALID_INPUT")

    def test_missing_api_key(self):
        with patch.dict(os.environ, {}, clear=True):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(result["errors"][0]["code"], "MISSING_API_KEY")
        self.assertEqual(result["attempts"], 0)
        self.assertTrue(all(value is None for value in result["metrics"].values()))

    def test_input_limit(self):
        with patch.dict(os.environ, {"SIMPLIFIER_MAX_INPUT_CHARS": "3"}):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(result["errors"][0]["code"], "INPUT_TOO_LONG")

    def test_timeout_is_reported_and_attempted_again(self):
        with patch.object(api, "generate_text", side_effect=LLMError("API_TIMEOUT", "Timed out.")) as generate:
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(result["errors"][0]["code"], "API_TIMEOUT")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(generate.call_count, 3)

    def test_rate_limit_and_generic_exception_have_safe_errors(self):
        for exception, code in [
            (LLMError("RATE_LIMIT", "Rate limited."), "RATE_LIMIT"),
            (LLMError("API_ERROR", "Unavailable."), "API_ERROR"),
        ]:
            with self.subTest(code=code), patch.object(api, "generate_text", side_effect=exception):
                result = api.simplify_text(TEXT, "Beginner")
                self.assertEqual(result["errors"][0]["code"], code)
                self.assertEqual(result["attempts"], 3)

    def test_malformed_generation_output_retries(self):
        with patch.object(api, "generate_text", return_value="") as generate:
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(result["errors"][0]["code"], "MODEL_OUTPUT_INVALID")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(result["simplified_text"], "")

    def test_verification_fail_retries_and_reports_exact_attempts(self):
        with patch.object(api, "generate_text", side_effect=["bad rewrite", SIMPLIFIED]) as generate, patch.object(
            api, "verify", side_effect=[
                [{"check": "facts", "status": "FAIL", "explanation": "Wrong."}],
                passing_checks(TEXT, SIMPLIFIED),
            ],
        ), patch.object(api, "semantic_similarity", return_value=0.7):
            result = api.simplify_text(TEXT, "Intermediate")
        self.assertEqual(result["verification_status"], "PASS")
        self.assertEqual(result["attempts"], 2)
        self.assertEqual(generate.call_count, 2)

    def test_verification_fail_after_last_retry_returns_best_result(self):
        failed = [{"check": "facts", "status": "FAIL", "explanation": "Unsupported."}]
        with patch.object(api, "generate_text", return_value=SIMPLIFIED), patch.object(api, "verify", return_value=failed), patch.object(
            api, "semantic_similarity", return_value=0.5
        ):
            result = api.simplify_text(TEXT, "Advanced")
        self.assertEqual(result["verification_status"], "FAIL")
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["simplified_text"], SIMPLIFIED)
        self.assertEqual(result["errors"][-1]["code"], "VERIFICATION_FAILED")

    def test_verification_not_run_never_becomes_pass(self):
        details = [
            {"check": "facts", "status": "PASS", "explanation": "Matched."},
            {"check": "review", "status": "NOT RUN", "explanation": "Offline."},
        ]
        with patch.object(api, "generate_text", return_value=SIMPLIFIED), patch.object(api, "verify", return_value=details), patch.object(
            api, "semantic_similarity", return_value=0.6
        ):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(result["verification_status"], "NOT RUN")
        self.assertTrue(any(error["code"] == "VERIFICATION_UNAVAILABLE" for error in result["errors"]))

    def test_similarity_failure_becomes_none_not_zero(self):
        with patch.object(api, "generate_text", return_value=SIMPLIFIED), patch.object(
            api, "verify", side_effect=passing_checks
        ), patch.object(api, "semantic_similarity", side_effect=LLMError("API_ERROR", "Unavailable.")):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertIsNone(result["metrics"]["semantic_similarity"])
        self.assertTrue(any(error["code"] == "API_ERROR" for error in result["errors"]))

    def test_generation_failure_does_not_leak_exception_text(self):
        with patch.object(api, "generate_text", side_effect=LLMError("API_ERROR", "Safe generic error.")):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertNotIn("test-key", str(result))
        self.assertNotIn("Traceback", str(result))


@unittest.skipUnless(os.environ.get("GEMINI_API_KEY"), "Optional integration test: GEMINI_API_KEY is not set")
class GeminiIntegrationTest(unittest.TestCase):
    def test_real_gemini_round_trip(self):
        result = api.simplify_text("Plants use sunlight to make food.", "Beginner")
        self.assertIsInstance(result, dict)
        self.assertGreaterEqual(result["attempts"], 1)
        self.assertTrue(result["simplified_text"] or result["errors"])


if __name__ == "__main__":
    unittest.main()
