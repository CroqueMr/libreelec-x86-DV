"""Analytic transfer admission is bounded to measured Adaptive paths."""
from pathlib import Path
import re
import unittest
from test_ai_reentry import execute


class P5AdaptiveTransferTests(unittest.TestCase):
    def test_admission_for_unscaled_placement(self):
        source=(Path(__file__).resolve().parents[2]/'CB1/src/dvbridge_render.c').read_text()
        statement=re.search(r'bool analytic_pq=pixels[^;]*;',source).group()
        execute(r"""
#include <cassert>
struct Renderer{bool enhanced_linear,authored_analytic_pq,authored_fel_lookup;};
enum {DVBRIDGE_ADAPTIVE_B_FP16=2};
struct Policy{int adaptive;};
struct Geometry{int source_width,source_height;};
bool dvbridge_dv_profile5_transport(const bool* value){return *value;}
int main(){
  for(unsigned bits=0;bits<256;bits++){
    bool pixels=bits&1,fel=bits&2,p5=bits&4;
    Renderer state{bool(bits&8),bool(bits&16),false};auto*r=&state;
    const bool*metadata=&p5;
    Policy selected{bits&32?DVBRIDGE_ADAPTIVE_B_FP16:0};auto*policy=&selected;
    Geometry geometry{bits&64?3840:1920,bits&64?2160:1080};
    bool full_fp16=selected.adaptive==DVBRIDGE_ADAPTIVE_B_FP16 && geometry.source_width==3840;
    int placed_y=(bits&128)&&!full_fp16?80:-1;
    @ADMISSION@
    assert(analytic_pq==(pixels && state.enhanced_linear &&
        (fel || (state.authored_analytic_pq && selected.adaptive==DVBRIDGE_ADAPTIVE_B_FP16 &&
            (placed_y>=0 || (p5 && full_fp16))))));
  }
}
""".replace('@ADMISSION@',statement))

    def test_fel_lookup_is_limited_to_selected_4k_fp16_adaptive(self):
        source=(Path(__file__).resolve().parents[2]/'CB1/src/dvbridge_render.c').read_text()
        statement=re.search(r'bool analytic_pq=pixels[^;]*;',source).group()
        execute(r"""
#include <cassert>
struct Renderer{bool enhanced_linear,authored_analytic_pq,authored_fel_lookup;};
enum {DVBRIDGE_ADAPTIVE_B_FP16=2};
struct Policy{int adaptive;};struct Geometry{int source_width,source_height;};
bool dvbridge_dv_profile5_transport(const bool* value){return *value;}
int main(){for(unsigned bits=0;bits<256;bits++){
  bool pixels=bits&1,fel=bits&2,p5=bits&4;
  Renderer state{bool(bits&8),bool(bits&16),bool(bits&128)};auto*r=&state;
  Policy selected{bits&32?DVBRIDGE_ADAPTIVE_B_FP16:0};auto*policy=&selected;
  Geometry geometry{bits&64?3840:1920,bits&64?2160:1080};const bool*metadata=&p5;
  bool full_fp16=selected.adaptive==DVBRIDGE_ADAPTIVE_B_FP16&&geometry.source_width==3840&&geometry.source_height==2160;
  const int placed_y=-1;
  @ADMISSION@
  bool wanted=pixels&&state.enhanced_linear&&
      ((fel&&!(state.authored_fel_lookup&&full_fp16))||(state.authored_analytic_pq&&p5&&full_fp16));
  assert(analytic_pq==wanted);
}}
""".replace('@ADMISSION@',statement))
