"""One shared monotonic execution deadline; wall UTC is expiry/drift evidence.

The parent and worker use the same system-wide monotonic baseline. UTC expiry
never extends. A wall/monotonic discontinuity stops further dispatch rather than
claiming an elapsed-time interpretation the recorded clocks cannot support.
"""
import math
import os
import time
from datetime import datetime, timezone


class DeadlineStop(TimeoutError):
    pass


class ClockDiscontinuity(DeadlineStop):
    pass


class SharedDeadline:
    FORMAT = 'EMBODY_SHARED_MONOTONIC_DEADLINE_V1'
    DRIFT_TOLERANCE_SECONDS = 1.0

    def __init__(self, stamp, expires_unix, *, monotonic=None, wall=None):
        self.monotonic = monotonic or time.monotonic
        self.wall = wall or time.time
        required = {'format', 'started_monotonic', 'started_unix', 'window_seconds'}
        if not isinstance(stamp, dict) or set(stamp) != required or stamp['format'] != self.FORMAT:
            raise ValueError('Exact shared deadline stamp required')
        for name in ('started_monotonic', 'started_unix', 'window_seconds'):
            if type(stamp[name]) not in (int, float) or not math.isfinite(stamp[name]):
                raise ValueError('Finite shared deadline required')
        if not 0 < stamp['window_seconds'] <= 180 or type(expires_unix) not in (int, float) or not math.isfinite(expires_unix):
            raise ValueError('Bounded execution window and absolute expiry required')
        self.stamp = dict(stamp)
        self.expires_unix = expires_unix

    @classmethod
    def start(cls, window_seconds, expires_unix, *, monotonic=None, wall=None):
        mono, utc = monotonic or time.monotonic, wall or time.time
        return cls({'format': cls.FORMAT, 'started_monotonic': mono(),
                    'started_unix': utc(), 'window_seconds': window_seconds},
                   expires_unix, monotonic=mono, wall=utc)

    def snapshot(self):
        mono, utc = self.monotonic(), self.wall()
        elapsed = mono - self.stamp['started_monotonic']
        wall_elapsed = utc - self.stamp['started_unix']
        remaining = max(0., min(self.stamp['window_seconds'] - elapsed,
                               self.expires_unix - utc))
        return {'pid': os.getpid(), 'wall_utc': datetime.fromtimestamp(utc, timezone.utc).isoformat(),
                'wall_unix': utc, 'monotonic': mono, 'elapsed_seconds': elapsed,
                'wall_elapsed_seconds': wall_elapsed, 'wall_minus_monotonic_seconds': wall_elapsed - elapsed,
                'remaining_seconds': remaining, 'clock_domain': 'system_monotonic',
                'clock_implementation': time.get_clock_info('monotonic').implementation}

    def check(self):
        value = self.snapshot()
        if value['elapsed_seconds'] < 0:
            raise ClockDiscontinuity('Monotonic baseline is incompatible; no dispatch')
        if abs(value['wall_minus_monotonic_seconds']) > self.DRIFT_TOLERANCE_SECONDS:
            raise ClockDiscontinuity('Wall/monotonic discontinuity; outcome/time may be unknown')
        if value['remaining_seconds'] <= 0:
            raise DeadlineStop('Shared execution deadline or immutable approval expiry reached')
        return value

    def timeout(self, cap):
        return min(float(cap), self.check()['remaining_seconds'])
