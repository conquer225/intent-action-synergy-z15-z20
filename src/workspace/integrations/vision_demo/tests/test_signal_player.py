"""Run the generated player's status expression at the hidden-audio seam."""
import ast,unittest
from pathlib import Path
from types import SimpleNamespace
from patch_media import patch


class SignalPlayerTests(unittest.TestCase):
 def test_fatigue_status_with_disabled_music_does_not_exit_the_display(self):
  original=Path(__file__).resolve().parents[2]/'eeg_demo/runtime/media_player.py'
  source=patch(original.read_text(encoding='utf-8'))
  calls=[n for n in ast.walk(ast.parse(source)) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='status']
  call=next(n for n in calls if any(k.arg=='state' and isinstance(k.value,ast.Constant) and k.value.value=='vision' for k in n.keywords))
  expression=next(k.value for k in call.keywords if k.arg=='audio_output')
  vision=SimpleNamespace(signal_mode=True,signal=SimpleNamespace(session=None))
  self.assertFalse(eval(compile(ast.Expression(expression),'generated-player','eval'),{'vision':vision}))

