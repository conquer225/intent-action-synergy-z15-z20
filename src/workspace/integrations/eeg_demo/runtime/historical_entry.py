"""Use the installed player/server in an isolated, visibly marked replay session."""
import argparse
import importlib.util
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
PRODUCTION = Path('/home/xilinx/gl-hdmi-live-20261008-ea117349')


def historical_text(words):
    if words == 'GuardianLoop':
        return '历史脑电回放'
    if words.startswith('心情参考 '):
        return '历史心情 '+words[len('心情参考 '):]
    if words.startswith('疲劳 '):
        return '历史疲劳 '+words[len('疲劳 '):]
    return words


def reject_wearing_change(controller, action, value):
    raise ValueError('历史回放不能修改真实佩戴或清除脑电校准')


def main(argv=None):
    parser = argparse.ArgumentParser();parser.add_argument('mode', choices=('player','web'))
    parser.add_argument('--enable-player-control', action='store_true')
    mode, remainder = parser.parse_known_args(argv)
    sys.path[:0] = [str(ROOT), str(PRODUCTION), str(PRODUCTION/'system_runtime'),
                   '/home/xilinx/jupyter_notebooks/guardianloop_pynq',
                   '/home/xilinx/brain_eye_coexist_20261005/eye/src']
    from guardianloop_system import live_inputs
    from historical_inputs import HistoricalInputs
    from replay_backend import ReplayBridge
    import ssvep_cue_runtime
    live_inputs.BrainInputs = lambda **kwargs: HistoricalInputs(ROOT, **kwargs)
    ssvep_cue_runtime.SSVEPCueBridge = ReplayBridge
    sys.argv = [str(ROOT/'historical_entry.py'), *remainder]
    if mode.mode == 'player':
        from guide_render import Renderer
        original_text = Renderer.write_text

        def marked_text(renderer, draw, x, y, words, *args, **kwargs):
            return original_text(renderer, draw, x, y, historical_text(words), *args, **kwargs)

        Renderer.write_text = marked_text
        from system_hdmi import UnifiedDisplay
        original = UnifiedDisplay.refresh_labels

        def marked_labels(display, brain, eye, video_name):
            return original(display, brain, eye, '历史脑电回放／当前眼控 | '+video_name)

        UnifiedDisplay.refresh_labels = marked_labels
        # Keep the ordinary player's rendering, dwell progress and USB ownership.
        script = 'media_player.py'
    else:
        script = 'media_server.py'
    spec = importlib.util.spec_from_file_location('existing_historical_'+mode.mode, PRODUCTION/script)
    module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.BASE = ROOT
    if mode.mode == 'web':
        module.Controller.wearing = reject_wearing_change
        if not mode.enable_player_control:
            class ReadOnlyHandler(module.MediaHandler):
                def do_POST(self):
                    if self.authorized():
                        self.reject(409, '当前只读回放；HDMI 联合会话尚未启用')

            module.MediaHandler = ReadOnlyHandler
        original_snapshot = module.Controller.snapshot

        def marked_snapshot(controller):
            result = original_snapshot(controller)
            result.update(source='historical_recorded_eeg', current_wearer=False,
                          wheelchair={'state':'unavailable','direction':'stop','physical_output_enabled':False})
            return result

        module.Controller.snapshot = marked_snapshot
    module.main()


if __name__ == '__main__':
    main()
