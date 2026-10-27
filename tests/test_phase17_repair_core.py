import unittest
from engineering.phase17_repair import (
    PHASE17_REPORTED_DESIGN, ContactWitness, NativeOutcome, candidate_designs,
    find_verified_repair, preflight, static_gravity_torque,
)

REQUIREMENTS = ('opens_before_deadline', 'no_fault', 'no_forbidden_contacts',
                'bounded_angle', 'bounded_speed', 'sensor_event',
                'controller_response', 'joint_limits', 'electrical_interface')


class RepairTests(unittest.TestCase):
    def test_reported_torque_shortfall(self):
        p = PHASE17_REPORTED_DESIGN
        self.assertAlmostEqual(static_gravity_torque(p), .247212, places=6)
        r = preflight(p)
        self.assertTrue(r.has_error)
        self.assertIn('INSUFFICIENT_STATIC_TORQUE', [x.code for x in r.findings])
        self.assertIn('SUPPORT_ENVELOPE_PROXIMITY', [x.code for x in r.findings])
        self.assertTrue(r.has_unknown)

    def test_candidate_is_not_claimed_verified(self):
        c = candidate_designs(PHASE17_REPORTED_DESIGN)[0]
        self.assertEqual((c.mass_kg, c.torque_nm, c.pivot_height_m), (.035, .12, .18))
        p = preflight(c)
        self.assertFalse(p.has_error)
        self.assertTrue(p.has_unknown)  # native collision check not yet run

    def test_contact_witness_rejects_candidate(self):
        def collides(_):
            return [ContactWitness('support', 'beam', .008)]
        p = preflight(candidate_designs(PHASE17_REPORTED_DESIGN)[0], contact_probe=collides)
        self.assertTrue(p.has_error)
        self.assertIn('FORBIDDEN_CONTACT', [f.code for f in p.findings])

    def test_bounded_search_requires_real_verification_contract(self):
        # A mocked runner tests ONLY the search protocol. Not a physics proof.
        calls = []
        def mock_native(c):
            calls.append(c)
            return NativeOutcome(dict.fromkeys(REQUIREMENTS, True), True,
                                 evidence_path='TEST_FIXTURE_ONLY')
        def mock_probe(_):
            return []
        result = find_verified_repair(
            PHASE17_REPORTED_DESIGN,
            trusted_native_preview=mock_native,
            frozen_check_names=REQUIREMENTS,
            contact_probe=mock_probe,
            max_native_previews=2,
        )
        self.assertEqual(result.state, 'VERIFIED_PROPOSAL_NOT_APPLIED')
        self.assertEqual(len(calls), 1)
        self.assertEqual(result.accepted_candidate.mass_kg, .035)

    def test_no_missing_checks_accepted(self):
        def incomplete(c):
            return NativeOutcome({'no_forbidden_contacts': True}, True,
                                 evidence_path='TEST_FIXTURE_ONLY')
        result = find_verified_repair(
            PHASE17_REPORTED_DESIGN, trusted_native_preview=incomplete,
            frozen_check_names=REQUIREMENTS, max_native_previews=1,
        )
        self.assertIsNone(result.accepted_candidate)
        self.assertEqual(result.state, 'NO_VERIFIED_FIX_WITHIN_BUDGET')

    def test_approval_budget_0_runs_zero_simulations(self):
        def should_not_run(_):
            raise AssertionError('must not run')
        result = find_verified_repair(
            PHASE17_REPORTED_DESIGN, trusted_native_preview=should_not_run,
            frozen_check_names=REQUIREMENTS, max_native_previews=0,
        )
        self.assertEqual(result.native_previews, 0)
        self.assertEqual(result.state, 'NOT_RUN')

    def test_false_independent_flag_blocks_success(self):
        def fake_runner(_):
            return NativeOutcome(dict.fromkeys(REQUIREMENTS, True), False,
                                 evidence_path='TEST_FIXTURE_ONLY')
        result = find_verified_repair(
            PHASE17_REPORTED_DESIGN, trusted_native_preview=fake_runner,
            frozen_check_names=REQUIREMENTS, max_native_previews=1,
        )
        self.assertIsNone(result.accepted_candidate)

if __name__ == '__main__':
    unittest.main()
