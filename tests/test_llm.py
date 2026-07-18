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


if __name__ == "__main__":
    unittest.main()
