"""Input-contract validation tests (Part 13: invalid configurations)."""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import unittest

from helpers import minimal_valid_config, mutated_config

from sakurascore_sim import ConfigError, validate_input
from sakurascore_sim.models import ErrorCodes


class TestSchemaValidation(unittest.TestCase):

    def test_minimal_valid_config_passes(self):
        parsed = validate_input(minimal_valid_config())
        self.assertEqual(parsed.ip_id, "test-ip")
        self.assertEqual(len(parsed.audience_segments), 2)
        self.assertEqual(len(parsed.scenarios), 2)
        self.assertEqual(parsed.simulation.agent_count, 12)

    def test_wrong_schema_version_rejected(self):
        with self.assertRaises(ConfigError) as cm:
            validate_input(mutated_config(schema_version="2.0"))
        self.assertEqual(cm.exception.code, ErrorCodes.SCHEMA_VERSION)

    def test_missing_ip_id(self):
        cfg = minimal_valid_config()
        del cfg["ip_id"]
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.BAD_ID)

    def test_bad_ip_id_format(self):
        with self.assertRaises(ConfigError) as cm:
            validate_input(mutated_config(ip_id="Not Kebab!"))
        self.assertEqual(cm.exception.code, ErrorCodes.BAD_ID)

    def test_empty_audience_segments_rejected(self):
        with self.assertRaises(ConfigError) as cm:
            validate_input(mutated_config(audience_segments=[]))
        self.assertEqual(cm.exception.code, ErrorCodes.EMPTY_SEGMENTS)

    def test_segment_shares_must_sum_to_one(self):
        cfg = minimal_valid_config()
        cfg["audience_segments"][0]["size_share"] = 0.9  # 0.9 + 0.4 = 1.3
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.SEGMENT_SHARES)

    def test_unknown_language_in_segment(self):
        cfg = minimal_valid_config()
        cfg["audience_segments"][0]["language_affinity"]["xx"] = 0.5
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.BAD_LANGUAGE)

    def test_unknown_evidence_reference(self):
        cfg = minimal_valid_config()
        cfg["audience_segments"][0]["evidence_ids"] = ["no-such-source"]
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.EVIDENCE_REF)

    def test_duplicate_segment_ids(self):
        cfg = minimal_valid_config()
        cfg["audience_segments"][1]["id"] = "seg-a"
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.DUPLICATE)

    def test_duplicate_evidence_ids(self):
        cfg = minimal_valid_config()
        cfg["evidence"].append(dict(cfg["evidence"][0]))
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.DUPLICATE)

    def test_evidence_url_must_be_http(self):
        cfg = minimal_valid_config()
        cfg["evidence"][0]["url"] = "ftp://not-allowed"
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.BAD_VALUE)

    def test_evidence_label_vocabulary(self):
        cfg = minimal_valid_config()
        cfg["evidence"][0]["label"] = "simulated"  # evidence can never be 'simulated'
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.BAD_VALUE)

    def test_evidence_date_formats(self):
        for good in ("2025", "2025-06", "2025-06-01"):
            cfg = minimal_valid_config()
            cfg["evidence"][0]["date"] = good
            validate_input(cfg)  # must not raise
        for bad in ("June 2025", "2025/06", "yesterday"):
            cfg = minimal_valid_config()
            cfg["evidence"][0]["date"] = bad
            with self.assertRaises(ConfigError):
                validate_input(cfg)

    def test_agent_count_bounds(self):
        for bad in (0, 1, 5001, -5):
            with self.assertRaises(ConfigError) as cm:
                validate_input(mutated_config(simulation={"agent_count": bad, "rounds": 3, "seed": 1}))
            self.assertEqual(cm.exception.code, ErrorCodes.SIM_PARAMS)

    def test_rounds_bounds(self):
        for bad in (0, 101):
            with self.assertRaises(ConfigError) as cm:
                validate_input(mutated_config(simulation={"agent_count": 10, "rounds": bad, "seed": 1}))
            self.assertEqual(cm.exception.code, ErrorCodes.SIM_PARAMS)

    def test_seed_bounds_and_type(self):
        with self.assertRaises(ConfigError) as cm:
            validate_input(mutated_config(simulation={"agent_count": 10, "rounds": 3, "seed": -1}))
        self.assertEqual(cm.exception.code, ErrorCodes.SIM_PARAMS)
        with self.assertRaises(ConfigError) as cm:
            validate_input(mutated_config(simulation={"agent_count": 10, "rounds": 3, "seed": "42"}))
        self.assertEqual(cm.exception.code, ErrorCodes.SIM_PARAMS)

    def test_dub_lift_can_never_be_a_penalty(self):
        with self.assertRaises(ConfigError) as cm:
            validate_input(mutated_config(
                simulation={"agent_count": 10, "rounds": 3, "seed": 1, "dub_lift": 0.5}))
        self.assertEqual(cm.exception.code, ErrorCodes.SIM_PARAMS)

    def test_unknown_engine_rejected_with_pointer(self):
        with self.assertRaises(ConfigError) as cm:
            validate_input(mutated_config(engine="oasis"))
        self.assertEqual(cm.exception.code, ErrorCodes.ENGINE_UNAVAILABLE)
        self.assertIn("REPOSITORY_EVALUATION", cm.exception.message)

    def test_scenario_must_offer_a_language(self):
        cfg = minimal_valid_config()
        cfg["scenarios"][1]["languages_available"] = []
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.BAD_SCENARIO)

    def test_scenario_unknown_language(self):
        cfg = minimal_valid_config()
        cfg["scenarios"][1]["languages_available"] = ["ja", "xx"]
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.BAD_LANGUAGE)

    def test_empty_evidence_is_warning_not_error(self):
        parsed = validate_input(mutated_config(evidence=[], evidence_file=None,
                                               audience_segments=[
                                                   {**minimal_valid_config()["audience_segments"][0],
                                                    "evidence_ids": []},
                                                   {**minimal_valid_config()["audience_segments"][1],
                                                    "evidence_ids": []},
                                               ]))
        self.assertTrue(any(w["code"] == "EVIDENCE_EMPTY" for w in parsed.warnings))

    def test_missing_audience_assumptions_is_error(self):
        cfg = minimal_valid_config()
        del cfg["audience_segments"]
        with self.assertRaises(ConfigError) as cm:
            validate_input(cfg)
        self.assertEqual(cm.exception.code, ErrorCodes.EMPTY_SEGMENTS)


if __name__ == "__main__":
    unittest.main()
