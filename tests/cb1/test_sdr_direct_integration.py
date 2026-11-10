"""Execute the shipped SDR preparation branch, never a copy of its selector."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import os
import shlex
from test_native_video_source import TREE, body

ROOT = Path(__file__).resolve().parents[2]


class SDRDirectIntegration(unittest.TestCase):
    def test_complete_prepare_resolve_and_strict_presented_owners(self):
        renderer = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        header = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h').read_text()
        settings = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        settings = settings[:settings.index('inline std::mutex& OutputSettingsMutex()')]
        settings = '\n'.join(line for line in settings.splitlines() if not line.startswith(('#include','#pragma')))+'\n}\n'
        snapshot = body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h').read_text(),'struct StreamSnapshot')
        # The real shipping build enables AI; retain its plain telemetry fields
        # while this deterministic external-boundary fixture disables model code.
        snapshot = snapshot.replace('#ifdef CB1_HAS_HDR10_AI', '#if 1')
        cls = 'class CDVBridgeGLES\n'+body(header,'class CDVBridgeGLES\n').replace('private:', 'public:')+';'
        signatures = (
            'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(const Layer& base, const Layer* enhancement,\n    const CDVMetadataBuffer& metadata, dvbridge_geometry geometry,\n    const DVBRIDGE::OutputPreferences& preferences, bool allowPacked, const dvbridge_policy* selected,\n    bool allowAsync)',
            'bool CDVBridgeGLES::ResolveHDR10(bool limited)',
            'bool CDVBridgeGLES::Presented(bool success, const Submission& submission)',
            'void CDVBridgeGLES::PreparedAudit(std::string_view sdr)')
        methods = '\n'.join(sig+body(renderer,sig) for sig in signatures)
        demux = (TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        decoder = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        producer = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp').read_text()
        start = demux.index('    AVDOVIDecoderConfigurationRecord sourceConfig{};')
        admission = demux[start:demux.index('    if (el->codecpar->extradata',start)]
        start = demux.index('          sideData =\n',demux.index('// https://github.com/FFmpeg/FFmpeg/blob/release/7.0/doc/APIchanges'))
        demux_copy = demux[start:demux.index('#ifdef HAVE_DVBRIDGE',start)]
        start = decoder.index('  pVideoPicture->doviMetadata.Reset();')
        decoded = decoder[start:decoder.index('  if (pVideoPicture->hdrType == StreamHdrType::HDR_TYPE_HDR10 ||',start)]
        start = producer.index('  layer.lease=buffer.doviSourcePicture;')
        layer_copy = producer[start:producer.index('  layer.sourceSerial=',start)]
        hints = (TREE/'xbmc/cores/VideoPlayer/DVDStreamInfo.cpp').read_text()
        provenance = Path(__file__).with_name('sdr_direct_provenance.cpp').read_text()
        for token,code in {'@ADMISSION@':admission,'@DEMUX_COPY@':demux_copy,
            '@HINTS_COPY@':next(line for line in hints.splitlines() if 'dovi = stream->dovi;' in line),
            '@DECODED@':decoded,'@LAYER_COPY@':layer_copy,
            '@LAYER_BINDING@':next(line for line in producer.splitlines() if 'layer.binding=hdr10 ?' in line)}.items():
            provenance = provenance.replace(token,code)
        program = (Path(__file__).with_name('sdr_direct_owners.cpp')).read_text()
        program = program.replace('@SETTINGS@',settings).replace('@CLASS@',cls).replace('@SNAPSHOT@',snapshot).replace('@METHODS@',methods).replace('@PROVENANCE@',provenance)
        program = program.replace('@CHROMA@',body(renderer,'pl_chroma_location SourceChroma(')).replace('@IMPORT@',body(renderer,'bool ImportDVLayer('))
        context_signatures = (
            'dvbridge_dv_policy_status CDVBridgeGLES::Context::Poll(bool allowAhead)',
            'void CDVBridgeGLES::Context::Retain(std::shared_ptr<void> base, std::shared_ptr<void> enhancement)',
            'void CDVBridgeGLES::Context::SourceReadComplete()',
            'bool CDVBridgeGLES::Context::FenceLastUse()')
        program = program.replace('@CONTEXT@','\n'.join(sig+body(renderer,sig) for sig in context_signatures))
        start=renderer.index('// Copy the live query context')
        program=program.replace('@SDR_AUDIT@',renderer[start:renderer.index('/* Native spatial interpolation',start)])
        env = dict(os.environ)
        prefix = env['FFMPEG_TEST_PREFIX']
        env['PKG_CONFIG_PATH'] = prefix+'/lib/pkgconfig:'+env.get('PKG_CONFIG_PATH','')
        flags = shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','libplacebo','libavutil','libavcodec'],env=env,text=True))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'check.cpp').write_text(program)
            state=(TREE/'xbmc/utils/DVBridgeDiagnosticState.h').read_text()
            state=state.replace(body(state,'inline bool DiagnosticsEnabled()'),'{ return testEnabled; }')
            state=state.replace(body(state,'inline uint64_t DiagnosticNowMs()'),'{ return testNow; }')
            state=state.replace('namespace DVBRIDGE\n{','namespace DVBRIDGE\n{\ninline bool testEnabled=false; inline uint64_t testNow=1000;',1)
            (root/'utils').mkdir();(root/'utils/DVBridgeDiagnosticState.h').write_text(state)
            built = subprocess.run(['cc','-std=gnu11','-ffunction-sections','-fdata-sections','-I'+str(ROOT/'CB1/src'),
                *flags,'-c',str(ROOT/'CB1/src/cb1_hdr10plus_dovi.c'),'-o',str(root/'describe.o')],env=env,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            build = subprocess.run(['c++','-std=c++20','-DFMT_HEADER_ONLY','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-I'+str(root),'-I'+str(ROOT/'CB1/src'),'-I'+str(ROOT/'CB1/tests'),'-I'+str(TREE/'xbmc'),
                str(root/'check.cpp'),str(TREE/'xbmc/utils/Crc32.cpp'),str(TREE/'xbmc/cores/VideoSourceSideData.cpp'),
                str(TREE/'xbmc/utils/Base64.cpp'),str(TREE/'xbmc/utils/Variant.cpp'),str(TREE/'xbmc/utils/JSONVariantWriter.cpp'),
                str(root/'describe.o'),str(ROOT/'CB1/src/dvbridge_policy.c'),*flags,'-o',str(root/'check')],env=env,capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run = subprocess.run([str(root/'check')],env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            self.assertIn('COMPLETE actual PrepareFrame/ResolveHDR10/Presented owners',run.stdout)
            self.assertIn('COMPLETE provenance 2 positive 16 negative controls',run.stdout)
            self.assertIn('COMPLETE actual Capture/Import/Presented 11 raw metadata controls',run.stdout)
            self.assertIn('COMPLETE actual SDR audit decisions and query counts',run.stdout)

    def test_selection_and_failure_keep_common_fence_and_release(self):
        source = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        prepare = body(source, 'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareFrame(')
        start = prepare.index('    // Reserve the film')
        branch = prepare[start:prepare.index('  if (m_pending)', start)]
        program = r'''
#include <cassert>
#include <cstddef>
#include <initializer_list>
#include <array>
#include <string>
#include "dvbridge_policy.h"
struct Identity {unsigned stream=1,picture=1,revision=1;};
struct Info {unsigned profile=7;bool rpu=true,el=false;};
struct Layer {Info sourceInfo;bool hlg=false;Identity binding;double pts=1;};
struct Metadata {bool present=true;const void*Data()const{return present?this:nullptr;}size_t Size()const{return present;} };
struct Frame {struct{struct{float scene_max[3]{},scene_avg=0;}hdr;}color;};
struct dvbridge_gl_frame {Frame frame;};
struct Geometry {int x=0,y=0,width=8,height=8,target_width=8,target_height=8;};
int directCalls=0,stagedCalls=0,resolveCalls=0,releases=0;
bool query=true,drawOK=true,resolveOK=true;
namespace DVBRIDGE {bool DiagnosticsEnabled(){return false;}}
std::string SDRPreparationAudit(const Frame&,const Frame*,const Metadata&,Geometry,int,unsigned,bool,double,double,const std::array<int,7>&){return {};}
template<class...T>bool dvbridge_render_sdr_policy_direct_eligible(T...){return query;}
template<class...T>bool dvbridge_render_hdr10_policy_direct(T...){++directCalls;return drawOK;}
bool dvbridge_render_sdr_policy_rgb(int*,const dvbridge_policy*,Identity*,Frame*,const void*,size_t,double,double,Geometry){++stagedCalls;return true;}
bool dvbridge_render_hdr10_policy_rgb(int*,const dvbridge_policy*,Identity*,Frame*,const void*,size_t,double,double,Geometry){++stagedCalls;return true;}
template<class...T>bool dvbridge_render_sdr_policy_resolve(T...){++resolveCalls;return resolveOK;}
void dvbridge_render_policy_cancel(int*){}
void dvbridge_gl_frame_release(dvbridge_gl_frame*){++releases;}
struct Renderer {
 enum class FrameStatus {Ready,Failed};
 struct Context {bool fenceOK=true;unsigned fences=0;bool FenceLastUse(){++fences;return fenceOK;}}context,*m_context=&context;
 int token=1,*m_renderer=&token,m_scanout=1;unsigned m_outputBits=8;
 bool m_hdr10Limited=false,m_directUsable=true,m_asyncEligible=true,m_direct=false,m_prepared=false,m_pending=false;
 Identity m_pendingIdentity;
 int m_auditPreparedSerial=0,m_auditSerial=0;
 void Failure(const char*){}
 FrameStatus prepare(Layer base,Metadata metadata,bool allowPacked=true){
  const Layer*enhancement=nullptr;Geometry geometry;dvbridge_policy policy{};policy.mode=DVBRIDGE_MODE_SDR;
  dvbridge_gl_frame bl{},el{};double elPts=base.pts;FrameStatus result=FrameStatus::Failed;
  std::string sdrAudit;
  { BRANCH
  return result;
 }
};
int main(){
 for(int origin=0;origin<7;origin++)for(bool eligible:{false,true}){
  Renderer r;Layer base;Metadata metadata;
  if(origin>=1){base.sourceInfo={0,false,false};metadata.present=false;}
  if(origin==2)base.hlg=true;
  if(origin==3)metadata.present=true; // Generated profile0 RPU cannot be original DV/raw HDR.
  if(origin==4)base.sourceInfo.rpu=true;
  if(origin==5)base.sourceInfo.el=true;
  if(origin==6){base.sourceInfo={8,false,false};metadata.present=true;}
  query=eligible;directCalls=stagedCalls=resolveCalls=releases=0;
  assert(r.prepare(base,metadata)==Renderer::FrameStatus::Ready);
  const bool direct=eligible&&(origin==0||origin==1);
  assert(directCalls==direct&&stagedCalls==!direct&&resolveCalls==!direct);
  assert(releases==2&&r.context.fences==1&&r.m_direct&&r.m_pending);
 }
 for(bool fence:{false,true}){
  Renderer r;query=true;drawOK=false;r.context.fenceOK=fence;
  directCalls=stagedCalls=resolveCalls=releases=0;
  assert(r.prepare({},{})==Renderer::FrameStatus::Failed);
  assert(directCalls==1&&stagedCalls==0&&resolveCalls==0&&releases==2&&r.context.fences==1&&!r.m_pending);
 }
 drawOK=true;
 for(unsigned guard=0;guard<3;guard++){
  Renderer r;if(guard==0)r.m_directUsable=false;if(guard==1)r.m_scanout=0;
  directCalls=stagedCalls=resolveCalls=0;
  const auto result=r.prepare({},{},guard!=2);
  assert(directCalls==0&&stagedCalls==1);
  assert(result==(guard==1?Renderer::FrameStatus::Failed:Renderer::FrameStatus::Ready));
 }
}
'''.replace('BRANCH', branch)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'check.cpp').write_text(program)
            build = subprocess.run(['c++','-std=c++20','-I'+str(ROOT/'CB1/src'),str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run = subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__ == '__main__':
    unittest.main()
