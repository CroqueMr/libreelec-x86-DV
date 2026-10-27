"""Execute the real Kodi import prefixes for all DV conversion policies."""
import unittest
import test_native_spatial_contract as spatial
from test_native_video_source import TREE, body


class SourceChromaTests(unittest.TestCase):
    def test_all_conversion_imports_preserve_declared_chroma_phase(self):
        text = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare = body(text, 'bool CDVBridgeGLES::Prepare(')
        prepare = prepare[prepare.index('  dvbridge_gl_frame bl{}, el{};'):prepare.index('  // Subtitle-only')]
        policy = body(text, 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        start = policy.index('  dvbridge_gl_frame bl{}, el{};')
        policy = policy[start:policy.index('  const double elPts', start)]
        helper = ''
        if 'bool ImportLayer(' in text:
            helper = 'bool ImportLayer(dvbridge_gl_frame* frame, int gpu, const Layer& layer) ' + body(text, 'bool ImportLayer(')
        program = r'''
#include <cassert>
#include <limits>
constexpr int AVCHROMA_LOC_UNSPECIFIED=0,AVCHROMA_LOC_LEFT=1,AVCHROMA_LOC_CENTER=2,AVCHROMA_LOC_TOPLEFT=3,
       PL_CHROMA_UNKNOWN=10,PL_CHROMA_LEFT=11,PL_CHROMA_CENTER=12,PL_CHROMA_TOP_LEFT=13;
struct Layer {int layout=0,width=8,height=8,planes[3]{};double pts=0;
 int chromaLocation=AVCHROMA_LOC_LEFT;struct{int profile=8;}sourceInfo;};
struct Frame {Frame* enhancement_layer=nullptr;float x=0,y=0;};
struct dvbridge_gl_frame {Frame frame;};
int dvbridge_map_chroma(int c){return c==AVCHROMA_LOC_LEFT?PL_CHROMA_LEFT:
 c==AVCHROMA_LOC_TOPLEFT?PL_CHROMA_TOP_LEFT:c==AVCHROMA_LOC_CENTER?PL_CHROMA_CENTER:PL_CHROMA_UNKNOWN;}
bool dvbridge_gl_frame_import(dvbridge_gl_frame* f,int,int layout,int,int,const int*){
 f->frame.x=layout?-.5f:0;return true;}
void dvbridge_gl_frame_release(dvbridge_gl_frame*){}
void dvbridge_gl_frame_set_chroma(dvbridge_gl_frame* f,int p){
 if(f->frame.x==-.5f && f->frame.y==17)return;
 f->frame.x=p==PL_CHROMA_CENTER?0:-.5f;
 f->frame.y=p==PL_CHROMA_TOP_LEFT?-.5f:0;
}
HELPER
enum FrameStatus{Failed};
struct Test {bool m_hdr10=false;struct{int gpu=0;}gl,*m_gl=&gl;
 bool Failure(const char*){return false;}
 bool run(const Layer& base,const Layer* enhancement,bool advanced){
 if(advanced){ POLICY CHECK }
 else { PREPARE CHECK }
 return true;
 }
};
int main(){Test t;Layer b,e;e.chromaLocation=AVCHROMA_LOC_TOPLEFT;
 for(bool advanced:{false,true})for(bool hdr:{false,true})for(int p:{AVCHROMA_LOC_LEFT,AVCHROMA_LOC_CENTER,AVCHROMA_LOC_TOPLEFT,AVCHROMA_LOC_UNSPECIFIED}){
 t.m_hdr10=hdr;b.chromaLocation=p;b.sourceInfo.profile=8;assert(t.run(b,&e,advanced));
 b.sourceInfo.profile=7;assert(t.run(b,&e,advanced));
 assert(t.run(b,nullptr,advanced));
 }
}
'''
        checks = r'''
 float x=base.chromaLocation==AVCHROMA_LOC_CENTER?0:-.5f;
 float y=base.chromaLocation==AVCHROMA_LOC_TOPLEFT ||
   (base.chromaLocation==AVCHROMA_LOC_UNSPECIFIED && base.sourceInfo.profile==7)?-.5f:0;
 assert(bl.frame.x==x && bl.frame.y==y);
 if(enhancement)assert(el.frame.x==-.5f && el.frame.y==-.5f);
'''
        spatial.NativeSpatialContractTests.run_program(self, program.replace('HELPER', helper).replace('PREPARE', prepare)
                         .replace('POLICY', policy).replace('CHECK', checks)
                         .replace('#include <limits>', '#include <limits>\n#include <initializer_list>'))
