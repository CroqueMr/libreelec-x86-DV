"""Native GUI binding must restore Kodi's viewport after offscreen AI work."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class GUIViewportTests(unittest.TestCase):
    def test_offscreen_analysis_does_not_shrink_the_next_gui(self):
        renderer = (TREE/'xbmc/rendering/gles/RenderSystemGLES.cpp').read_text()
        window = (TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        fbo = (TREE/'xbmc/cores/VideoPlayer/VideoRenderers/FrameBufferObject.cpp').read_text()
        program = r'''
#define HAVE_DVBRIDGE
#include <cassert>
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fmt/format.h>
#include <string>
#include <vector>
using GLint=int;using GLsizei=int;
constexpr int GL_FRAMEBUFFER=1,GL_TEXTURE_2D=2,GL_RGBA=3,GL_COLOR_BUFFER_BIT=4;
constexpr int GL_VIEWPORT=5,GL_FRAMEBUFFER_BINDING=6;
constexpr int LOGERROR=1,LOGDEBUG=2,LOGINFO=3;
std::array<int,4> viewport{},scissor{};
unsigned queries=0;
void glGetIntegerv(int key,int* out){++queries;if(key==GL_VIEWPORT)std::copy(viewport.begin(),viewport.end(),out);else *out=71;}
namespace DVBRIDGE {
@INTERVAL@;
bool enabled=true;uint64_t now=0;
bool DiagnosticsEnabled(){return enabled;}
uint64_t DiagnosticNowMs(){return now;}
std::vector<std::string> lines;
template<class...T>bool DiagnosticLog(int,fmt::format_string<T...> f,T&&...a){
 lines.push_back(fmt::format(f,std::forward<T>(a)...));return false;}
}
void glViewport(int x,int y,int w,int h){viewport={x,y,w,h};}
void glScissor(int x,int y,int w,int h){scissor={x,y,w,h};}
void glBindFramebuffer(int,int){}void glClearColor(float,float,float,float){}void glClear(int){}
struct CRect {float x1=0,y1=0,x2=0,y2=0;
 float Width()const{return x2-x1;}float Height()const{return y2-y1;}};
struct CLog {template<class... T>static void Log(T...){}};
namespace MathUtils {int round_int(double value){return int(std::lround(value));}}
struct CRenderSystemGLES {
 bool m_bRenderCreated=true;int m_height=2160,m_viewPort[4]{0,0,3840,2160};
 void GetViewPort(CRect& viewPort) @GET@
 void SetViewPort(const CRect& viewPort) @SET@
 void SetScissors(const CRect& rect) @SCISSORS@
};
struct FBO {
 int m_fbo=1;bool IsValid(){return true;}bool IsBound(){return true;}
 bool BeginRender() @BIND@
 void Cleanup(){}bool Initialize(){return true;}
 bool CreateAndBindToTexture(int,int,int,int){return true;}bool AttachDepthBuffer(int,int){return true;}
};
struct CWinSystemGbmGLESContext:CRenderSystemGLES {
 int m_nWidth=3840,m_nHeight=2160,m_guiFboWidth=3840,m_guiFboHeight=2160;
 FBO m_guiFbo,m_dvPQSubtitleFbo;
 void* m_dvContext=nullptr;
 bool m_guiCompositing=true,m_guiWillRender=false,m_guiFboClean=false,m_hdrConversion=false;
 bool m_dvPQGuiMergeAttempted=false,m_dvPQGuiComposed=false,m_cb1FramePending=false,m_dvFrame=false;
 bool m_dvPQSubtitleCleared=false,m_dvNativeGui=false;
 unsigned m_dvGUIContentGeneration=0,m_dvSubtitleDraws=0,m_dvSubtitleContent=0,m_dvPQSubtitleDraws=0;
 int m_dvPQSubtitleWidth=0,m_dvPQSubtitleHeight=0;
 CRect m_dvSubtitleBounds;
 DVBRIDGE::DiagnosticInterval m_dvGuiDiagnostic;
 struct State{bool captured=true;bool Captured(){return captured;}}m_dvState;
 struct Context{
  CRect clip{0,0,3840,2160};CRect GetScissors()const{return clip;}
  CRect StereoCorrection(CRect value)const{return value;}
 }context;
 const Context& GetGfxContext(){return context;}
 bool GetEnabledFrontToBackRendering(){return false;}
 bool HasDVBridgeScreenshot(){return false;}bool BeginDVPQSubtitle(){return false;}void EndDVPQSubtitle(){}
 bool BeginGuiComposite(bool guiWillRender) @BEGIN@
};
int main(){
 for(bool hdr:{false,true})for(int size:{2160,1080,720}){
  CWinSystemGbmGLESContext window;
  window.m_height=window.m_nHeight=size;window.m_nWidth=size*16/9;
  window.m_guiFboWidth=window.m_nWidth;window.m_guiFboHeight=size;
  window.m_dvState.captured=!hdr;window.m_hdrConversion=hdr;
  window.context.clip={7,11,float(window.m_nWidth-13),float(size-17)};
  // Kodi owns this logical viewport. The AI raster dispatch bypasses its cache.
  CRect intended{17,23,float(window.m_nWidth-31),float(size-47)};
  window.SetViewPort(intended);const auto expected=viewport;
  glViewport(0,0,64,36);
  DVBRIDGE::lines.clear();queries=0;DVBRIDGE::now=0;DVBRIDGE::enabled=true;
  assert(window.BeginGuiComposite(true));
  assert(viewport==expected && "AI analysis viewport leaked into native GUI rendering");
  const std::array<int,4> expectedClip{7,17,window.m_nWidth-20,size-28};
  assert(scissor==expectedClip && "Viewport restoration must not replace Kodi's clip");
  assert(DVBRIDGE::lines.size()==1 && "Missing GUI viewport witness");
  const auto& line=DVBRIDGE::lines.back();
  for(auto part:{"before=0,0,64,36","framebuffer=71","fbo=","after="})
   assert(line.find(part)!=std::string::npos);
  const auto readCount=queries;assert(readCount==3);
  // Even a saturated common log budget must not trigger per-frame GL queries.
  for(unsigned n=0;n<100;++n)assert(window.BeginGuiComposite(true));
  assert(queries==readCount && DVBRIDGE::lines.size()==1);
  DVBRIDGE::now=5000;assert(window.BeginGuiComposite(true));
  assert(queries==readCount+3 && DVBRIDGE::lines.size()==2);
  DVBRIDGE::enabled=false;DVBRIDGE::now=10000;
  assert(window.BeginGuiComposite(true) && queries==readCount+3);
  DVBRIDGE::enabled=true;DVBRIDGE::now=15000;
  assert(window.BeginGuiComposite(false) && queries==readCount+3);
  window.m_dvState.captured=false;window.m_hdrConversion=false;
  assert(window.BeginGuiComposite(true) && queries==readCount+3);
  assert(DVBRIDGE::lines.size()==2);
  window.m_guiCompositing=false;glViewport(0,0,19,11);
  assert(!window.BeginGuiComposite(true) && viewport[2]==19);
  // The first AI passes run before DV has captured its output and GUI FBO.
  // Native/direct GUI rendering must not inherit their tiny viewport either.
  window.m_dvContext=&window;DVBRIDGE::enabled=false;
  glViewport(0,0,128,72);
  assert(!window.BeginGuiComposite(true));
  assert(viewport==expected && "AI priming shrank the GUI before DV activation");
  assert(scissor==expectedClip && "AI priming lost Kodi's logical clip");
  glViewport(0,0,64,36);
  assert(!window.BeginGuiComposite(false) && viewport[2]==64); // No GUI drawing.
  window.m_guiCompositing=true;
  assert(window.BeginGuiComposite(true) && viewport==expected);
 }
}
'''
        for name, value in {
            'GET': body(renderer, 'void CRenderSystemGLES::GetViewPort('),
            'SET': body(renderer, 'void CRenderSystemGLES::SetViewPort('),
            'SCISSORS': body(renderer, 'void CRenderSystemGLES::SetScissors('),
            'BIND': body(fbo, 'bool CFrameBufferObject::BeginRender('),
            'BEGIN': body(window, 'bool CWinSystemGbmGLESContext::BeginGuiComposite('),
            'INTERVAL': 'class DiagnosticInterval'+body(
                (TREE/'xbmc/utils/DVBridgeDiagnosticState.h').read_text(), 'class DiagnosticInterval'),
        }.items():
            program=program.replace('@'+name+'@', value)
        with tempfile.TemporaryDirectory(prefix='gui-viewport-') as temporary:
            code,binary=Path(temporary)/'check.cpp',Path(temporary)/'check'
            code.write_text(program)
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                                  '-DFMT_HEADER_ONLY','-idirafter',os.environ.get('CB1_FMT_INCLUDE','/usr/include'),
                                  str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
