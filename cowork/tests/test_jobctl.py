from __future__ import annotations

import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / "zed-seo-operator"
    / "scripts"
    / "jobctl.py"
)
SPEC = importlib.util.spec_from_file_location("jobctl", MODULE_PATH)
assert SPEC and SPEC.loader
jobctl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(jobctl)


class JobControlTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.workspace = self.root / "workspace"
        jobctl.init_workspace(self.workspace)
        self.client = "vitale-vv"
        self.profile_source = self.root / "profile.json"
        self.profile_source.write_text(
            json.dumps(
                {
                    "business_name": "Vitale V&V",
                    "domain": "vitale.example",
                    "services": ["vascular care"],
                    "locations": ["Tampa, FL"],
                    "specialties": ["vascular surgery"],
                    "negative_keywords": ["jobs"],
                    "negative_categories": ["unrelated specialties"],
                    "url_inventory": [
                        {
                            "url": "https://vitale.example/vascular-care",
                            "title": "Vascular Care",
                            "summary": "Vascular care services in Tampa.",
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        jobctl.save_client(self.workspace, self.client, self.profile_source)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_csv(self, name: str, rows: list[dict[str, str]]) -> Path:
        path = self.root / name
        fieldnames = list(rows[0])
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def write_json(self, name: str, payload: object) -> Path:
        path = self.root / name
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    def test_cleaning_checkpoints_resume_export_and_redaction(self) -> None:
        source = self.write_csv(
            "keywords.csv",
            [
                {"keyword": "vascular doctor tampa", "volume": "100"},
                {"keyword": "vascular jobs", "volume": "20"},
                {"keyword": "vein treatment tampa", "volume": "80"},
                {"keyword": "cardiology miami", "volume": "40"},
                {"keyword": "vascular specialist", "volume": "60"},
            ],
        )
        summary = jobctl.start_job(
            self.workspace, self.client, "cleaning", source, batch_size=2
        )
        job = Path(summary["job"])
        self.assertEqual(summary["auto_removed_rows"], 1)
        self.assertEqual(summary["total_batches"], 2)
        duplicate_start = jobctl.start_job(
            self.workspace, self.client, "cleaning", source, batch_size=2
        )
        self.assertTrue(duplicate_start["resumed_existing"])
        self.assertEqual(duplicate_start["job"], str(job))

        prepared = jobctl.prepare_batch(job)
        self.assertEqual(prepared["prepared_batch"], 1)
        self.assertTrue(Path(prepared["prompt"]).is_file())

        wrong = self.write_json(
            "wrong.json",
            {
                "classifications": [
                    {
                        "keyword": "vein treatment tampa",
                        "classification": "KEEP",
                        "confidence": 90,
                        "reason": "Relevant",
                    }
                ]
            },
        )
        with self.assertRaises(jobctl.JobError):
            jobctl.record_batch(job, 1, wrong)
        self.assertEqual(jobctl.job_summary(job)["completed_batches"], 0)

        first = self.write_json(
            "first.json",
            {
                "classifications": [
                    {
                        "keyword": "vascular doctor tampa",
                        "classification": "KEEP",
                        "confidence": 96,
                        "reason": "Direct service and location match",
                    },
                    {
                        "keyword": "vein treatment tampa",
                        "classification": "KEEP",
                        "confidence": 82,
                        "reason": "Related vascular treatment in served location",
                    },
                ]
            },
        )
        recorded = jobctl.record_batch(job, 1, first)
        self.assertEqual(recorded["next_batch"], 2)

        fake_google_key = "AI" + "za" + ("x" * 35)
        failed = jobctl.fail_batch(
            job,
            2,
            f"provider rejected api_key=supersecret and {fake_google_key}",
        )
        incident = json.loads(Path(failed["incident"]).read_text(encoding="utf-8"))
        self.assertNotIn("supersecret", incident["error"])
        self.assertNotIn("AIzaSy", incident["error"])
        self.assertIn("[REDACTED]", incident["error"])

        second = self.write_json(
            "second.json",
            {
                "classifications": [
                    {
                        "keyword": "cardiology miami",
                        "classification": "REMOVE",
                        "confidence": 99,
                        "reason": "Wrong specialty and location",
                    },
                    {
                        "keyword": "vascular specialist",
                        "classification": "UNSURE",
                        "confidence": 68,
                        "reason": "Relevant specialty but no location signal",
                    },
                ]
            },
        )
        complete = jobctl.record_batch(job, 2, second)
        self.assertEqual(complete["status"], "complete")
        exported = jobctl.export_job(job)
        self.assertEqual(exported["exported_rows"], 5)

        with Path(exported["exports"]["all"]).open(encoding="utf-8", newline="") as handle:
            all_rows = list(csv.DictReader(handle))
        self.assertEqual([row["keyword"] for row in all_rows], [
            "vascular doctor tampa",
            "vascular jobs",
            "vein treatment tampa",
            "cardiology miami",
            "vascular specialist",
        ])
        self.assertEqual(all_rows[1]["classification"], "REMOVE")
        self.assertEqual(all_rows[1]["confidence"], "100")
        self.assertTrue(jobctl.doctor(self.workspace)["healthy"])
        self.assertEqual(jobctl.doctor(self.workspace)["incomplete_jobs"], [])

    def test_mapping_rejects_invented_url_and_preserves_source_url(self) -> None:
        source = self.write_csv(
            "mapping.csv",
            [
                {
                    "keyword": "vascular care tampa",
                    "volume": "120",
                    "url": "https://semrush.example/source-result",
                }
            ],
        )
        summary = jobctl.start_job(
            self.workspace, self.client, "mapping", source, batch_size=1
        )
        job = Path(summary["job"])
        invented = self.write_json(
            "invented.json",
            {
                "mappings": [
                    {
                        "keyword": "vascular care tampa",
                        "url": "https://vitale.example/invented",
                        "confidence": 90,
                        "intent": "transactional",
                        "notes": "Looks relevant",
                    }
                ]
            },
        )
        with self.assertRaises(jobctl.JobError):
            jobctl.record_batch(job, 1, invented)

        valid = self.write_json(
            "mapping-valid.json",
            {
                "mappings": [
                    {
                        "keyword": "vascular care tampa",
                        "url": "https://vitale.example/vascular-care",
                        "confidence": 95,
                        "intent": "transactional",
                        "notes": "Exact service and location match",
                    }
                ]
            },
        )
        jobctl.record_batch(job, 1, valid)
        exported = jobctl.export_job(job)
        with Path(exported["exports"]["mapping"]).open(
            encoding="utf-8", newline=""
        ) as handle:
            row = next(csv.DictReader(handle))
        self.assertEqual(row["url"], "https://semrush.example/source-result")
        self.assertEqual(row["mapped_url"], "https://vitale.example/vascular-care")
        self.assertEqual(row["recommendation"], "Existing URL")

    def test_doctor_detects_normalized_input_mutation(self) -> None:
        source = self.write_csv("one.csv", [{"keyword": "vascular care"}])
        summary = jobctl.start_job(
            self.workspace, self.client, "cleaning", source, batch_size=1
        )
        job = Path(summary["job"])
        (job / "input.csv").write_text("keyword\nchanged\n", encoding="utf-8")
        report = jobctl.doctor(self.workspace)
        self.assertFalse(report["healthy"])
        self.assertIn("Normalized input changed", report["problems"][0])

    def test_all_negative_keywords_complete_without_model_batches(self) -> None:
        source = self.write_csv(
            "negative.csv",
            [{"keyword": "vascular jobs"}, {"keyword": "medical jobs"}],
        )
        summary = jobctl.start_job(
            self.workspace, self.client, "cleaning", source, batch_size=100
        )
        self.assertEqual(summary["status"], "complete")
        self.assertEqual(summary["total_batches"], 0)
        self.assertEqual(summary["progress_percent"], 100.0)
        exported = jobctl.export_job(Path(summary["job"]))
        self.assertEqual(exported["exported_rows"], 2)

    def test_40k_job_resumes_from_batch_43_without_source_reupload(self) -> None:
        source = self.root / "forty-thousand.csv"
        with source.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["keyword", "volume"])
            writer.writeheader()
            for index in range(40_000):
                writer.writerow(
                    {"keyword": f"vascular keyword {index:05d}", "volume": str(index)}
                )

        summary = jobctl.start_job(
            self.workspace, self.client, "cleaning", source, batch_size=100
        )
        job = Path(summary["job"])
        self.assertEqual(summary["total_rows"], 40_000)
        self.assertEqual(summary["total_batches"], 400)

        for batch_number in range(1, 43):
            input_rows = jobctl.read_json(
                jobctl.batch_input_path(job, batch_number)
            )["rows"]
            result = self.write_json(
                f"large-result-{batch_number:04d}.json",
                {
                    "classifications": [
                        {
                            "keyword": row["keyword"],
                            "classification": "KEEP",
                            "confidence": 90,
                            "reason": "Synthetic scale-test result",
                        }
                        for row in input_rows
                    ]
                },
            )
            jobctl.record_batch(job, batch_number, result)

        stopped = jobctl.fail_batch(job, 43, "Synthetic interruption")
        self.assertEqual(stopped["completed_batches"], 42)
        self.assertEqual(stopped["next_batch"], 43)
        self.assertTrue((job / "input.csv").is_file())

        resumed = jobctl.prepare_batch(job)
        self.assertEqual(resumed["prepared_batch"], 43)
        self.assertTrue(Path(resumed["prompt"]).is_file())
        self.assertTrue(jobctl.doctor(self.workspace)["healthy"])


if __name__ == "__main__":
    unittest.main()
