import unittest
from copy import deepcopy
from basheco.location_generator import build, PILOT
from basheco.generated_storage import prepare, import_unpublished


class GeneratedStorageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = build()

    def test_full_bundle(self):
        prepared = prepare(self.bundle)
        self.assertEqual(len(prepared), len(self.bundle["selection"]))
        self.assertLessEqual(len(prepared), 315)
        self.assertEqual(len({item["id"] for item in prepared}), len(prepared))
        self.assertTrue(all(item["chunks"] for item in prepared))

    def test_deterministic_dry_run_no_database(self):
        self.assertEqual(import_unpublished(self.bundle),
                         {"candidates": len(self.bundle["locations"]), "inserted": 0,
                          "unchanged": 0, "dry_run": True})

    def test_cap_cannot_be_bypassed(self):
        broken = deepcopy(self.bundle)
        extra = deepcopy(broken["selection"][0])
        extra["settlement_id"] = "S00000000001"
        broken["selection"].append(extra)
        with self.assertRaises(ValueError):
            prepare(broken)

    def test_overlap_is_rejected(self):
        broken = deepcopy(self.bundle)
        broken["locations"][0]["objects"].append(deepcopy(broken["locations"][0]["objects"][0]))
        with self.assertRaises(ValueError):
            prepare(broken)

    def test_publication_is_not_automatic(self):
        self.assertEqual(self.bundle["published_settlement_ids"], [PILOT])
        with self.assertRaises(ValueError):
            broken = deepcopy(self.bundle)
            broken["published_settlement_ids"].append("S80745000001")
            prepare(broken)


if __name__ == "__main__":
    unittest.main()