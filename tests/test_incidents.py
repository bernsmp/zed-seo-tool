import unittest
from unittest.mock import patch

from utils import incidents


class IncidentSanitizationTests(unittest.TestCase):
    def test_api_keys_are_redacted(self):
        message = (
            "Gemini failed with AIzaSyExampleSecretValue123456789 and "
            "Authorization: BearerSecretValue123456789"
        )

        sanitized = incidents.sanitize_error_message(message)

        self.assertNotIn("AIzaSyExampleSecretValue123456789", sanitized)
        self.assertNotIn("BearerSecretValue123456789", sanitized)
        self.assertEqual(sanitized.count("[REDACTED]"), 2)

    def test_report_contains_diagnostics_without_job_content(self):
        report = incidents.build_incident_report(
            client_slug="test-client",
            job_type="keyword_cleaning",
            failed_batch=45,
            processed_batches=44,
            total_batches=302,
            saved_result_count=4625,
            error_message=(
                "Anthropic credit balance is too low. "
                "Gemini response was malformed JSON."
            ),
        )

        self.assertEqual(report["error_category"], "structured_output")
        self.assertTrue(report["auto_fix_eligible"])
        self.assertEqual(report["provider_signals"], ["anthropic", "gemini"])
        self.assertEqual(report["failed_batch"], 45)
        self.assertEqual(report["saved_result_count"], 4625)
        self.assertNotIn("keywords", report)
        self.assertNotIn("results", report)
        self.assertNotIn("prompt", report)


class IncidentDeliveryTests(unittest.TestCase):
    def test_remote_delivery_status_is_returned(self):
        with patch.object(
            incidents,
            "save_incident_report",
            return_value=("local-path", True),
        ) as save:
            report = incidents.report_incident(
                client_slug="test-client",
                job_type="keyword_mapping",
                failed_batch=14,
                processed_batches=13,
                total_batches=20,
                saved_result_count=1300,
                error_message="Gemini response was truncated",
            )

        self.assertTrue(report["remote_saved"])
        self.assertEqual(report["error_category"], "output_truncation")
        save.assert_called_once()


if __name__ == "__main__":
    unittest.main()
