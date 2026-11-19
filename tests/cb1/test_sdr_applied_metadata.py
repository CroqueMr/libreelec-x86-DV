"""Compare applied DV metadata with the real libplacebo import and accepted geometry."""
from pathlib import Path
import os,shlex,subprocess,tempfile,unittest
from test_native_video_source import TREE,body
ROOT=Path(__file__).resolve().parents[2]

class SDRAppliedMetadataTests(unittest.TestCase):
    def test_applied_components_match_imported_statistics_static_target_and_accepted_geometry(self):
        env=dict(os.environ);prefix=env['FFMPEG_TEST_PREFIX']
        env['PKG_CONFIG_PATH']=prefix+'/lib/pkgconfig:'+env.get('PKG_CONFIG_PATH','')
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','libavutil','libplacebo'],env=env,text=True))
        libdir=subprocess.check_output(['pkg-config','--variable=libdir','libplacebo'],env=env,text=True).strip()
        env['LD_LIBRARY_PATH']=libdir+':'+prefix+'/lib:'+env.get('LD_LIBRARY_PATH','')
        snapshot=body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h').read_text(encoding='utf-8'),'struct StreamSnapshot')
        renderer=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text(encoding='utf-8')
        fact=next(line for line in renderer.splitlines() if 'output.ignoreL5 =' in line)
        dialog=(TREE/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp').read_text(encoding='utf-8')
        start=dialog.index('    SetProperty("DV.UsedL6Max",')
        display=dialog[start:dialog.index(';',start)+1]
        program=r"""
#include "cores/VideoProcessingInfo.h"
#include <cassert>
#include <cmath>
#include <format>
#include <string>
#include <bitset>
#include <array>
#include <map>
extern "C" {
#include "dvbridge_placebo.h"
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
}
struct SourceBinding{uint64_t stream{},picture{},revision{};bool Valid()const{return stream&&picture&&revision;}};
struct OutputCapabilities{bool isHDR10{},isDV{},isHLG{};};using OutputReason=VideoProcessingReason;
struct CDVPlaybackInfo{enum{HDMI=1,FEL=2,CM4=4,HDR10=8,HDR10PLUS=16,SDR=32};};
namespace DVBRIDGE{using ::SourceBinding;using ::OutputCapabilities;using ::OutputReason;struct StreamSnapshot SNAPSHOT;}
#include "DVProcessingInfo.h"
struct StringUtils {template<class...T>static std::string Format(std::format_string<T...> f,T&&...v){return std::format(f,std::forward<T>(v)...);}};
int main(int argc,char**argv){assert(argc==2);std::string test=argv[1];size_t bytes=0;auto*m=av_dovi_metadata_alloc(&bytes);assert(m);
 auto*h=av_dovi_get_header(m);h->disable_residual_flag=1;h->bl_bit_depth=h->el_bit_depth=10;h->coef_log2_denom=12;
 auto*c=av_dovi_get_color(m);c->signal_eotf=65535;c->source_max_pq=4095;
 for(unsigned row=0;row<3;++row){c->ycc_to_rgb_offset[row]={0,1};for(unsigned col=0;col<3;++col)c->ycc_to_rgb_matrix[3*row+col]=c->rgb_to_lms_matrix[3*row+col]={int(row==col),1};auto&curve=av_dovi_get_mapping(m)->curves[row];curve.num_pivots=2;curve.pivots[1]=1023;curve.poly_order[0]=1;curve.mapping_idc[0]=AV_DOVI_MAPPING_POLYNOMIAL;curve.poly_coef[0][1]=4096;}
 m->num_ext_blocks=2;auto*l1=av_dovi_get_ext(m,0);l1->level=1;l1->l1.min_pq=0;l1->l1.max_pq=3079;l1->l1.avg_pq=0;
 auto*l6=av_dovi_get_ext(m,1);l6->level=6;l6->l6.max_luminance=4000;l6->l6.min_luminance=50;l6->l6.max_cll=2000;l6->l6.max_fall=500;
 dvbridge_color mapped{};assert(dvbridge_map_color(&mapped,m,bytes,true));
 DVBRIDGE::StreamSnapshot s;s.metadata=true;s.profile=7;s.blocks[1]=s.blocks[5]=s.blocks[6]=true;s.l1=s.l5=s.l6=true;s.pq={0,3079,0};s.output.flags=CDVPlaybackInfo::SDR;s.output.effective=8;
 if(test=="sdr-zero-average"){
  assert(mapped.color.hdr.max_pq_y>0&&mapped.color.hdr.avg_pq_y==0);
  assert(!pl_hdr_metadata_contains(&mapped.color.hdr,PL_HDR_METADATA_CIE_Y));
  auto info=DVBRIDGE::NativeProcessingInfo(s);assert(!info.appliedBlocks[1]&&info.blocks[1]);
  s.output.flags=CDVPlaybackInfo::HDR10;s.output.effective=2;assert(!DVBRIDGE::NativeProcessingInfo(s).appliedBlocks[1]);
  s.output.effective=3;assert(DVBRIDGE::NativeProcessingInfo(s).appliedBlocks[1]);
  s.output.flags=CDVPlaybackInfo::SDR;s.output.effective=8;s.pq[2]=1;l1->l1.avg_pq=1;assert(dvbridge_map_color(&mapped,m,bytes,true));assert(pl_hdr_metadata_contains(&mapped.color.hdr,PL_HDR_METADATA_CIE_Y));assert(DVBRIDGE::NativeProcessingInfo(s).appliedBlocks[1]);
 }
 if(test=="l6-max-only"){
  l1->l1.avg_pq=1500;assert(dvbridge_map_color(&mapped,m,bytes,true));const auto originalMinimum=mapped.color.hdr.min_luma;
  l1->l1.min_pq=500;assert(dvbridge_map_color(&mapped,m,bytes,true));assert(mapped.color.hdr.min_luma==originalMinimum);
 }
 if(test=="ignored-l5"){
  struct{bool ignore_l5=true;}m_sourceGeometry;DVBRIDGE::StreamSnapshot::Output output;IGNORE_FACT s.output=output;s.output.flags=CDVPlaybackInfo::HDR10;s.output.effective=3;
  auto info=DVBRIDGE::NativeProcessingInfo(s);assert(!info.appliedBlocks[5]&&info.blocks[5]);s.output.flags=CDVPlaybackInfo::HDMI;assert(DVBRIDGE::NativeProcessingInfo(s).transmittedBlocks[5]);
 }
 if(test=="l6-max-only"){
  pl_color_space target{};dvbridge_hdr10_metadata signal{};assert(dvbridge_hdr10_target(&target,m,bytes)&&dvbridge_get_hdr10_metadata(&signal,m,bytes));assert(target.hdr.max_luma==4000&&target.hdr.min_luma==PL_COLOR_HDR_BLACK);assert(signal.level6&&signal.max_luminance==4000&&!signal.min_luminance&&!signal.max_cll&&!signal.max_fall);
  auto data=DVBRIDGE::NativeProcessingInfo(s);data.maxMaster=4000;data.minMaster=50;data.maxCLL=2000;data.maxFALL=500;data.output.effective=2;
  const bool metadata=true,hdr10=true;std::bitset<256>applied;applied[6]=true;std::map<std::string,std::string> p;auto SetProperty=[&](const char*k,const std::string&v){p[k]=v;};L6_DISPLAY
  assert(p["DV.UsedL6Max"]=="4000 nits");
 }
 av_free(m);
}
"""
        program=program.replace('SNAPSHOT',snapshot).replace('IGNORE_FACT',fact).replace('L6_DISPLAY',display)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'check.cpp').write_text(program,encoding='utf-8')
            build=subprocess.run(['cc','-std=c11','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'CB1/src'),*flags,
                '-c',str(ROOT/'CB1/src/dvbridge_placebo.c'),'-o',str(root/'placebo.o')],env=env,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            build=subprocess.run(['c++','-std=c++20','-I'+str(ROOT/'CB1/src'),'-I'+str(TREE/'xbmc'),
                '-I'+str(TREE/'xbmc/cores'),'-I'+str(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video'),
                str(root/'check.cpp'),str(root/'placebo.o'),*flags,'-Wl,--gc-sections','-o',str(root/'check')],env=env,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            for case in ('sdr-zero-average','ignored-l5','l6-max-only'):
                with self.subTest(case=case):
                    run=subprocess.run([str(root/'check'),case],env=env,capture_output=True,text=True)
                    self.assertEqual(run.returncode,0,run.stderr)
