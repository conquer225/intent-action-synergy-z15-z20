import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class VideoBootTests(unittest.TestCase):
    def test_startup_stops_at_each_failed_stage_and_rejects_invalid_pool(self):
        self.run_program(r'''
        #include "video_boot.h"
        static int calls=0, failure=0;
        static int step() { return ++calls==failure?1:0; }
        static int camera(void*,unsigned,unsigned,unsigned){return step();}
        static int dma(void*,unsigned,unsigned,unsigned,unsigned,unsigned){return step();}
        static int display(void*){return step();}
        int main(){ z20_video_ops ops={camera,dma,display};
          for(failure=1;failure<=6;++failure){calls=0;
            if(z20_video_start(&ops,0,0x01000000u)==0 || calls!=failure) return 1;}
          calls=0;
          if(z20_video_start(&ops,0,0x3ff00000u)==0 || calls) return 2;
          if(z20_video_start(0,0,0x01000000u)==0 || calls) return 3;
          ops.dma=0;
          if(z20_video_start(&ops,0,0x01000000u)==0 || calls) return 4;
          return 0;
        }''')

    def test_startup_uses_half_width_writers_and_full_display_stride(self):
        source = r'''
        #include "video_boot.h"
        static int calls=0;
        static int camera(void*, unsigned id, unsigned w, unsigned h) {
          if (id!=(unsigned)calls || w!=640 || h!=720) return 99;
          ++calls; return 0;
        }
        static int dma(void*, unsigned id, unsigned address, unsigned active,
                       unsigned stride, unsigned height) {
          if (calls!=2+(int)id || address!=(id==1?0x01000780u:0x01000000u)
              || active!=(id==2?3840u:1920u) || stride!=3840 || height!=720) return 99;
          ++calls; return 0;
        }
        static int display(void*) { if(calls!=5) return 99; ++calls; return 0; }
        int main() { z20_video_ops ops={camera,dma,display};
          return z20_video_start(&ops,0,0x01000000u) || calls!=6; }
        '''
        self.run_program(source)

    def run_program(self, source):
        self.assertIsNotNone(shutil.which('g++'), 'host C++ compiler required')
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path/'test.cpp').write_text(source)
            command = ['g++', '-std=c++11', '-O2', '-static',
                       '-I'+str(ROOT/'hardware/standalone'), str(path/'test.cpp'),
                       str(ROOT/'hardware/standalone/video_boot.c'), '-o', str(path/'test.exe')]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
            self.assertEqual(subprocess.run([str(path/'test.exe')]).returncode, 0)


if __name__ == '__main__': unittest.main()
