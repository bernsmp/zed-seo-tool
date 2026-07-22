import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from utils import data


class MappingCheckpointSelectionTests(unittest.TestCase):
    @staticmethod
    def _checkpoint(
        processed_batches,
        result_count,
        *,
        source_keyword_count=2621,
        total_batches=27,
        completed=False,
        batch_size=None,
    ):
        meta = {
            "client_slug": "vitale-vein-vascular",
            "source_keyword_count": source_keyword_count,
            "processed_batches": processed_batches,
            "total_batches": total_batches,
            "completed": completed,
        }
        if batch_size is not None:
            meta["batch_size"] = batch_size
        return {
            "results": [{"keyword": f"keyword {index}"} for index in range(result_count)],
            "meta": meta,
        }

    def test_mapping_selector_falls_back_to_last_complete_checkpoint(self):
        incomplete_batch_13 = self._checkpoint(processed_batches=13, result_count=1269)
        complete_batch_9 = self._checkpoint(processed_batches=9, result_count=900)

        selected = data._select_best_mapping_result(
            [incomplete_batch_13, complete_batch_9]
        )

        self.assertIs(selected, complete_batch_9)

    def test_mapping_selector_returns_none_when_every_checkpoint_is_inconsistent(self):
        inconsistent = self._checkpoint(processed_batches=13, result_count=1269)

        self.assertIsNone(data._select_best_mapping_result([inconsistent]))

    def test_completed_checkpoint_requires_every_source_row(self):
        incomplete = self._checkpoint(
            processed_batches=27,
            result_count=2620,
            completed=True,
        )
        complete = self._checkpoint(
            processed_batches=27,
            result_count=2621,
            completed=True,
        )

        self.assertIs(data._select_best_mapping_result([incomplete, complete]), complete)

    def test_checkpoint_uses_persisted_non_default_batch_size(self):
        checkpoint = self._checkpoint(
            processed_batches=2,
            result_count=100,
            source_keyword_count=125,
            total_batches=3,
            batch_size=50,
        )

        self.assertIs(data._select_best_mapping_result([checkpoint]), checkpoint)

    def test_final_partial_checkpoint_is_consistent(self):
        checkpoint = self._checkpoint(
            processed_batches=3,
            result_count=125,
            source_keyword_count=125,
            total_batches=3,
            batch_size=50,
        )

        self.assertIs(data._select_best_mapping_result([checkpoint]), checkpoint)

    def test_invalid_remote_mapping_does_not_fall_through_to_stale_local_file(self):
        inconsistent = self._checkpoint(processed_batches=13, result_count=1269)
        stale_local = self._checkpoint(
            processed_batches=27,
            result_count=2621,
            completed=True,
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            client_dir = Path(temp_dir) / "vitale-vein-vascular"
            client_dir.mkdir()
            (client_dir / "mapping_20260720_120000.json").write_text(
                json.dumps(stale_local)
            )

            with patch.object(data, "DATA_DIR", Path(temp_dir)):
                with patch.object(data.db, "is_available", return_value=True):
                    with patch.object(
                        data.db,
                        "load_recent_results",
                        return_value=[inconsistent],
                    ):
                        selected = data.load_latest_results(
                            "vitale-vein-vascular",
                            "mapping",
                        )

        self.assertIsNone(selected)


class CleaningCheckpointReconciliationTests(unittest.TestCase):
    @staticmethod
    def _source(count):
        return [{"keyword": f"keyword {index}"} for index in range(count)]

    @staticmethod
    def _classified(rows):
        return [
            {
                **row,
                "classification": "KEEP",
                "confidence": 90,
                "reason": "Relevant",
            }
            for row in rows
        ]

    def test_duplicate_middle_batch_is_removed_without_losing_later_batches(self):
        auto_removed = [{"keyword": "jobs", "classification": "REMOVE"}]
        source = self._source(500)
        classified = self._classified(source)
        saved = (
            auto_removed
            + classified[:200]
            + classified[100:200]
            + classified[200:500]
        )

        repaired, processed_batches, discarded_rows = data.reconcile_cleaning_checkpoint(
            saved,
            auto_removed,
            source,
            processed_batches=5,
            batch_size=100,
        )

        self.assertEqual(processed_batches, 5)
        self.assertEqual(discarded_rows, 100)
        self.assertEqual(
            [row["keyword"] for row in repaired],
            ["jobs", *[row["keyword"] for row in source]],
        )

    def test_misaligned_checkpoint_rewinds_to_last_verified_batch(self):
        source = self._source(300)
        classified = self._classified(source)
        saved = classified[:100] + [{"keyword": "unexpected"}] * 100

        repaired, processed_batches, discarded_rows = data.reconcile_cleaning_checkpoint(
            saved,
            [],
            source,
            processed_batches=2,
            batch_size=100,
        )

        self.assertEqual(processed_batches, 1)
        self.assertEqual(discarded_rows, 100)
        self.assertEqual(repaired, classified[:100])


if __name__ == "__main__":
    unittest.main()
