"""Checks the administrative catalog export without relying on external services."""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from export_navigation import export


class NavigationCatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.catalog = export()

    def test_complete_registry(self):
        self.assertEqual(len(self.catalog["districts"]), 63)
        self.assertEqual(sum(len(d["locations"]) for d in self.catalog["districts"]), 4561)

    def test_unique_ids(self):
        ids = [s["id"] for d in self.catalog["districts"] for s in d["locations"]]
        self.assertEqual(len(ids), len(set(ids)))

    def test_unsafe_coordinates_not_exposed(self):
        for district in self.catalog["districts"]:
            for location in district["locations"]:
                if location["coordinate_status"] != "inside_municipality":
                    self.assertIsNone(location["cell"])

    def test_deterministic_order(self):
        self.assertEqual(self.catalog, export())


if __name__ == "__main__":
    unittest.main()
