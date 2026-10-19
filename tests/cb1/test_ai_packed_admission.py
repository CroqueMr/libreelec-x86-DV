"""Run Kodi's actual packed-output admission with literal geometry cases."""
import pathlib
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

ROOT = pathlib.Path(__file__).resolve().parents[2]

class PackedAdmission(unittest.TestCase):
    def test_unscaled_borders_use_packed_output_without_admitting_scaled_borders(self):
        added = shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        condition = re.search(r'if \(allowPacked && m_directUsable.*?\n\s*\{', added, re.S).group(0)
        program = '''#include <cassert>
enum { DVBRIDGE_MODE_STANDARD=0, DVBRIDGE_MODE_ENHANCED_DV=1 };
struct Geometry { int source_width,source_height,x,y,width,height; };
bool admits(Geometry geometry,bool allowPacked=true,bool m_directUsable=true,bool m_scanout=true,int mode=0,bool optimized=true,bool m_overlayVisible=false) {
    struct {int mode;} policy{mode};
    struct {bool optimizedDV;} preferences{optimized};
''' + condition + '''return true;} return false;}
int main(){
    assert(admits({3840,1600,0,280,3840,1600}));
    assert(admits({3840,1920,0,120,3840,1920}));
    assert(admits({1920,1080,0,0,3840,2160}));
    assert(!admits({1920,800,0,280,3840,1600}));
    assert(!admits({3840,1600,0,280,3840,1600},false));
    assert(!admits({3840,1600,0,280,3840,1600},true,false));
    assert(!admits({3840,1600,0,280,3840,1600},true,true,false));
    assert(admits({3840,1600,0,280,3840,1600},true,true,true,1));
    assert(admits({1920,800,0,280,3840,1600},true,true,true,1));
    assert(!admits({3840,1600,0,280,3840,1600},true,true,true,1,true,true));
    assert(!admits({3840,1600,0,280,3840,1600},true,true,true,2));
    assert(!admits({3840,1600,0,280,3840,1600},true,true,true,0,false));
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source = pathlib.Path(directory) / 'admission.cpp'
            binary = pathlib.Path(directory) / 'admission'
            source.write_text(program)
            subprocess.run(['c++','-std=c++20',str(source),'-o',str(binary)],check=True,capture_output=True)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
