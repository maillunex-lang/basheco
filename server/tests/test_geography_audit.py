"""Geography audit is deterministic, read-only, and fail-closed."""
import unittest
from basheco.geography_audit import audit


class GeographyAuditTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.report = audit()

    def test_all_candidates_screened_and_no_publication_clearance(self):
        report = self.report
        self.assertEqual(report["candidate_count"], 252)
        self.assertEqual(len(report["locations"]), report["candidate_count"])
        self.assertEqual(report["safe_to_publish"], 0)
        self.assertTrue(all(not x["safe_to_publish"] for x in report["locations"]))
        self.assertTrue(all(not x["water_verified"] and not x["terrain_verified"]
                            and not x["land_rights_verified"] for x in report["locations"]))

    def test_boundary_screening_deterministic(self):
        self.assertEqual(self.report, audit())
        self.assertEqual(self.report["boundary_sample_pass"]
                         + self.report["boundary_conflict"],
                         self.report["candidate_count"])
        self.assertTrue(all(x["sampled_points"] > 0 for x in self.report["locations"]))