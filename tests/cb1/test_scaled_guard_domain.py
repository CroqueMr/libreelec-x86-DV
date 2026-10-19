"""The direct recovery branch must pass the actual source encoding to the GPU."""
from pathlib import Path
import subprocess
import tempfile
import unittest

class ScaledGuardDomain(unittest.TestCase):
    def test_pq_and_linear_recovery_use_their_own_domain(self):
        root=Path(__file__).resolve().parents[2]
        code=(root/'CB1/src/dvbridge_render.c').read_text()
        start=code.index('    }else if(!intermediate && r->dv.enhanced_pixels')
        end=code.index('    }else if(composed && r->fragment_quad)',start)
        branch=code[start:end]
        program=r'''
#include <cassert>
constexpr int DVBRIDGE_ADAPTIVE_A=0,CB1_DVE_SOURCE_BOUND=5;
struct Renderer {
 struct {bool enhanced_pixels=true,ai_source=false;
   struct {struct {struct {int adaptive=1;} policy;int expansion_reason=5;} value;} output;} dv;
 bool enhanced_skip_aux=true,fragment_quad=true,enhanced_linear=false;
 int enhanced_input=0,rgb=7;
};
static bool selected_linear,called;
static bool dve_pack_overlay(Renderer*,int input,int,bool,const unsigned*,unsigned,bool linear)
{assert(input==7 || input==8);called=true;selected_linear=linear;return true;}
static void run(bool linear) {
 Renderer state;Renderer* r=&state;r->enhanced_linear=linear;r->enhanced_input=linear?8:0;
 int intermediate=0,target=1;bool flip=false,ok=false;const unsigned* packets=nullptr;unsigned count=0;
 called=false;
 if(false) {
'''+branch+r'''
 }
 assert(ok && called && selected_linear==linear);
}
int main(){run(false);run(true);}
'''
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);(path/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(path/'test.cpp'),'-o',str(path/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(path/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
