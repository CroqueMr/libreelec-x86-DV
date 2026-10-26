"""Analytic transfer admission is bounded to the measured Adaptive P5 path."""
from pathlib import Path
import re
import unittest
from test_ai_reentry import execute


class P5AdaptiveTransferTests(unittest.TestCase):
    def test_actual_admission_preserves_fel_and_excludes_unmeasured_paths(self):
        source=(Path(__file__).resolve().parents[2]/'CB1/src/dvbridge_render.c').read_text()
        statement=re.search(r'bool fast_(?:fel|pq)=pixels[^;]*;',source).group()
        statement=statement.replace('bool fast_fel=', 'bool fast_pq=')
        execute(r"""
#include <cassert>
struct Renderer{bool enhanced_linear,fast_chroma,authored_p5_analytic,authored_fel_lookup;};
enum {DVBRIDGE_ADAPTIVE_B_FP16=2};
struct Policy{int adaptive;};
struct Geometry{int source_width,source_height;};
bool dvbridge_dv_profile5_transport(const bool* value){return *value;}
int main(){
  for(unsigned bits=0;bits<256;bits++){
    bool pixels=bits&1,fel=bits&2,p5=bits&4;
    Renderer state{bool(bits&8),bool(bits&16),bool(bits&32),false};auto*r=&state;
    const bool*metadata=&p5;
    Policy selected{bits&64?DVBRIDGE_ADAPTIVE_B_FP16:0};auto*policy=&selected;
    Geometry geometry{bits&128?3840:1920,bits&128?2160:1080};
    @ADMISSION@
    assert(fast_pq==(pixels && state.enhanced_linear && state.fast_chroma &&
        (fel || (state.authored_p5_analytic && p5 &&
            policy->adaptive==DVBRIDGE_ADAPTIVE_B_FP16 &&
            geometry.source_width==3840 && geometry.source_height==2160))));
  }
}
""".replace('@ADMISSION@',statement))

    def test_fel_lookup_is_limited_to_selected_4k_fp16_adaptive(self):
        source=(Path(__file__).resolve().parents[2]/'CB1/src/dvbridge_render.c').read_text()
        statement=re.search(r'bool fast_(?:fel|pq)=pixels[^;]*;',source).group()
        execute(r"""
#include <cassert>
struct Renderer{bool enhanced_linear,fast_chroma,authored_p5_analytic,authored_fel_lookup;};
enum {DVBRIDGE_ADAPTIVE_B_FP16=2};
struct Policy{int adaptive;};struct Geometry{int source_width,source_height;};
bool dvbridge_dv_profile5_transport(const bool* value){return *value;}
int main(){for(unsigned bits=0;bits<512;bits++){
  bool pixels=bits&1,fel=bits&2,p5=bits&4;
  Renderer state{bool(bits&8),bool(bits&16),bool(bits&32),bool(bits&256)};auto*r=&state;
  Policy selected{bits&64?DVBRIDGE_ADAPTIVE_B_FP16:0};auto*policy=&selected;
  Geometry geometry{bits&128?3840:1920,bits&128?2160:1080};const bool*metadata=&p5;
  @ADMISSION@
  bool fp16_4k=selected.adaptive==DVBRIDGE_ADAPTIVE_B_FP16&&geometry.source_width==3840&&geometry.source_height==2160;
  bool wanted=pixels&&state.enhanced_linear&&state.fast_chroma&&
      ((fel&&!(state.authored_fel_lookup&&fp16_4k))||(state.authored_p5_analytic&&p5&&fp16_4k));
  assert(fast_pq==wanted);
}}
""".replace('@ADMISSION@',statement))
