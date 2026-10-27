"""Developer-defined reference state machine, not ESP32 firmware or an AI proposal.

Input: delayed sampled distance in metres and actual hinge angle in radians.
Output: bounded joint position request in radians, at 50 Hz. Invalid/stale
measurements request open and enter FAULT. No source from imports is evaluated.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Reading:
    sequence: int
    sampled_s: float
    delivered_s: float
    distance_m: float | None
    geom_id: int
    reason: str


@dataclass(frozen=True)
class Command:
    state: str
    target_rad: float
    reason: str


class ReferenceLogic:
    def __init__(self,config):
        self.config=config;self.state='IDLE';self.since=0.;self.last_sequence=-1;self.near_count=0;self.clear_count=0

    def update(self,t,reading,q):
        c=self.config;reason='Hold current state'
        invalid=reading is not None and reading.distance_m is None
        stale=t>c.stale_s and (reading is None or t-reading.sampled_s>c.stale_s)
        if invalid or stale:self.state='FAULT';reason='Invalid or stale sensor: request open'
        if self.state=='FAULT':return Command('FAULT',c.open_target_rad,reason)
        if reading and reading.sequence!=self.last_sequence:
            self.last_sequence=reading.sequence
            near=reading.distance_m<c.threshold_m;clear=reading.distance_m>c.clear_threshold_m
            self.near_count=self.near_count+1 if near else 0;self.clear_count=self.clear_count+1 if clear else 0
        if self.state in ('IDLE','CLOSING') and self.near_count>=c.debounce_samples:
            self.state='OBJECT_DETECTED';self.since=t;reason='Debounced approach'
        elif self.state=='OBJECT_DETECTED':self.state='OPENING';self.since=t;reason='Open request'
        elif self.state=='OPENING':
            if q>=c.open_target_rad-.05:self.state='OPEN';self.since=t;reason='Measured opening reached'
            elif t-self.since>=c.timeout_s:self.state='FAULT';reason='Opening timeout'
        elif self.state=='OPEN':
            permitted=self.near_count>=c.debounce_samples if c.close_while_near else self.clear_count>=c.debounce_samples
            if permitted and t-self.since>=c.hold_s:self.state='CLOSING';self.since=t;reason='Defect: closes on approach' if c.close_while_near else 'Debounced clearance and hold elapsed'
        elif self.state=='CLOSING':
            if q<.04:self.state='IDLE';reason='Measured closed'
            elif t-self.since>=c.timeout_s:self.state='FAULT';reason='Closing timeout'
        target=c.open_target_rad if self.state in ('OBJECT_DETECTED','OPENING','OPEN','FAULT') else 0.
        return Command(self.state,target,reason)
