"""Execute the real Kodi import prefixes for all DV conversion policies."""
import unittest
import re
import os
import shlex
import subprocess
import tempfile
from pathlib import Path
import test_native_spatial_contract as spatial
from test_native_video_source import TREE, body


class SourceChromaTests(unittest.TestCase):
    def test_hdr10plus_import_links_without_optional_placebo_libav_adapter(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        helper=body(source,'bool ImportDVLayer(')
        program=r'''
#include <cassert>
#include <memory>
extern "C" {
#include "dvbridge_gl_frame.h"
#include "cb1_hdr10plus_dovi.h"
#define PL_LIBAV_IMPLEMENTATION 0
#include <libplacebo/utils/libav.h>
}
struct Side {
 AVDynamicHDRPlus metadata{};
 unsigned Serial()const{return 7;}unsigned Generation()const{return 9;}
 const AVDynamicHDRPlus* HDR10Plus()const{return &metadata;}
};
struct Binding{bool Valid()const{return true;}};
struct Layer {
 dvbridge_gl_layout layout=DVBRIDGE_P010;int width=16,height=16;
 dvbridge_gl_plane planes[3]{};AVChromaLocation chromaLocation=AVCHROMA_LOC_LEFT;
 struct{unsigned profile=0,informationGeneration=9;}sourceInfo;
 pl_hdr_metadata hdr{};bool hlg=false,fullRange=false;Binding binding;
 unsigned sourceSerial=7;std::shared_ptr<Side> sourceSideData=std::make_shared<Side>();
};
extern "C" bool dvbridge_gl_frame_import(dvbridge_gl_frame* out,pl_gpu,dvbridge_gl_layout,int,int,const dvbridge_gl_plane[3]){
 out->frame={};out->frame.color=pl_color_space_hdr10;return true;
}
extern "C" void dvbridge_gl_frame_set_chroma(dvbridge_gl_frame*,pl_chroma_location){}
pl_chroma_location SourceChroma(AVChromaLocation,unsigned){return PL_CHROMA_LEFT;}
bool ImportDVLayer(dvbridge_gl_frame* frame,pl_gpu gpu,const Layer& layer) HELPER
int main(){
 Layer layer;layer.hdr.max_luma=1000;
 auto& metadata=layer.sourceSideData->metadata;
 metadata.itu_t_t35_country_code=0xb5;metadata.num_windows=1;
 metadata.params[0].maxscl[0]={10000,100000};
 metadata.params[0].maxscl[1]={20000,100000};
 metadata.params[0].maxscl[2]={30000,100000};
 metadata.params[0].average_maxrgb={5000,100000};
 dvbridge_gl_frame imported{};
 assert(ImportDVLayer(&imported,nullptr,layer));
 assert(imported.frame.color.hdr.scene_max[0]==1000 && imported.frame.color.hdr.scene_max[2]==3000);
 assert(imported.frame.color.hdr.scene_avg==500 && imported.frame.color.hdr.max_luma==1000);
 layer.sourceSerial=8;assert(ImportDVLayer(&imported,nullptr,layer));
 assert(imported.frame.color.hdr.scene_max[0]==0 && imported.frame.color.hdr.scene_avg==0);
 layer.sourceSerial=7;metadata.params[0].maxscl[0].den=0;
 assert(ImportDVLayer(&imported,nullptr,layer) && imported.frame.color.hdr.scene_max[0]==0);
}
'''.replace('HELPER',helper)
        repo=Path(__file__).resolve().parents[2]
        env=dict(os.environ)
        prefix=env.get('FFMPEG_TEST_PREFIX')
        if prefix:env['PKG_CONFIG_PATH']=prefix+'/lib/pkgconfig:'+env.get('PKG_CONFIG_PATH','')
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','libavutil','libplacebo'],env=env,text=True))
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);(root/'test.cpp').write_text(program)
            build=subprocess.run(['cc','-std=c11','-I'+str(repo/'CB1/src'),*flags,
                '-c',str(repo/'CB1/src/cb1_hdr10plus_dovi.c'),'-o',str(root/'adapter.o')],env=env,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            build=subprocess.run(['c++','-std=c++20','-I'+str(repo/'CB1/src'),str(root/'test.cpp'),
                str(root/'adapter.o'),*flags,'-lm','-o',str(root/'test')],env=env,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            symbols=subprocess.check_output(['nm','-u',str(root/'test')],text=True)
            self.assertNotIn('pl_map_hdr_metadata',symbols)
            run=subprocess.run([str(root/'test')],env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_ai_ingress_keeps_unshifted_coded_planes(self):
        text = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        for signature in ('cb1_ai_status CDVBridgeGLES::Context::AnalyseHDR10AI(',
                          'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareHDR10AIFrame('):
            implementation = body(text, signature)
            start = implementation.index('  dvbridge_gl_frame imported{};')
            imported = implementation[start:implementation.index('  HDR10Color(imported.frame,base);', start)]
            program = r'''
#include <cassert>
struct Layer {int layout=0,width=8,height=8,planes[3]{};};
struct dvbridge_gl_frame {struct{float x=0,y=0;}frame;};
bool dvbridge_gl_frame_import(dvbridge_gl_frame*,int,int,int,int,const int*){return true;}
bool ImportLayer(dvbridge_gl_frame* frame,int,const Layer&){frame->frame.x=-.5f;return true;}
bool ImportDVLayer(dvbridge_gl_frame* frame,int,const Layer& layer){return ImportLayer(frame,0,layer);}
enum FrameStatus {Unsupported};constexpr int CB1_AI_INCOMPATIBLE=3;
struct AI {int RecordStatus(const char*,int){return -1;}};
AI HDR10AI(){return {};}
int run(){struct GL{int gpu=0;}gl,*m_gl=&gl;struct{GL*gl;}state{&gl},*m_state=&state;Layer base;
 PREFIX
 assert(imported.frame.x==0 && imported.frame.y==0);return 0;
}
int main(){assert(run()==0);}
'''.replace('PREFIX', imported)
            with self.subTest(entry=signature):
                spatial.NativeSpatialContractTests.run_program(self, program)

    def test_hardware_fel_and_prefetch_use_the_declared_input_siting(self):
        text = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        signature = 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareHardwareFrame('
        hardware = body(text, signature)
        key = '  const auto sourceChroma =' if '  const auto sourceChroma =' in hardware else '  const auto chroma ='
        sync = hardware[hardware.index(key):hardware.index('  if (m_hardwareBinding')]
        prefetch = re.search(r'dvbridge_fel_vpp_prefetch_chroma\(pending->vpp.get\(\),frame.get\(\),(.*?),\n', text)[1]
        helper = ''
        if 'SourceChroma(' in text:
            helper = 'int SourceChroma(int source,unsigned profile) ' + body(text, 'SourceChroma(')
        program = r'''
#include <cassert>
#include <initializer_list>
constexpr int AVCHROMA_LOC_UNSPECIFIED=0,AVCHROMA_LOC_LEFT=1,AVCHROMA_LOC_CENTER=2,AVCHROMA_LOC_TOPLEFT=3,
 PL_CHROMA_UNKNOWN=10,PL_CHROMA_LEFT=11,PL_CHROMA_CENTER=12,PL_CHROMA_TOP_LEFT=13;
int dvbridge_map_chroma(int c){return c==0?PL_CHROMA_UNKNOWN:c+10;}
HELPER
struct Frame {int chroma_location; Frame* get(){return this;}};
int sync(Frame* enhancement,bool native){SYNC return chroma;}
int prefetched(Frame* frame){return PREFETCH;}
int main(){for(int c:{0,1,2,3}){Frame f{c};int expected=c?c+10:PL_CHROMA_TOP_LEFT;
 CHECK
}}
'''.replace('HELPER', helper).replace('SYNC', sync).replace('PREFETCH', prefetch)
        for check in ('assert(sync(&f,false)==expected && sync(&f,true)==expected);',
                      'assert(prefetched(&f)==expected);'):
            with self.subTest(path=check):
                spatial.NativeSpatialContractTests.run_program(self, program.replace('CHECK', check))

    def test_all_conversion_imports_preserve_declared_chroma_phase(self):
        text = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare = body(text, 'bool CDVBridgeGLES::Prepare(')
        prepare = prepare[prepare.index('  dvbridge_gl_frame bl{}, el{};'):prepare.index('  // Subtitle-only')]
        policy = body(text, 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        start = policy.index('  dvbridge_gl_frame bl{}, el{};')
        policy = policy[start:policy.index('  const double elPts', start)]
        helper = ''
        if 'bool ImportDVLayer(' in text:
            helper = 'bool ImportDVLayer(dvbridge_gl_frame* frame, int gpu, const Layer& layer) ' + body(text, 'bool ImportDVLayer(')
        if 'SourceChroma(' in text:
            helper = 'int SourceChroma(int source,unsigned profile) ' + body(text, 'SourceChroma(') + helper
        program = r'''
#include <cassert>
#include <limits>
constexpr int AVCHROMA_LOC_UNSPECIFIED=0,AVCHROMA_LOC_LEFT=1,AVCHROMA_LOC_CENTER=2,AVCHROMA_LOC_TOPLEFT=3,
       PL_CHROMA_UNKNOWN=10,PL_CHROMA_LEFT=11,PL_CHROMA_CENTER=12,PL_CHROMA_TOP_LEFT=13;
constexpr int PL_COLOR_SYSTEM_BT_2020_NC=1,PL_COLOR_PRIM_BT_2020=2,
 PL_COLOR_TRC_HLG=3,PL_COLOR_TRC_PQ=4,PL_COLOR_LEVELS_FULL=5,PL_COLOR_LEVELS_LIMITED=6;
struct Binding{bool Valid()const{return true;}};
struct Dynamic{struct{double maxscl[3]{.1,.2,.3},average_maxrgb=.05;
 unsigned num_distribution_maxrgb_percentiles=0;
 struct{double percentile;}distribution_maxrgb[15];}params[1];};
struct Side{unsigned Serial()const{return 1;}unsigned Generation()const{return 1;}
 const Dynamic* HDR10Plus()const{static Dynamic metadata;return &metadata;}};
struct cb1_hdr10plus_dovi_result{};
constexpr int CB1_HDR10PLUS_DOVI_OK=0;
int cb1_hdr10plus_dovi_describe(cb1_hdr10plus_dovi_result*,const Dynamic*,void*){return 0;}
double av_q2d(double value){return value;}
struct HDR{double scene_max[3]{},scene_avg{};int sentinel{};
 HDR& operator=(int value){for(auto& c:scene_max)c=0;scene_avg=0;sentinel=value;return *this;}
 bool operator==(int value)const{return sentinel==value && scene_max[0]==0;}};
struct Layer {int layout=0,width=8,height=8,planes[3]{};double pts=0;
 Binding binding;Side* sourceSideData=nullptr;unsigned sourceSerial=0;
 bool hlg=false,fullRange=false;int hdr=0;
 int chromaLocation=AVCHROMA_LOC_LEFT;struct{int profile=8;unsigned informationGeneration=1;}sourceInfo;};
struct Frame {Frame* enhancement_layer=nullptr;float x=0,y=0;
 struct{int sys=0,levels=0;}repr;struct{int primaries=0,transfer=0;HDR hdr;}color;};
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
 Layer hdr;hdr.sourceInfo.profile=0;Side side;hdr.sourceSideData=&side;hdr.sourceSerial=1;
 dvbridge_gl_frame mapped;
 assert(ImportDVLayer(&mapped,0,hdr) && mapped.frame.color.hdr.scene_max[0]==1000 && mapped.frame.color.hdr.scene_max[2]==3000 && mapped.frame.color.hdr.scene_avg==500);
 hdr.sourceSerial=2;assert(ImportDVLayer(&mapped,0,hdr) && mapped.frame.color.hdr==0);
 hdr.sourceSerial=1;hdr.sourceInfo.informationGeneration=2;
 assert(ImportDVLayer(&mapped,0,hdr) && mapped.frame.color.hdr==0);
 hdr.sourceInfo.informationGeneration=1;hdr.hlg=true;
 assert(ImportDVLayer(&mapped,0,hdr) && mapped.frame.color.hdr==0);
 for(bool advanced:{false,true})for(bool hdr:{false,true})for(int p:{AVCHROMA_LOC_LEFT,AVCHROMA_LOC_CENTER,AVCHROMA_LOC_TOPLEFT,AVCHROMA_LOC_UNSPECIFIED,999}){
 t.m_hdr10=hdr;b.chromaLocation=p;b.sourceInfo.profile=8;assert(t.run(b,&e,advanced));
 b.sourceInfo.profile=7;assert(t.run(b,&e,advanced));
 b.sourceInfo.profile=0;b.hlg=true;assert(t.run(b,nullptr,advanced));
 assert(t.run(b,nullptr,advanced));
 }
}
'''
        checks = r'''
 float x=base.chromaLocation==AVCHROMA_LOC_CENTER?0:-.5f;
 float y=base.chromaLocation==AVCHROMA_LOC_TOPLEFT ||
   (base.chromaLocation==AVCHROMA_LOC_UNSPECIFIED && base.sourceInfo.profile==7)?-.5f:0;
 assert(bl.frame.x==x && bl.frame.y==y);
 if(!base.sourceInfo.profile){assert(bl.frame.color.transfer==PL_COLOR_TRC_HLG);
  assert(bl.frame.color.primaries==PL_COLOR_PRIM_BT_2020 && bl.frame.repr.sys==PL_COLOR_SYSTEM_BT_2020_NC);}
 if(enhancement)assert(el.frame.x==-.5f && el.frame.y==-.5f);
'''
        spatial.NativeSpatialContractTests.run_program(self, program.replace('HELPER', helper).replace('PREPARE', prepare)
                         .replace('POLICY', policy).replace('CHECK', checks)
                         .replace('#include <limits>', '#include <limits>\n#include <initializer_list>'))
