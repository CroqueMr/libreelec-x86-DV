"""A submitted GUI pass is not evidence that the selected video picture rendered."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body
import test_diagnostics_runtime as diagnostic_test_support


class NativeRenderReceiptTests(unittest.TestCase):
    def test_rejected_pending_source_is_cleared_before_later_no_draw_commit(self):
        manager=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        stage=body(manager.split('// the just-presented region is video-only:',1)[1],'if (presented)')
        window_header=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.h').read_text()
        window_source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        native_stage=body(window_header,'void StageVideoSource(')
        native_publish=body(window_source,'void CWinSystemGbmGLESContext::PublishVideoSource(')
        program=r'''
#include <cassert>
#include <cstdint>
#include <memory>
#define HAVE_GBM
#define HAS_GLES
struct VideoSourceSideData {int frame; uint64_t Generation() const {return 1;}};
struct Cache {
 std::shared_ptr<const VideoSourceSideData> accepted;
 bool SetVideoSourceSideData(uint64_t generation,std::shared_ptr<const VideoSourceSideData> source){
  assert(generation==source->Generation()); accepted=std::move(source); return true;
 }
} cache;
struct WindowBase {virtual ~WindowBase()=default;};
struct CServiceBroker {
 static WindowBase* GetWinSystem();
 static Cache& GetDataCacheCore(){return cache;}
};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext:WindowBase {
 std::shared_ptr<const VideoSourceSideData> m_videoSourceSideData;
 void StageVideoSource(std::shared_ptr<const VideoSourceSideData> source) @@NATIVE_STAGE@@
 void PublishVideoSource(bool accepted,const std::shared_ptr<const VideoSourceSideData>& source) @@NATIVE_PUBLISH@@
 void Commit(bool accepted){PublishVideoSource(accepted,m_videoSourceSideData);}
};
}
KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
WindowBase* CServiceBroker::GetWinSystem(){return &window;}
struct Renderer {bool drawn=true; bool HasRenderedFrame() const{return drawn;}} renderer;
struct CRenderManager {
 Renderer* m_pRenderer=&renderer;
 struct Slot{std::shared_ptr<const VideoSourceSideData> sourceSideData;}m_Queue[1];
 unsigned m_presentsource=0;
 void ServiceVideoCaptures(){}
 void Present(){ @@STAGE@@ }
} manager;
int main(){
 auto a=std::make_shared<VideoSourceSideData>(VideoSourceSideData{1});
 auto b=std::make_shared<VideoSourceSideData>(VideoSourceSideData{2});
 auto c=std::make_shared<VideoSourceSideData>(VideoSourceSideData{3});
 manager.m_Queue[0].sourceSideData=a; manager.Present(); window.Commit(true);
 assert(cache.accepted==a);
 manager.m_Queue[0].sourceSideData=b; manager.Present(); window.Commit(false);
 assert(cache.accepted==a && window.m_videoSourceSideData==b);
 manager.m_Queue[0].sourceSideData=c; renderer.drawn=false;
 manager.Present(); window.Commit(true); // GUI/clear accepted, no video C drawn
 assert(cache.accepted==a && !window.m_videoSourceSideData);
 renderer.drawn=true; manager.Present(); window.Commit(true);
 assert(cache.accepted==c);
}
'''.replace('@@NATIVE_STAGE@@',native_stage).replace('@@NATIVE_PUBLISH@@',native_publish).replace('@@STAGE@@',stage)
        with tempfile.TemporaryDirectory(prefix='native-pending-source-') as folder:
            root=Path(folder); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_actual_gles_success_gates_source_but_keeps_render_decisions(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp').read_text()
        definitions='\n'.join(signature+body(source,signature) for signature in (
            'void CLinuxRendererGLES::RenderUpdate(int index, int index2, bool clear, unsigned int flags, unsigned int alpha)',
            'void CLinuxRendererGLES::RenderUpdateVideo(bool clear, unsigned int flags, unsigned int alpha)',
            'bool CLinuxRendererGLES::Render(unsigned int flags, int index)'))
        manager=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        stage=body(manager.split('// the just-presented region is video-only:',1)[1],'if (presented)')
        base=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/BaseRenderer.h').read_text()
        header=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.h').read_text()
        self.assertTrue('virtual bool HasRenderedFrame()' in base,'native unknown-render receipt is missing')
        self.assertTrue('bool HasRenderedFrame()' in header,'native GLES success receipt is missing')
        base_receipt=body(base,'virtual bool HasRenderedFrame()')
        receipt=body(header,'bool HasRenderedFrame()')
        program=r'''
#include <cassert>
#include <memory>
#include <array>
#define HAVE_GBM
#define HAS_GLES
constexpr int GL_BLEND=1,GL_SRC_ALPHA=2,GL_ONE_MINUS_SRC_ALPHA=3;
constexpr unsigned RENDER_FLAG_TOP=1,RENDER_FLAG_BOT=2,RENDER_GLSL=1;
constexpr int RQ_LOW=0,RQ_SINGLEPASS=1,RQ_MULTIPASS=2;
void glEnable(int){} void glDisable(int){} void glBlendFunc(int,int){} void VerifyGLState(){}
struct Shader {void SetAlpha(float){}};
struct CPictureBuffer {struct Plane {unsigned id=1;}; Plane fields[3][1];};
struct CBaseRenderer {
 virtual ~CBaseRenderer()=default;
 virtual bool HasRenderedFrame() const @@BASE@@
};
struct CLinuxRendererGLES:CBaseRenderer {
 bool m_bConfigured=true,m_frameRendered=false,gui=true,firstPass=false,upload=true;
 int m_iYUVRenderBuffer=0,m_currentField=0,m_renderMethod=RENDER_GLSL,m_renderQuality=RQ_SINGLEPASS;
 static constexpr int FIELD_FULL=0,FIELD_TOP=1,FIELD_BOT=2;
 CPictureBuffer m_buffers[4]; Shader* m_pYUVProgShader=nullptr; Shader* m_pYUVBobShader=nullptr;
 unsigned clears=0,draws=0,uploadCalls=0,afterCalls=0;
 bool IsGuiLayer(){return gui;}
 bool HasRenderedFrame() const override @@RECEIPT@@
 bool ValidateRenderTarget(){return firstPass;}
 void ClearBackBuffer(){++clears;} void DrawBlackBars(){} void ManageRenderArea(){}
 bool UploadTexture(int){++uploadCalls;return upload;}
 bool RenderHook(int){return false;} void UpdateVideoFilter(){}
 void RenderSinglePass(int,int){++draws;} void RenderToFBO(int,int){++draws;}
 void RenderFromFBO(){} void AfterRenderHook(int){++afterCalls;}
 bool Render(unsigned,int);
 void RenderUpdate(int,int,bool,unsigned,unsigned);
 void RenderUpdateVideo(bool,unsigned,unsigned);
};
@@RENDER_METHODS@@
struct WindowBase {virtual ~WindowBase()=default;};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext:WindowBase {
 std::shared_ptr<int> staged=std::make_shared<int>(1),accepted=staged;
 void StageVideoSource(std::shared_ptr<int> source){staged=std::move(source);}
 void GUICommit(){if(staged) accepted=staged;}
};
}
KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker {static WindowBase* GetWinSystem(){return &window;}};
struct CRenderManager {
 CBaseRenderer* m_pRenderer;
 struct Slot{std::shared_ptr<int> sourceSideData=std::make_shared<int>(2);}m_Queue[1];
 unsigned m_presentsource=0,captures=0;
 void ServiceVideoCaptures(){++captures;}
 void Stage(bool presented){if(presented) @@STAGE@@}
};
int main(){
 CLinuxRendererGLES renderer; CRenderManager manager{&renderer};
 renderer.firstPass=true; renderer.RenderUpdate(0,0,true,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==1 && !renderer.HasRenderedFrame() && renderer.clears==1);
 renderer.firstPass=false; renderer.RenderUpdate(0,0,false,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==2 && renderer.HasRenderedFrame() && renderer.draws==1);
 manager.m_Queue[0].sourceSideData=std::make_shared<int>(3);
 renderer.m_buffers[0].fields[0][0].id=0;
 renderer.RenderUpdate(0,0,false,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==2 && !renderer.HasRenderedFrame() && renderer.draws==1);
 renderer.m_buffers[0].fields[0][0].id=1; renderer.upload=false;
 renderer.RenderUpdate(0,0,true,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==2 && !renderer.HasRenderedFrame() && renderer.draws==1 && renderer.clears==2);
 renderer.upload=true; renderer.m_bConfigured=false;
 renderer.RenderUpdate(0,0,true,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==2 && !renderer.HasRenderedFrame());
 renderer.m_bConfigured=true; renderer.gui=false; renderer.upload=false;
 renderer.RenderUpdateVideo(true,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==2 && !renderer.HasRenderedFrame());
 renderer.upload=true; renderer.RenderUpdateVideo(false,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==3 && renderer.HasRenderedFrame() && renderer.draws==2);
 renderer.m_bConfigured=false; renderer.RenderUpdateVideo(false,0,255); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==3 && !renderer.HasRenderedFrame());
 CBaseRenderer unknown; manager.m_pRenderer=&unknown;
 manager.m_Queue[0].sourceSideData=std::make_shared<int>(4); manager.Stage(true); window.GUICommit();
 assert(*window.accepted==3 && !unknown.HasRenderedFrame());
 // This observer must not change historical capture/control entry semantics.
 assert(manager.captures==9 && renderer.draws==2 && renderer.afterCalls==2);
}
'''.replace('@@BASE@@',base_receipt).replace('@@RECEIPT@@',receipt).replace('@@RENDER_METHODS@@',definitions).replace('@@STAGE@@',stage)
        with tempfile.TemporaryDirectory(prefix='native-render-receipt-') as folder:
            root=Path(folder); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_source_omission_debug_diagnostics_share_the_sliding_budget(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        omission=body(source,'if (pVideoPicture->sourceSideData && pVideoPicture->sourceSideData->RejectedSections())')
        program=r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
#include <memory>
struct Source {unsigned RejectedSections(){return 31;}};
struct Picture {std::shared_ptr<Source> sourceSideData=std::make_shared<Source>();};
void capture(uint64_t m_videoProcessingGeneration,Picture* pVideoPicture) @@OMISSION@@
int main(){
 DVBRIDGE::DiagnosticOpen(); Picture picture;
 for(unsigned i=1;i<=200;++i) capture(i,&picture);
 assert(CLog::lines.size()==24);
 for(const auto& line:CLog::lines) assert(line.find("Native source side-data omitted")!=std::string::npos);
}
'''.replace('@@OMISSION@@',omission)
        diagnostic_test_support.DiagnosticsRuntime().run_cpp(program,{'utils/log.h':r'''
#pragma once
#include <fmt/format.h>
#include <string>
#include <vector>
constexpr int LOGDEBUG=0,LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
 inline static std::vector<std::string> lines;
 template<class... T> static void Log(int,fmt::format_string<T...> f,T&&... a){
  lines.push_back(fmt::format(f,std::forward<T>(a)...));
 }
};
'''})


if __name__=='__main__':unittest.main()
