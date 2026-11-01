"""Offline-only proposed-command policy. No actuator, serial, network or board I/O."""
from dataclasses import dataclass
import math

FINGERS = ('thumb','index','middle','ring','little')


@dataclass(frozen=True)
class Evidence:
    window_start: float
    window_end: float
    probabilities: tuple
    transport_ok: bool
    quality_ok: bool
    cue_active: bool
    model_validated: bool


@dataclass(frozen=True)
class Limits:
    # Example simulation limits, not calibrated thresholds or real joint limits.
    probability: float = 0.8
    margin: float = 0.2
    max_age: float = 0.5
    confirmations: int = 2
    cooldown: float = 1.0
    max_silence: float = 2.5
    action_budget_ms: int = 250

    def __post_init__(self):
        if not 0.2 < self.probability <= 1 or not 0 < self.margin <= 1:
            raise ValueError('Invalid probability limits')
        if self.max_age <= 0 or self.confirmations < 2 or self.cooldown <= 0 or self.max_silence <= 0 or not 0 < self.action_budget_ms <= 250:
            raise ValueError('Invalid bounded dry-run limits')


class HandProposalPolicy:
    """Simulation mode must be explicit; production mode cannot arm yet."""
    def __init__(self, *, simulation=False, limits=None):
        self.simulation = simulation
        self.limits = limits or Limits()
        self.state = 'DISARMED'
        self.sequence = 0
        self.pending = None
        self.count = 0
        self.last_end = None
        self.cooldown_until = 0.0

    def stop(self, reason='operator_stop'):
        self.state = 'DISARMED'; self.pending = None; self.count = 0; self.last_end = None
        return dict(kind='STOP_PROPOSAL', reason=reason, control_enabled=False, dry_run=True)

    def arm(self):
        if not self.simulation:
            return dict(state='DISARMED', reason='offline_model_not_promoted', control_enabled=False)
        self.state = 'ARMED'; self.pending = None; self.count = 0; self.last_end = None
        return dict(state=self.state, control_enabled=False, dry_run=True)

    def tick(self, now):
        """Caller must tick independently of EEG arrival; local hardware watchdog remains mandatory."""
        if not math.isfinite(now): return self.stop('invalid_clock')
        if self.state!='DISARMED' and self.last_end is not None and now-self.last_end > self.limits.max_silence:
            return self.stop('input_silence')
        return dict(state=self.state, control_enabled=False, dry_run=True)

    def observe(self, evidence, now):
        if self.state == 'DISARMED':
            return dict(state=self.state, reason='explicit_arm_required', control_enabled=False)
        timing = (evidence.window_start, evidence.window_end, now)
        if not all(math.isfinite(v) for v in timing) or not evidence.window_start < evidence.window_end <= now:
            return self.stop('invalid_timing')
        if now-evidence.window_end > self.limits.max_age:
            return self.stop('stale_input')
        if not evidence.transport_ok or not evidence.quality_ok or not evidence.cue_active or not evidence.model_validated:
            return self.stop('transport_quality_cue_or_model_invalid')
        p = evidence.probabilities
        if len(p)!=5 or not all(math.isfinite(v) and 0<=v<=1 for v in p) or abs(sum(p)-1)>1e-6:
            return self.stop('invalid_probabilities')
        if self.last_end is not None and evidence.window_start < self.last_end:
            return dict(state=self.state, reason='overlapping_or_repeated_window', control_enabled=False)
        self.last_end = evidence.window_end
        if now < self.cooldown_until:
            return dict(state='COOLDOWN', reason='rate_limited', control_enabled=False)
        order = sorted(range(5),key=lambda i:p[i],reverse=True)
        best = order[0]
        if p[best] < self.limits.probability or p[best]-p[order[1]] < self.limits.margin:
            self.pending = None; self.count = 0
            return dict(state='ARMED', reason='uncertain', control_enabled=False)
        self.count = self.count+1 if self.pending==best else 1
        self.pending = best
        if self.count < self.limits.confirmations:
            return dict(state='PENDING', confirmations=self.count, control_enabled=False)
        self.sequence += 1; self.cooldown_until = now+self.limits.cooldown
        self.pending = None; self.count = 0
        return dict(kind='FINGER_PRESET_PROPOSAL', finger=FINGERS[best], sequence=self.sequence,
                    valid_until=now+self.limits.max_age, action_budget_ms=self.limits.action_budget_ms,
                    control_enabled=False, dry_run=True,
                    hardware_profile='UNSPECIFIED_NO_JOINT_ANGLES_OR_TRANSPORT')
