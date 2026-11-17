"""Injected clocks only: no sleeps, SDK, credentials or native engine."""
import pytest
from ide_api.agent_deadline import SharedDeadline, DeadlineStop, ClockDiscontinuity

class Clocks:
    mono = 100.
    utc = 2000.
    def advance(self, seconds):
        self.mono += seconds
        self.utc += seconds
    def deadline(self, seconds=180., expires=3000.):
        return SharedDeadline.start(seconds, expires, monotonic=lambda: self.mono, wall=lambda: self.utc)

def test_parent_child_share_one_original_window_without_reset():
    clock = Clocks(); parent = clock.deadline()
    clock.advance(40)
    child = SharedDeadline(parent.stamp, 3000., monotonic=lambda: clock.mono, wall=lambda: clock.utc)
    assert parent.check()['remaining_seconds'] == child.check()['remaining_seconds'] == 140
    clock.advance(135)
    assert child.timeout(30) == parent.timeout(30) == 5
    clock.advance(5)
    with pytest.raises(DeadlineStop): child.check()
    with pytest.raises(DeadlineStop): parent.check()

@pytest.mark.parametrize('jump', [332.788, -5.])
def test_wall_monotonic_jump_stops_instead_of_inventing_elapsed_time(jump):
    clock = Clocks(); deadline = clock.deadline(); clock.advance(30); clock.utc += jump
    with pytest.raises(ClockDiscontinuity): deadline.check()
    assert deadline.snapshot()['wall_minus_monotonic_seconds'] == pytest.approx(jump)

def test_approval_expiry_can_only_shorten_a_window():
    clock = Clocks(); deadline = clock.deadline(expires=2010.)
    assert deadline.timeout(30) == 10
    clock.advance(10)
    with pytest.raises(DeadlineStop): deadline.check()

def test_incompatible_monotonic_domain_and_invalid_stamp_reject():
    clock = Clocks(); deadline = clock.deadline(); clock.mono -= 1
    with pytest.raises(ClockDiscontinuity): deadline.check()
    for stamp in ({}, {**deadline.stamp, 'window_seconds':True}, {**deadline.stamp,'window_seconds':181}):
        with pytest.raises(ValueError): SharedDeadline(stamp, 3000.)
