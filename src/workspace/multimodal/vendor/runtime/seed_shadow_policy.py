"""SEED shadow candidate: absolute rejection, soft-warning mean updates, bounded retention."""
from seed_gate_policy import GatePolicy
from seed_quality_runtime import SeedQualityRuntime

POLICY_VERSION = 'seed-soft-update-short-gap-v1'


class ShadowPolicy(GatePolicy):
    def __init__(self, weights):
        super().__init__(weights, soft_warning=True, retain_short_gap=True)

    def _accept_feature(self, feature):
        if self.window_warning:
            self.window_warning = False
            event = SeedQualityRuntime._accept_feature(self, feature)
            event['warning'] = True
            event['baseline_updated'] = event['state'] in ('prediction', 'calibrating')
            return event
        return super()._accept_feature(feature)
