"""Exercise native snapshot receipts and first-frame transition order without DRM hardware."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_gbm_colour_owner import method, native_owner_program


def compile_run(test, program, includes=()):
    with tempfile.TemporaryDirectory() as directory:
        binary = Path(directory) / "check"
        result = subprocess.run(["c++", "-std=c++20", *includes, "-x", "c++", "-", "-o", str(binary)],
                                input=program, capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        result = subprocess.run([str(binary)], capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class GbmColourTransition(unittest.TestCase):
    def setUp(self):
        tree = os.environ.get("KODI_NATIVE_SOURCE_TREE")
        if not tree:
            self.skipTest("requires the fully prepared native Kodi tree")
        self.root = Path(tree)

    def test_native_successor_selects_saved_color_and_range_before_first_render(self):
        controller = (self.root / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        native = (self.root / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
        program = native_owner_program(self.root).split('int main() {', 1)[0]
        for signature in ('bool ConnectorPreferencesAllowed()',
                          'std::optional<bool> TransportLimitedColor()',
                          'std::optional<uint64_t> RestoredConnectorProperty('):
            program = program.replace(signature, 'virtual ' + signature)
        program = program.replace('struct VideoPicture {', 'struct VideoPicture {int color_transfer=16;')
        program = program.replace(' bool rangeTransition=false;', r'''
 std::vector<std::map<std::string,uint64_t>> attempts;bool accept=false;
 bool HasPendingCB1Page()const{return false;}
 void AllowModeset(){}
 bool FlipPageTransactional(void*,bool){attempts.push_back(pending);Commit(accept);return accept;}
 bool rangeTransition=false;''')
        present = method(controller, 'CWinSystemGbmGLESContext::PresentFrame')
        ordinary = present.split('\n  if (m_dvOrdinaryFrame)\n', 1)[1]
        ordinary = ordinary[ordinary.index('{') + 1:ordinary.index('    if (!submitted)')]
        ordinary = ordinary.replace('return;', 'return false;') + '\nreturn submitted;'
        methods = '\n'.join(method(controller, 'CWinSystemGbmGLESContext::' + name) for name in
                            ('PrepareOrdinaryDVOutput', 'StageCB1ConnectorPreferences',
                             'ConnectorPreferencesAllowed', 'TransportLimitedColor',
                             'RestoredConnectorProperty'))
        program += r'''
#include <iostream>
struct State{
 bool captured=false;std::map<std::string,uint64_t> before;
 bool Captured()const{return captured;}
 std::optional<uint64_t> Before(const char*name)const{
  auto it=before.find(name);return it==before.end()?std::optional<uint64_t>{}:it->second;}
 bool Stage(CDRMAtomic&d,bool restore){assert(restore);
  for(const auto&[name,value]:before)if(!d.AddProperty(d.GetConnector(),name.c_str(),value))return false;
  return true;}
 enum class Backend{KERNEL,NVIDIA};Backend CapturedBackend(){return Backend::KERNEL;}
};
using CDVBridgeState=State;
struct Surface{Surface&GetDevice(){return *this;}Surface&GetSurface(){return *this;}
 void*LockTransactionalBuffer(){return this;}void CompleteTransactionalBuffer(bool){}};
struct CWinSystemGbmGLESContext:CWinSystemGbm{
 State m_cb1ConnectorState,m_dvState;
 bool m_cb1RestoringPreferences=false,m_dvOrdinaryFrame=false,m_dvStopPending=false;
 bool m_dvOutputSurface=false,m_dvEndPending=false;
 std::shared_ptr<void>m_nativeDVProperties;
 std::optional<uint64_t>m_hdrDeepColorPrevious,m_queuedHdrMetadata;
 std::optional<bool>m_cb1LimitedRange,m_cb1OrdinaryLimitedRange;
 unsigned hdrPreparations=0;bool guiLimited=false;
 std::shared_ptr<Surface>m_GBM=std::make_shared<Surface>();
 struct EGL{bool TrySwapBuffers(){return true;}}m_eglContext;
 bool HasPendingDVBridgeRestore()const{return m_cb1ConnectorState.Captured();}
 bool HasPendingDVOutputSurface()const{return true;}
 bool SetHDR(const VideoPicture*){++hdrPreparations;m_queuedHdrMetadata=99;return true;}
 void SetGuiCompositing(int){guiLimited=UseLimitedColor();}
 bool PrepareOrdinaryDVOutput(const VideoPicture*);
 bool StageCB1ConnectorPreferences(bool);
 bool ConnectorPreferencesAllowed()const override;
 std::optional<bool>TransportLimitedColor()const override;
 std::optional<uint64_t>RestoredConnectorProperty(const char*)const override;
 bool RequeueOutputProperties() @REQUEUE@
 void AnnounceCB1Mode(bool){}void CompleteCB1Mode(bool,bool){}
 bool FlipDVBridgePage(State&,bool,bool,bool,void*){assert(false);return false;}
 bool Ordinary(bool rendered){@ORDINARY@}
};
@METHODS@
int main(){unsigned failed=0;
 for(bool yuv:{true,false}){
  CWinSystemGbmGLESContext w;auto drm=std::dynamic_pointer_cast<CDRMAtomic>(w.m_DRM);
  auto&con=drm->connector;
  con.cache["color format"]=1;con.cache["Broadcast RGB"]=1;con.cache["Colorspace"]=0;
  con.cache["HDR_OUTPUT_METADATA"]=0;
  con.enums["Colorspace"]={{"Default",0},{"BT2020_RGB",1},{"BT2020_YCC",2},{"BT709_YCC",3}};
  w.m_cb1ConnectorState.captured=true;
  w.m_cb1ConnectorState.before={{"color format",yuv?3U:1U},{"Broadcast RGB",yuv?2U:1U},{"max bpc",8}};
  w.m_cb1LimitedRange=yuv;w.m_cb1OrdinaryLimitedRange=!yuv;
  assert(w.UseLimitedColor()==yuv);
  VideoPicture picture;
  assert(w.PrepareOrdinaryDVOutput(&picture));
  const bool prepared=w.m_queuedColorspace==(yuv?2:1) && w.UseLimitedColor()==!yuv && w.guiLimited==!yuv;
  std::cout<<"prepared "<<(yuv?"saved-YUV":"saved-RGB")<<" color="<<*w.m_queuedColorspace
           <<" shader_limited="<<w.UseLimitedColor()<<" gui_limited="<<w.guiLimited<<std::endl;
  failed+=!prepared;
  assert(w.PrepareOrdinaryDVOutput(&picture) && w.hdrPreparations==1);
  assert(!w.Ordinary(true));assert(!w.Ordinary(true));drm->accept=true;assert(w.Ordinary(true));
  assert(w.hdrPreparations==1 && drm->attempts.size()==3);
  for(const auto&attempt:drm->attempts){
   const bool correct=attempt.at("Colorspace")==uint64_t(yuv?2:1) &&
      attempt.at("color format")==uint64_t(yuv?3:1) &&
      attempt.at("Broadcast RGB")==uint64_t(yuv?2:1) &&
      attempt.at("HDR_OUTPUT_METADATA")==99;
   std::cout<<"commit saved_"<<(yuv?"YUV":"RGB")<<" colorspace="<<attempt.at("Colorspace")
            <<" format="<<attempt.at("color format")<<" range="<<attempt.at("Broadcast RGB")<<std::endl;
   failed+=!correct;
  }
 }
 assert(failed==0 && "Native color/range policy must be selected before first render and preserved by every attempt");
}
'''
        requeue = method(native, 'CWinSystemGbm::RequeueOutputProperties')
        program = program.replace('@METHODS@', methods).replace('@ORDINARY@', ordinary).replace(
            '@REQUEUE@', requeue[requeue.index('{'):])
        compile_run(self, program)

    def test_snapshot_accepted_rejected_restore_and_missing_properties(self):
        base = self.root / "xbmc/windowing/gbm/drm"
        source = (base / "DVBridgeState.cpp").read_text()
        header = (base / "DVBridgeState.h").read_text()
        declaration = header[header.index("class CDVBridgeState\n"):header.rindex("}")]
        names = ["Read", "CaptureColorPreferences", "Before", "Stage"]
        methods = "\n".join(method(source, "CDVBridgeState::" + name) for name in names)
        controller = (self.root / "xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp").read_text()
        controllers = "\n".join(method(controller, "CWinSystemGbmGLESContext::" + name) for name in
                                ["CaptureCB1ConnectorPreferences", "StageCB1ConnectorPreferences",
                                 "StageTransportPreferences", "TransportLimitedColor",
                                 "RestoredConnectorProperty", "CompleteCB1ConnectorRestore",
                                 "ConnectorPreferencesAllowed"])
        fixture = Path(__file__).with_name("gbm_colour_transition.cpp").read_text().replace("// NATIVE_CONTROLLER", controllers)
        compile_run(self, fixture.replace("// NATIVE_DECLARATION", declaration)
                    .replace("// NATIVE_METHODS", methods))

    def test_deferred_stop_requires_a_new_frame(self):
        source = (self.root / "xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp").read_text()
        start = source.index("  // An ordinary restoration must present")
        end = source.index("  if (m_dvEndPending", start)
        fragment = source[start:end]
        program = r'''
#include <cassert>
struct Manager {int dirties=0;void MarkDirty(){++dirties;} Manager& GetWindowManager(){return *this;}};
struct CServiceBroker {static Manager* GetGUI(){static Manager manager;return &manager;}};
struct Window {
 bool m_dvStopPending=true,m_dvOrdinaryFrame=false,stopReady=true,fenceReady=true,commitAccepted=true;
 int commits=0,renders=0;bool renderedForOrdinary=false;
 bool StopDVBridgePlayback(){if(!stopReady)return false;m_dvOrdinaryFrame=true;return true;}
 void BeginRender(){++renders;renderedForOrdinary=m_dvOrdinaryFrame;}
 void PresentFrame(){
  if(!fenceReady)return;
  FRAGMENT
  if(m_dvOrdinaryFrame){assert(renderedForOrdinary);++commits;
   if(commitAccepted){m_dvStopPending=false;m_dvOrdinaryFrame=false;}}
 }
};
int main(){
 Window w;w.BeginRender();w.PresentFrame();assert(w.commits==0 && w.m_dvOrdinaryFrame);
 assert(CServiceBroker::GetGUI()->dirties==1);
 w.BeginRender();w.fenceReady=false;w.PresentFrame();assert(w.commits==0);
 w.fenceReady=true;w.commitAccepted=false;w.PresentFrame();assert(w.commits==1 && w.m_dvOrdinaryFrame);
 w.BeginRender();w.commitAccepted=true;w.PresentFrame();assert(w.commits==2 && !w.m_dvStopPending);
 Window waiting;waiting.stopReady=false;waiting.BeginRender();waiting.PresentFrame();assert(waiting.commits==0);
}
'''.replace("FRAGMENT", fragment)
        compile_run(self, program)

    def test_mastering_luminance_compares_rational_values(self):
        source = (self.root / "xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodec.cpp").read_text()
        compare = method(source, "VideoPicture::CompareDisplayMetadata")
        prefix = os.environ.get("FFMPEG_TEST_PREFIX")
        includes = ("-I", str(Path(prefix) / "include")) if prefix else ()
        compile_run(self, r'''
#include <cassert>
extern "C" {
#include <libavutil/mastering_display_metadata.h>
}
struct VideoPicture {
 bool hasDisplayMetadata = true;
 AVMasteringDisplayMetadata displayMetadata{};
 bool CompareDisplayMetadata(const VideoPicture& pic) const;
};
COMPARE
int main() {
 VideoPicture configured, incoming;
 configured.displayMetadata.has_luminance = incoming.displayMetadata.has_luminance = 1;
 configured.displayMetadata.max_luminance = {10000000, 10000};
 configured.displayMetadata.min_luminance = {50, 10000};
 incoming.displayMetadata.max_luminance = {1000, 1};
 incoming.displayMetadata.min_luminance = {1, 200};
 assert(configured.CompareDisplayMetadata(incoming));
 incoming.displayMetadata.max_luminance = {4000, 1};
 assert(!configured.CompareDisplayMetadata(incoming));
 incoming.displayMetadata.max_luminance = {1000, 1};
 incoming.displayMetadata.min_luminance = {1, 100};
 assert(!configured.CompareDisplayMetadata(incoming));
 incoming.displayMetadata.has_luminance = 0;
 assert(!configured.CompareDisplayMetadata(incoming));
 configured.displayMetadata.has_luminance = 0;
 assert(configured.CompareDisplayMetadata(incoming));
}
'''.replace("COMPARE", compare), includes)

    def test_source_depth_change_requires_configuration_before_render(self):
        source = (self.root / "xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodec.cpp").read_text()
        body = method(source, "VideoPicture::IsSameParams")
        compile_run(self, r'''
#include <cassert>
struct VideoPicture {
 int iWidth=1920,iHeight=1080,iDisplayWidth=1920,iDisplayHeight=1080;
 int stereoMode=0,color_primaries=1,color_transfer=1,hdrType=0,colorBits=8;
 bool CompareDisplayMetadata(const VideoPicture&) const {return true;}
 bool IsSameParams(const VideoPicture&) const;
};
BODY
int main(){VideoPicture configured,buffered;assert(configured.IsSameParams(buffered));
 buffered.colorBits=10;assert(!configured.IsSameParams(buffered));
 configured.colorBits=10;assert(configured.IsSameParams(buffered));}
'''.replace("BODY", body))
        for backend in ("GL", "GLES"):
            renderer = (self.root / f"xbmc/cores/VideoPlayer/VideoRenderers/LinuxRenderer{backend}.cpp").read_text()
            addition = method(renderer, f"CLinuxRenderer{backend}::AddVideoPicture")
            check = method(renderer, f"CLinuxRenderer{backend}::CheckVideoParameters")
            self.assertIn("buf.m_srcBits = picture.colorBits;", addition)
            self.assertIn("tmp.colorBits = buf.m_srcBits;", check)

    def test_range_changing_rejection_keeps_the_previous_pixels(self):
        source = (self.root / "xbmc/windowing/gbm/drm/DRMAtomic.cpp").read_text()
        start = source.index("    if (strict || m_req->sdrRestore || frameMetadata")
        end = source.index("    CLog::LogF(LOGERROR,", start)
        fragment = source[start:end]
        compile_run(self, r'''
#include <cassert>
constexpr unsigned DRM_MODE_FLAG_3D_MASK=16;
struct Request{bool sdrRestore=false;};struct Mode{unsigned flags=0;};
struct Window {
 bool strict=false,frameMetadata=false,m_colorRangeTransition=false;
 Request request;Request* m_req=&request;Mode mode;Mode* m_mode=&mode;
 int testError=22,framebuffer=11,tuple=1,fallbacks=0;
 bool reject(const char*,int){return false;}
 bool Submit(bool rejected){if(rejected){FRAGMENT ++fallbacks;framebuffer=22;return true;}
  framebuffer=22;tuple=2;return true;}
};
int main(){Window changed;changed.m_colorRangeTransition=true;
 assert(!changed.Submit(true) && changed.framebuffer==11 && changed.tuple==1 && !changed.fallbacks);
 assert(changed.Submit(false) && changed.framebuffer==22 && changed.tuple==2);
 Window ordinary;assert(ordinary.Submit(true) && ordinary.fallbacks==1);}
'''.replace("FRAGMENT", fragment))

    def test_video_and_gui_shaders_refresh_live_in_gl_and_gles(self):
        for backend in ("GL", "GLES"):
            with self.subTest(backend=backend):
                renderer = (self.root / f"xbmc/cores/VideoPlayer/VideoRenderers/LinuxRenderer{backend}.cpp").read_text()
                fragments = []
                cursor = 0
                while True:
                    start = renderer.find("  if (const bool fullRange = !CServiceBroker::GetWinSystem()->UseLimitedColor();", cursor)
                    if start < 0:
                        break
                    end = renderer.index("\n  }", start) + len("\n  }")
                    fragments.append(renderer[start:end])
                    cursor = end
                self.assertEqual(len(fragments), 1 if backend == "GL" else 2)
                for fragment in fragments:
                    compile_run(self, r'''
#include <cassert>
constexpr int VS_SCALINGMETHOD_MAX=999;
struct Window{bool limited=false;bool UseLimitedColor(){return limited;}};
struct CServiceBroker {static Window* GetWinSystem(){static Window w;return &w;}};
struct Renderer {
 bool m_fullRange=true,m_reloadShaders=false;int m_scalingMethodGui=0;
 void Update(){FRAGMENT}
};
int main(){Renderer r;r.Update();assert(!r.m_reloadShaders);
 CServiceBroker::GetWinSystem()->limited=true;r.Update();assert(!r.m_fullRange&&r.m_reloadShaders&&r.m_scalingMethodGui==999);
 r.m_reloadShaders=false;r.Update();assert(!r.m_reloadShaders);
 CServiceBroker::GetWinSystem()->limited=false;r.Update();assert(r.m_fullRange&&r.m_reloadShaders);}
'''.replace("FRAGMENT", fragment))
                gui = (self.root / f"xbmc/windowing/gbm/WinSystemGbm{backend}Context.cpp").read_text()
                body = method(gui, f"CWinSystemGbm{backend}Context::BeginGuiComposite")
                start = body.index("  if (!m_guiCompositing)")
                end = body.index("  m_guiWillRender = guiWillRender;")
                fragment = body[start:end]
                compile_run(self, r'''
#define HAVE_DVBRIDGE
#include <cassert>
#include <memory>
struct Manager {int dirty=0;void MarkDirty(){++dirty;} Manager& GetWindowManager(){return *this;}};
struct CServiceBroker {static Manager* GetGUI(){static Manager m;return &m;}};
struct CaptureState {bool captured=false;bool Captured() const{return captured;}};
struct Window {
 bool m_guiCompositing=true,m_compositeShaderLimited=false,m_hdrConversion=false,limited=false;
 int m_guiColorTransfer=74,rebuilds=0;CaptureState m_dvState;
 std::unique_ptr<int> m_compositeShader=std::make_unique<int>(1);
 bool UseLimitedColor(){return limited;}
 bool SetGuiCompositing(int transfer){assert(transfer==74);++rebuilds;m_compositeShaderLimited=limited;
  m_compositeShader=std::make_unique<int>(1);return true;}
 bool BeginGuiComposite(bool guiWillRender){FRAGMENT return true;}
};
int main(){Window w;w.BeginGuiComposite(false);assert(!w.rebuilds);
 w.limited=true;w.BeginGuiComposite(false);assert(w.rebuilds==1 && CServiceBroker::GetGUI()->dirty==1);
 w.BeginGuiComposite(false);assert(w.rebuilds==1);
 w.limited=false;w.BeginGuiComposite(true);assert(w.rebuilds==2 && CServiceBroker::GetGUI()->dirty==1);}
'''.replace("FRAGMENT", fragment))

    def test_atomic_fallback_retains_the_last_accepted_request(self):
        source = (self.root / "xbmc/windowing/gbm/drm/DRMAtomic.cpp").read_text()
        body = method(source, "CDRMAtomic::FinishRequest")
        program = r'''
#include <cassert>
#include <deque>
#include <memory>
#include <optional>
constexpr int LOGINFO=0;
struct CLog{template<class... T>static void Log(T...) {}};
namespace DVBRIDGE{bool DiagnosticsEnabled(){return false;}}
int close(int){return 0;}
struct CDRMAtomic {
 struct CDRMAtomicRequest {int id=0;bool sdrRestore=false;std::optional<bool> hdr10plus;
  std::optional<int> signalMode;int cacheCalls=0;void CacheProperties(){++cacheCalls;}};
 std::deque<std::unique_ptr<CDRMAtomicRequest>> m_atomicRequestQueue;
 CDRMAtomicRequest* m_req=nullptr;
 bool m_sdrRestoreFailed=false,m_signalDirty=false,m_propertyFailure=false,m_commitFellBack=false,m_colorRangeTransition=false;
 int m_committedMode=0,m_inFenceFd=-1;
 void SetSDRRestorePending(bool){} void AcceptHDR10Plus(bool){} void ReportSignalState(){}
 void FinishRequest(bool);
};
BODY
int main(){
 CDRMAtomic d;
 d.m_atomicRequestQueue.emplace_back(std::make_unique<CDRMAtomic::CDRMAtomicRequest>());
 d.m_req=d.m_atomicRequestQueue.back().get();d.m_req->id=11;d.FinishRequest(true);
 assert(d.m_atomicRequestQueue.front()->id==11);
 d.m_req->id=22;d.m_req=d.m_atomicRequestQueue.front().get();d.m_commitFellBack=true;d.FinishRequest(true);
 assert(d.m_atomicRequestQueue.size()==2 && d.m_atomicRequestQueue.front()->id==11);
 d.m_req->id=33;d.m_commitFellBack=false;d.FinishRequest(true);
 assert(d.m_atomicRequestQueue.front()->id==33);
 d.m_req->id=44;d.FinishRequest(false);assert(d.m_atomicRequestQueue.front()->id==33);
}
'''.replace("BODY", body)
        compile_run(self, program)


if __name__ == "__main__":
    unittest.main()
