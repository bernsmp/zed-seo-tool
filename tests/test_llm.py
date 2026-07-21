import json
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from utils import llm


class AnthropicOutputLimitTests(unittest.TestCase):
    def test_default_output_limit_handles_full_keyword_batch(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(llm._max_output_tokens(), 8192)

    def test_truncated_response_raises_actionable_error(self):
        response = SimpleNamespace(
            stop_reason="max_tokens",
            usage=None,
            content=[SimpleNamespace(type="text", text='{"classifications": [')],
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(create=Mock(return_value=response))
        )

        with patch.object(llm, "_get_client", return_value=client):
            with self.assertRaisesRegex(
                RuntimeError,
                "truncated after reaching the 8192-token output limit",
            ):
                llm._chat_with_anthropic(
                    "claude-haiku-4-5",
                    [{"role": "user", "content": "Return JSON"}],
                    task="classify_keywords",
                )

        client.messages.create.assert_called_once()
        self.assertEqual(client.messages.create.call_args.kwargs["max_tokens"], 8192)

    def test_complete_response_uses_output_limit_and_returns_text(self):
        response = SimpleNamespace(
            stop_reason="end_turn",
            usage=None,
            content=[SimpleNamespace(type="text", text='{"ok": true}')],
        )
        client = SimpleNamespace(
            messages=SimpleNamespace(create=Mock(return_value=response))
        )

        with patch.dict(os.environ, {}, clear=True):
            with patch.object(llm, "_get_client", return_value=client):
                result = llm._chat_with_anthropic(
                    "claude-haiku-4-5",
                    [{"role": "user", "content": "Return JSON"}],
                )

        self.assertEqual(result, '{"ok": true}')
        self.assertEqual(client.messages.create.call_args.kwargs["max_tokens"], 8192)


class KeywordBatchValidationTests(unittest.TestCase):
    def test_incomplete_classification_batch_is_rejected(self):
        partial_json = (
            '{"classifications": [{"keyword": "vein clinic", '
            '"classification": "KEEP", "confidence": 95, '
            '"reason": "Relevant service"}]}'
        )

        with patch.object(llm, "_chat", return_value=partial_json):
            with self.assertRaisesRegex(
                RuntimeError,
                "LLM returned 1 of 2 keyword classifications",
            ):
                llm.classify_keywords(
                    {"business_name": "Test Clinic"},
                    [{"keyword": "vein clinic"}, {"keyword": "spider veins"}],
                )


class KeywordMappingValidationTests(unittest.TestCase):
    @staticmethod
    def _mapping(keyword):
        return {
            "keyword": keyword,
            "url": "https://example.com/veins",
            "confidence": 90,
            "intent": "transactional",
            "notes": "Relevant service page",
        }

    def test_large_mapping_batch_is_split_into_safe_requests(self):
        keywords = [{"keyword": f"keyword {index}"} for index in range(100)]
        responses = [
            json.dumps(
                {"mappings": [self._mapping(item["keyword"]) for item in keywords[:50]]}
            ),
            json.dumps(
                {"mappings": [self._mapping(item["keyword"]) for item in keywords[50:]]}
            ),
        ]

        with patch.object(llm, "_chat", side_effect=responses) as chat:
            mappings = llm.map_keywords(
                {"business_name": "Test Clinic"},
                keywords,
                [{"url": "https://example.com/veins", "title": "Vein Care"}],
            )

        self.assertEqual(chat.call_count, 2)
        self.assertEqual(len(mappings), 100)
        self.assertEqual(
            [mapping["keyword"] for mapping in mappings],
            [item["keyword"] for item in keywords],
        )

    def test_duplicate_keywords_are_mapped_once_and_reexpanded(self):
        keywords = [
            {"keyword": "vein clinic"},
            {"keyword": "spider veins"},
            {"keyword": "vein clinic"},
        ]
        response = json.dumps(
            {
                "mappings": [
                    self._mapping("vein clinic"),
                    self._mapping("spider veins"),
                ]
            }
        )

        with patch.object(llm, "_chat", return_value=response) as chat:
            mappings = llm.map_keywords(
                {"business_name": "Test Clinic"},
                keywords,
                [{"url": "https://example.com/veins", "title": "Vein Care"}],
            )

        chat.assert_called_once()
        self.assertEqual(
            [mapping["keyword"] for mapping in mappings],
            [item["keyword"] for item in keywords],
        )

    def test_final_partial_mapping_request_preserves_order(self):
        keywords = [{"keyword": f"keyword {index}"} for index in range(51)]
        responses = [
            json.dumps(
                {"mappings": [self._mapping(item["keyword"]) for item in keywords[:50]]}
            ),
            json.dumps({"mappings": [self._mapping(keywords[50]["keyword"])]}),
        ]

        with patch.object(llm, "_chat", side_effect=responses) as chat:
            mappings = llm.map_keywords(
                {"business_name": "Test Clinic"},
                keywords,
                [{"url": "https://example.com/veins", "title": "Vein Care"}],
            )

        self.assertEqual(chat.call_count, 2)
        self.assertEqual(
            [mapping["keyword"] for mapping in mappings],
            [item["keyword"] for item in keywords],
        )

    def test_second_mapping_request_failure_returns_no_partial_result(self):
        keywords = [{"keyword": f"keyword {index}"} for index in range(100)]
        first_response = json.dumps(
            {"mappings": [self._mapping(item["keyword"]) for item in keywords[:50]]}
        )

        with patch.object(
            llm,
            "_chat",
            side_effect=[first_response, RuntimeError("provider unavailable")],
        ):
            with self.assertRaisesRegex(RuntimeError, "provider unavailable"):
                llm.map_keywords(
                    {"business_name": "Test Clinic"},
                    keywords,
                    [{"url": "https://example.com/veins", "title": "Vein Care"}],
                )

    def test_incomplete_mapping_request_is_rejected(self):
        keywords = [{"keyword": "vein clinic"}, {"keyword": "spider veins"}]
        response = json.dumps({"mappings": [self._mapping("vein clinic")]})

        with patch.object(llm, "_chat", return_value=response):
            with self.assertRaisesRegex(
                RuntimeError,
                "LLM returned 1 of 2 keyword mappings",
            ):
                llm.map_keywords(
                    {"business_name": "Test Clinic"},
                    keywords,
                    [{"url": "https://example.com/veins", "title": "Vein Care"}],
                )

    def test_reordered_mapping_request_is_rejected(self):
        keywords = [{"keyword": "vein clinic"}, {"keyword": "spider veins"}]
        response = json.dumps(
            {
                "mappings": [
                    self._mapping("spider veins"),
                    self._mapping("vein clinic"),
                ]
            }
        )

        with patch.object(llm, "_chat", return_value=response):
            with self.assertRaisesRegex(
                RuntimeError,
                "keywords in a different order",
            ):
                llm.map_keywords(
                    {"business_name": "Test Clinic"},
                    keywords,
                    [{"url": "https://example.com/veins", "title": "Vein Care"}],
                )

    def test_invalid_mapping_payload_is_rejected(self):
        response = json.dumps({"mappings": {}})

        with patch.object(llm, "_chat", return_value=response):
            with self.assertRaisesRegex(RuntimeError, "invalid keyword mapping payload"):
                llm.map_keywords(
                    {"business_name": "Test Clinic"},
                    [{"keyword": "vein clinic"}],
                    [{"url": "https://example.com/veins", "title": "Vein Care"}],
                )


class MappingCostEstimateTests(unittest.TestCase):
    def test_mapping_estimate_counts_internal_requests(self):
        with patch.object(llm, "_model", return_value="anthropic/claude-haiku-4-5"):
            one_progress_batch = llm.estimate_cost(100, "mapping")
            carlos_run = llm.estimate_cost(2621, "mapping")

        self.assertEqual(one_progress_batch["batches"], 1)
        self.assertEqual(one_progress_batch["requests"], 2)
        self.assertEqual(carlos_run["batches"], 27)
        self.assertEqual(carlos_run["requests"], 53)


if __name__ == "__main__":
    unittest.main()
