"""Fail-closed land constraint decisions and complete cell coverage."""
import unittest

from basheco.land_constraints import (
    REQUIRED_LAYERS, SCHEMA, assess_cells, footprint_cells,
)
from basheco.location_generator import choose_settlements, generate


class LandConstraintTests(unittest.TestCase):
    def setUp(self):
        self.cells = {(10, -20), (11, -20)}

    def test_missing_evidence_never_means_buildable(self):
        report = assess_cells(self.cells, None)
        self.assertFalse(report["safe_to_build"])
        self.assertEqual(report["decision"], "unknown")
        self.assertEqual(report["unknown_checks"], 2 * len(REQUIRED_LAYERS))

    def test_incomplete_coverage_is_unknown(self):
        report = assess_cells(self.cells, {
            "schema": SCHEMA, "source": "test fixture", "source_version": "1",
            "layers": {layer: {"10,-20": "clear"} for layer in REQUIRED_LAYERS}})
        self.assertFalse(report["safe_to_build"])
        self.assertEqual(report["unknown_checks"], len(REQUIRED_LAYERS))

    def test_explicit_water_or_protection_block(self):
        layers = {layer: {f"{x},{y}": "clear" for x, y in self.cells}
                  for layer in REQUIRED_LAYERS}
        layers["water"]["10,-20"] = "blocked"
        layers["protected_area"]["11,-20"] = "blocked"
        report = assess_cells(self.cells, {
            "schema": SCHEMA, "source": "test fixture", "source_version": "1",
            "layers": layers})
        self.assertFalse(report["safe_to_build"])
        self.assertEqual(report["decision"], "blocked")
        self.assertEqual(report["blocked_checks"], 2)

    def test_all_clear_fixture_only_not_publication_authorization(self):
        layers = {layer: {f"{x},{y}": "clear" for x, y in self.cells}
                  for layer in REQUIRED_LAYERS}
        report = assess_cells(self.cells, {
            "schema": SCHEMA, "source": "synthetic test fixture", "source_version": "1",
            "layers": layers})
        self.assertTrue(report["safe_to_build"])
        self.assertEqual(report["clear_checks"], 8)

    def test_invalid_values_and_provenance_fail_closed(self):
        report = assess_cells(self.cells, {
            "schema": SCHEMA,
            "layers": {layer: {f"{x},{y}": "clear" for x, y in self.cells}
                       for layer in REQUIRED_LAYERS}})
        self.assertFalse(report["safe_to_build"])
        self.assertIn("missing_source", report["reasons"])

    def test_generated_footprints_are_unique(self):
        record = choose_settlements()[0]
        occupied = footprint_cells(generate(record))
        self.assertGreater(len(occupied), 61)
        self.assertEqual(len(occupied), len(set(occupied)))

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):
            footprint_cells({"objects": [
                {"cell": [0, 0], "size": [2, 1]},
                {"cell": [1, 0], "size": [1, 1]}]})