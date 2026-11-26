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
from pipeline.verification import simplification_check, verify


TEXT = "cells contain 42 parts and help the body function."
SIMPLIFIED = "cells have 42 parts that help the body work."


def passing_checks(original, simplified, level=None):
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

    def test_no_prompt_asks_the_model_to_add_explanations(self):
        # The factuality review fails added facts, so asking for explanations would
        # make Beginner results fail by design.
        for level, instruction in LEVEL_INSTRUCTIONS.items():
            with self.subTest(level=level):
                self.assertNotIn("explain", instruction.lower())
                self.assertIn("do not add", simplification_prompt(TEXT, level).lower())


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

    def test_model_review_is_skipped_when_a_local_check_already_failed(self):
        calls = []

        def verifier(*_):
            calls.append(1)
            return {}

        details = verify(TEXT, "cells have parts that help the body work.", verifier=verifier)  # the number 42 is missing
        self.assertEqual(calls, [])  # no Gemini request was spent
        self.assertEqual(details[0]["status"], "FAIL")
        self.assertEqual([d["status"] for d in details[-2:]], ["NOT RUN", "NOT RUN"])
        self.assertIn("Skipped to save quota", details[-1]["explanation"])

    def test_skipped_review_does_not_hide_the_failure(self):
        details = verify(TEXT, "cells have parts that help the body work.", verifier=lambda *_: {})
        self.assertEqual(api._overall_status(details), "FAIL")

    def test_model_review_runs_when_local_checks_pass(self):
        calls = []

        def verifier(*_):
            calls.append(1)
            return {"supported": True, "meaning_preserved": True, "unsupported_claims": [], "omissions": [], "explanation": "ok"}

        verify(TEXT, SIMPLIFIED, verifier=verifier)
        self.assertEqual(calls, [1])

    def test_verification_unavailable_is_not_run(self):
        def unavailable(*_):
            raise LLMError("API_TIMEOUT", "Timed out.")

        details = verify(TEXT, SIMPLIFIED, verifier=unavailable)
        self.assertEqual([item["status"] for item in details[-2:]], ["NOT RUN", "NOT RUN"])


# Real texts from a live run (source and two outputs), used to calibrate the check.
LIVE_SOURCE = (
    "Photosynthesis is the biochemical process by which autotrophic organisms, such as plants and algae, convert "
    "light energy into chemical energy. During the light-dependent reactions, chlorophyll absorbs photons, driving "
    "the synthesis of ATP and NADPH, which subsequently power the Calvin cycle, wherein carbon dioxide is fixed "
    "into glucose."
)
LIVE_BEGINNER = (
    "Photosynthesis is a biochemical process. Autotrophic organisms, such as plants and algae, use it to convert "
    "light energy into chemical energy. During the light-dependent reactions, chlorophyll absorbs photons. This "
    "drives the synthesis of ATP and NADPH. These then power the Calvin cycle, where carbon dioxide is fixed into "
    "glucose."
)


class SimplificationCheckTests(unittest.TestCase):
    def test_real_beginner_output_passes_and_reports_the_numbers(self):
        check = simplification_check(LIVE_SOURCE, LIVE_BEGINNER, "Beginner")
        self.assertEqual(check["status"], "PASS")
        self.assertIn("20.3 to 44.4", check["explanation"])

    def test_near_copy_fails_with_actionable_feedback(self):
        check = simplification_check(LIVE_SOURCE, LIVE_SOURCE.replace("Photosynthesis", "Photosynthesis,"), "Beginner")
        self.assertEqual(check["status"], "FAIL")
        self.assertIn("shorter sentences", check["explanation"])

    def test_advanced_has_no_simplification_target(self):
        self.assertEqual(simplification_check(LIVE_SOURCE, LIVE_SOURCE, "Advanced")["status"], "PASS")

    def test_already_easy_source_passes(self):
        easy = "The cat sat on the mat. It was warm."
        self.assertEqual(simplification_check(easy, easy + " Yes.", "Beginner")["status"], "PASS")

    def test_uncomputable_readability_is_not_run(self):
        self.assertEqual(simplification_check("...", "...", "Beginner")["status"], "NOT RUN")

    def test_verify_includes_the_check_only_when_a_level_is_given(self):
        verifier = lambda *_: {
            "supported": True, "meaning_preserved": True, "unsupported_claims": [], "omissions": [], "explanation": "ok",
        }
        without = verify(LIVE_SOURCE, LIVE_BEGINNER, verifier=verifier)
        with_level = verify(LIVE_SOURCE, LIVE_BEGINNER, verifier=verifier, level="Beginner")
        self.assertNotIn("Simplification effect", [d["check"] for d in without])
        self.assertIn("Simplification effect", [d["check"] for d in with_level])


class GeminiClientTests(unittest.TestCase):
    def setUp(self):
        llm_client._EMBEDDING_CACHE.clear()
        self.addCleanup(llm_client._EMBEDDING_CACHE.clear)

    def test_embedding_of_the_same_source_text_is_reused(self):
        requests = []

        def embed_content(**kwargs):
            requests.append(kwargs["contents"])
            return SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 0.0])])

        fake = SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))
        with patch.object(llm_client, "_client", return_value=fake):
            llm_client.semantic_similarity(TEXT, "first rewrite")
            llm_client.semantic_similarity(TEXT, "second rewrite")
        self.assertEqual(requests, [TEXT, "first rewrite", "second rewrite"])  # the source was embedded once

    def test_embedding_cache_is_bounded(self):
        fake = SimpleNamespace(models=SimpleNamespace(
            embed_content=lambda **kwargs: SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0])]),
        ))
        with patch.object(llm_client, "_client", return_value=fake):
            for number in range(llm_client._EMBEDDING_CACHE_LIMIT + 10):
                llm_client._embed_one(fake, "model", f"text {number}")
        self.assertEqual(len(llm_client._EMBEDDING_CACHE), llm_client._EMBEDDING_CACHE_LIMIT)

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
            embed_content=lambda **kwargs: SimpleNamespace(embeddings=[SimpleNamespace(values=[1.0, 0.0])]),
        ))
        with patch.object(llm_client, "_client", return_value=fake):
            self.assertEqual(llm_client.semantic_similarity(TEXT, SIMPLIFIED), 1.0)

    def test_embedding_texts_are_sent_in_separate_requests(self):
        # gemini-embedding-2-preview merges a list of texts into ONE vector, so each
        # text must be embedded on its own.
        requests = []

        def embed_content(**kwargs):
            requests.append(kwargs["contents"])
            vector = [1.0, 0.0] if kwargs["contents"] == TEXT else [0.0, 1.0]
            return SimpleNamespace(embeddings=[SimpleNamespace(values=vector)])

        fake = SimpleNamespace(models=SimpleNamespace(embed_content=embed_content))
        with patch.object(llm_client, "_client", return_value=fake):
            score = llm_client.semantic_similarity(TEXT, SIMPLIFIED)
        self.assertEqual(requests, [TEXT, SIMPLIFIED])
        self.assertAlmostEqual(score, 0.5)  # orthogonal vectors: cosine 0 -> (0 + 1) / 2

    def test_unexpected_embedding_count_is_metric_unavailable(self):
        for embeddings in ([], [SimpleNamespace(values=[1.0]), SimpleNamespace(values=[1.0])], None):
            with self.subTest(count=None if embeddings is None else len(embeddings)):
                fake = SimpleNamespace(models=SimpleNamespace(
                    embed_content=lambda **kwargs: SimpleNamespace(embeddings=embeddings),
                ))
                with patch.object(llm_client, "_client", return_value=fake):
                    with self.assertRaises(LLMError) as raised:
                        llm_client.semantic_similarity(TEXT, SIMPLIFIED)
                self.assertEqual(raised.exception.code, "METRIC_UNAVAILABLE")

    def test_429_with_retry_delay_gives_seconds_and_a_clear_message(self):
        error = Exception("429 RESOURCE_EXHAUSTED {'retryDelay': '34s'} private details")
        error.code = 429
        mapped = llm_client._safe_provider_error(error)
        self.assertEqual(mapped.code, "RATE_LIMIT")
        self.assertEqual(mapped.retry_after, 34.0)
        self.assertFalse(mapped.daily)
        self.assertIn("34 seconds", mapped.public_message)
        self.assertNotIn("private details", mapped.public_message)

    def test_429_with_fractional_delay_is_rounded_up(self):
        error = Exception("Please retry in 34.5s.")
        error.code = 429
        self.assertIn("35 seconds", llm_client._safe_provider_error(error).public_message)

    def test_429_daily_quota_is_flagged(self):
        error = Exception("Quota exceeded for metric GenerateRequestsPerDayPerProjectPerModel retryDelay 20s")
        error.code = 429
        mapped = llm_client._safe_provider_error(error)
        self.assertTrue(mapped.daily)
        self.assertIn("daily quota", mapped.public_message)

    def test_429_without_details_still_gives_a_clear_message(self):
        error = Exception("quota")
        error.code = 429
        mapped = llm_client._safe_provider_error(error)
        self.assertIsNone(mapped.retry_after)
        self.assertIn("about a minute", mapped.public_message)

    def test_server_overload_is_reported_with_status_and_logged_without_provider_text(self):
        error = Exception("private provider response")
        error.code = 503
        with self.assertLogs("pipeline.llm_client", level="WARNING") as logs:
            mapped = llm_client._safe_provider_error(error)
        self.assertEqual(mapped.code, "API_ERROR")
        self.assertIn("503", mapped.public_message)
        self.assertNotIn("private provider response", mapped.public_message)
        self.assertIn("status=503", logs.output[0])
        self.assertNotIn("private provider response", logs.output[0])


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.key_patch = patch.dict(os.environ, {"GEMINI_API_KEY": "test-key", "SIMPLIFIER_MAX_ATTEMPTS": "3"})
        self.key_patch.start()
        self.addCleanup(self.key_patch.stop)
        self.sleep_patch = patch.object(api, "_sleep")  # keep retry tests fast
        self.sleep = self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

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

    def test_transient_errors_pause_between_retries_but_not_after_the_last(self):
        with patch.object(api, "generate_text", side_effect=LLMError("API_ERROR", "Unavailable.")):
            api.simplify_text(TEXT, "Beginner")
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1.0, 2.0])

    def test_all_retries_share_one_budget_of_three_requests(self):
        busy = LLMError("API_ERROR", "Unavailable.")
        failed = [{"check": "facts", "status": "FAIL", "explanation": "Added claim."}]
        # Two temporary errors use two of the three requests, leaving one real attempt.
        with patch.object(api, "generate_text", side_effect=[busy, busy, "first rewrite", SIMPLIFIED]) as generate, patch.object(
            api, "verify", side_effect=[failed]
        ), patch.object(api, "semantic_similarity", return_value=0.8):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(result["verification_status"], "FAIL")
        self.assertEqual(result["simplified_text"], "first rewrite")

    def test_a_mix_of_errors_never_exceeds_the_request_cap(self):
        short_limit = LLMError("RATE_LIMIT", "Limited.", retry_after=2.0)
        errors = [LLMError("API_TIMEOUT", "Timed out."), short_limit, LLMError("API_ERROR", "Unavailable."), short_limit]
        with patch.object(api, "generate_text", side_effect=errors) as generate:
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(generate.call_count, 3)
        self.assertEqual(result["attempts"], 3)
        self.assertEqual(len(result["errors"]), 1)  # only the error we gave up on is reported

    def test_the_request_cap_can_be_lowered_with_an_environment_variable(self):
        with patch.dict(os.environ, {"SIMPLIFIER_MAX_ATTEMPTS": "1"}), patch.object(
            api, "generate_text", side_effect=LLMError("API_ERROR", "Unavailable.")
        ) as generate:
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result["attempts"], 1)
        self.sleep.assert_not_called()

    def test_non_transient_errors_do_not_pause_or_retry(self):
        with patch.object(api, "generate_text", side_effect=LLMError("API_AUTH_ERROR", "Rejected.")) as generate:
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(generate.call_count, 1)
        self.assertEqual(result["attempts"], 1)
        self.sleep.assert_not_called()

    def test_generic_api_error_has_safe_error_and_is_retried(self):
        with patch.object(api, "generate_text", side_effect=LLMError("API_ERROR", "Unavailable.")):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(result["errors"][0]["code"], "API_ERROR")
        self.assertEqual(result["attempts"], 3)

    def test_short_per_minute_limit_is_waited_out_once_and_recovers_silently(self):
        limited = LLMError("RATE_LIMIT", "Limited.", retry_after=5.0)
        with patch.object(api, "generate_text", side_effect=[limited, SIMPLIFIED]) as generate, patch.object(
            api, "verify", side_effect=passing_checks
        ), patch.object(api, "semantic_similarity", return_value=0.8):
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result["verification_status"], "PASS")
        self.assertEqual(result["errors"], [])  # the recovered error is not reported
        self.assertEqual(result["attempts"], 2)
        self.sleep.assert_called_once_with(6.0)

    def test_per_minute_limit_is_waited_out_only_once(self):
        limited = LLMError("RATE_LIMIT", "Limited.", retry_after=5.0)
        with patch.object(api, "generate_text", side_effect=limited) as generate:
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(generate.call_count, 2)
        self.assertEqual(result["errors"][0]["code"], "RATE_LIMIT")

    def test_long_wait_and_daily_quota_are_not_retried(self):
        for error in (
            LLMError("RATE_LIMIT", "Limited.", retry_after=60.0),
            LLMError("RATE_LIMIT", "Daily.", retry_after=5.0, daily=True),
        ):
            with self.subTest(daily=error.daily), patch.object(api, "generate_text", side_effect=error) as generate:
                result = api.simplify_text(TEXT, "Beginner")
            self.assertEqual(generate.call_count, 1)
            self.assertEqual(result["errors"][0]["code"], "RATE_LIMIT")
        self.sleep.assert_not_called()

    def test_rate_limit_is_not_retried_quickly(self):
        with patch.object(api, "generate_text", side_effect=LLMError("RATE_LIMIT", "Rate limited.")) as generate:
            result = api.simplify_text(TEXT, "Beginner")
        self.assertEqual(result["errors"][0]["code"], "RATE_LIMIT")
        self.assertEqual(result["attempts"], 1)
        self.assertEqual(generate.call_count, 1)
        self.sleep.assert_not_called()

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
