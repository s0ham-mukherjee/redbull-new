"""Output-contract tests: labelling, evidence linkage, comparison semantics."""

import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest

from helpers import minimal_valid_config, mutated_config

from sakurascore_sim import run_simulation
from sakurascore_sim.simulation.results import validate_output


class TestOutputContract(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.output = run_simulation(minimal_valid_config())

    def test_required_top_level_keys(self):
        for key in ("schema_version", "ip_id", "experiment_id", "simulation_status",
                    "engine", "scenarios", "comparisons", "assumptions",
                    "source_references", "limitations", "run_metadata"):
            self.assertIn(key, self.output)

    def test_scenario_metrics_labelled_simulated(self):
        for sc in self.output["scenarios"]:
            self.assertEqual(sc["data_label"], "simulated")
            self.assertEqual(sc["totals"]["data_label"], "simulated")

    def test_source_references_have_provenance(self):
        for ref in self.output["source_references"]:
            self.assertTrue(ref["url"].startswith(("http://", "https://")))
            self.assertIn(ref["label"], ("observed", "inferred"))
            self.assertIn(ref["quality"], ("high", "medium", "low"))
            self.assertTrue(ref.get("date"))

    def test_assumptions_carry_labels_and_values(self):
        ids = {a["id"] for a in self.output["assumptions"]}
        self.assertIn("dub-lift", ids)
        for a in self.output["assumptions"]:
            self.assertIn(a["data_label"], ("observed", "inferred", "simulated", "unknown"))
            self.assertTrue(a["statement"])
        dub = next(a for a in self.output["assumptions"] if a["id"] == "dub-lift")
        self.assertEqual(dub["value"]["dub_lift"], self.output and 1.6)

    def test_assumption_evidence_links_resolve(self):
        valid_ids = {r["id"] for r in self.output["source_references"]}
        for a in self.output["assumptions"]:
            for ev in a.get("evidence_ids", []):
                self.assertIn(ev, valid_ids,
                              f"assumption {a['id']} cites unknown evidence {ev}")

    def test_comparison_semantics_and_drivers(self):
        cmp = self.output["comparisons"][0]
        self.assertEqual(cmp["baseline_id"], "baseline")
        self.assertEqual(cmp["scenario_id"], "dub")
        self.assertTrue(cmp["paired_seeds"])
        m = cmp["metrics"]["engagement_rate"]
        self.assertEqual(
            round(m["comparison_mean"] - m["baseline_mean"], 6), m["delta_mean"])
        # drivers must name the differing parameter
        params = {d["parameter"] for d in cmp["drivers"]}
        self.assertIn("languages_available", params)
        driver = next(d for d in cmp["drivers"] if d["parameter"] == "languages_available")
        self.assertEqual(driver["added"], ["hi", "ta"])

    def test_per_segment_delta_is_bounded(self):
        cmp = self.output["comparisons"][0]
        for sid, delta in cmp["per_segment_engagement_delta"].items():
            self.assertLessEqual(abs(delta["engagement_rate_delta_mean"]), 1.0)

    def test_limitations_flag_non_predictive_use(self):
        lim = {l["id"]: l for l in self.output["limitations"]}
        self.assertIn("not-a-forecast", lim)
        self.assertEqual(lim["not-a-forecast"]["severity"], "critical")

    def test_run_metadata_completeness(self):
        rm = self.output["run_metadata"]
        self.assertEqual(rm["agent_count"], 12)
        self.assertEqual(rm["rounds"], 4)
        self.assertIn(42, rm["seeds"])
        self.assertTrue(rm["config_hash"])
        self.assertEqual(rm["engine"], "sakura-abm")
        self.assertIn("rng", rm)

    def test_validate_output_detects_corruption(self):
        broken = json.loads(json.dumps(self.output))
        del broken["assumptions"]
        problems = validate_output(broken)
        self.assertTrue(problems)

        broken2 = json.loads(json.dumps(self.output))
        broken2["scenarios"][0]["data_label"] = "observed"  # engine output is never 'observed'
        problems2 = validate_output(broken2)
        self.assertTrue(problems2)

    def test_counterfactual_labelling_flows_through(self):
        for sc in self.output["scenarios"]:
            if sc["id"] == "baseline":
                self.assertTrue(sc["counterfactual"])


if __name__ == "__main__":
    unittest.main()
