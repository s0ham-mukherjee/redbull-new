"""Runner tests: end-to-end execution, reproducibility, failure handling,
paired monotonicity and the word-of-mouth ablation baseline."""

import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest

from helpers import minimal_valid_config, mutated_config, example_config_path, REPO_ROOT

from sakurascore_sim import ConfigError, run_simulation, run_simulation_from_file
from sakurascore_sim.simulation.results import validate_output
from sakurascore_sim.adapters import abm_engine
from sakurascore_sim.models import validate_input
from sakurascore_sim.research.evidence_loader import merge_evidence


class TestRunner(unittest.TestCase):

    def test_full_example_config_completes(self):
        output = run_simulation_from_file(example_config_path())
        self.assertIn(output["simulation_status"], ("completed", "completed_with_warnings"))
        self.assertEqual(len(output["scenarios"]), 2)
        self.assertEqual(len(output["comparisons"]), 1)
        self.assertEqual(output["comparisons"][0]["baseline_id"], "baseline-subs-only")
        self.assertEqual(output["comparisons"][0]["scenario_id"], "regional-dub")
        problems = validate_output(output)
        self.assertEqual(problems, [], f"output contract problems: {problems}")

    def test_reproducibility_identical_json(self):
        cfg = minimal_valid_config()
        a = run_simulation(cfg)
        b = run_simulation(cfg)
        self.assertEqual(a["simulation_status"], b["simulation_status"])
        # strip volatile metadata before comparing
        for out in (a, b):
            out["run_metadata"].pop("generated_at", None)
            out["run_metadata"].pop("total_duration_ms", None)
            out["run_metadata"].pop("python_version", None)
            out["run_metadata"].pop("platform", None)
            for sc in out["scenarios"]:
                sc.pop("duration_ms", None)
        self.assertEqual(json.dumps(a, sort_keys=True), json.dumps(b, sort_keys=True),
                         "same seed must reproduce identical results")

    def test_paired_monotonicity_across_seeds(self):
        """Engine invariant: with identical marketing and a language superset,
        the dub scenario can never reach/engage FEWER agents than the baseline
        for the same seed (stream-aligned thresholds)."""
        cfg = minimal_valid_config()
        parsed = validate_input(cfg)
        scen = {s.id: s for s in parsed.scenarios}
        for seed in range(1, 31):
            ra = abm_engine.run_scenario(parsed, scen["baseline"], seed)
            rb = abm_engine.run_scenario(parsed, scen["dub"], seed)
            self.assertGreaterEqual(rb["totals"]["reach"], ra["totals"]["reach"],
                                    f"seed {seed}: reach regressed")
            self.assertGreaterEqual(rb["totals"]["engaged"], ra["totals"]["engaged"],
                                    f"seed {seed}: engagement regressed")

    def test_invalid_config_returns_failure_envelope(self):
        cfg = minimal_valid_config()
        cfg["ip_id"] = "INVALID ID"
        output = run_simulation(cfg)  # non-strict: no raise
        self.assertEqual(output["simulation_status"], "failed")
        self.assertTrue(output["errors"])
        self.assertTrue(output["errors"][0]["code"])
        problems = validate_output(output)
        self.assertEqual(problems, [])

    def test_invalid_config_strict_raises(self):
        cfg = minimal_valid_config()
        del cfg["title"]
        with self.assertRaises(ConfigError):
            run_simulation(cfg, strict=True)

    def test_word_of_mouth_ablation_baseline(self):
        """Part 13: compare against a simple baseline. With WOM disabled the
        reach must not exceed the WOM-enabled run (same seed)."""
        base_cfg = minimal_valid_config()
        ablation_cfg = minimal_valid_config()
        ablation_cfg["simulation"]["word_of_mouth_boost"] = 0.0

        pa = validate_input(base_cfg)
        pb = validate_input(ablation_cfg)
        scen = pa.scenarios[0]
        ra = abm_engine.run_scenario(pa, scen, 7)
        rb = abm_engine.run_scenario(pb, scen, 7)
        self.assertGreaterEqual(ra["totals"]["reach"], rb["totals"]["reach"],
                                "disabling word-of-mouth must not increase reach")
        self.assertGreaterEqual(ra["totals"]["engaged"], rb["totals"]["engaged"])

    def test_variability_ensemble_present(self):
        cfg = minimal_valid_config()
        cfg["simulation"]["seeds"] = [42, 43, 44]
        cfg["simulation"]["seed"] = 42
        output = run_simulation(cfg)
        self.assertEqual(output["simulation_status"], "completed")
        for sc in output["scenarios"]:
            self.assertIn("variability", sc)
            self.assertEqual(sc["variability"]["repetitions"], 3)
            self.assertEqual(sc["variability"]["seeds"], [42, 43, 44])
        cmp = output["comparisons"][0]
        self.assertEqual(cmp["repetitions"], 3)
        self.assertTrue(cmp["paired_seeds"])

    def test_missing_evidence_file_fails_cleanly(self):
        cfg = minimal_valid_config()
        cfg["evidence_file"] = "no/such/file.json"
        output = run_simulation(cfg)
        self.assertEqual(output["simulation_status"], "failed")
        self.assertEqual(output["errors"][0]["code"], "BAD_FIELD_VALUE")

    def test_run_from_file_with_relative_evidence_path(self):
        output = run_simulation_from_file(example_config_path())
        self.assertTrue(output["source_references"], "evidence file must be loaded")

    def test_runtime_is_small(self):
        t0 = time.perf_counter()
        run_simulation_from_file(example_config_path())
        elapsed = time.perf_counter() - t0
        self.assertLess(elapsed, 5.0, f"experiment took {elapsed:.2f}s; must stay fast")


if __name__ == "__main__":
    unittest.main()
