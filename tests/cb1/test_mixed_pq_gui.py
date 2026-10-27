"""Exercise mixed PQ subtitles, native Master admission and GUI ownership."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class MixedPQGUI(unittest.TestCase):
    def test_master_mixed_overlay_and_generation_ownership(self):
        tree = TREE
        window = (tree/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        bridge = (tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        header = (tree/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h').read_text()
        render = body(window, 'bool CWinSystemGbmGLESContext::RenderDVBridge(')
        start = '  const bool mergedPQGUI =' if '  const bool mergedPQGUI =' in render else '  const bool subtitlesOnly ='
        route = render[render.index(start):render.index('  // The TV masks L5 margins.')]
        merge = body(window, 'bool CWinSystemGbmGLESContext::ComposeDVPQGUI(') if 'bool CWinSystemGbmGLESContext::ComposeDVPQGUI(' in window else '{return false;}'
        begin = body(window, 'bool CWinSystemGbmGLESContext::BeginGuiComposite(')
        reset = begin[begin.index('  m_dvSubtitleBounds = {};'):begin.index('#endif', begin.index('  m_dvSubtitleBounds = {};'))]
        if 'm_dvPQGuiMergeAttempted = m_dvPQGuiComposed = false;' in begin:
            reset = 'm_dvPQGuiMergeAttempted = m_dvPQGuiComposed = false;\n'+reset
        prepare = body(bridge, 'bool CDVBridgeGLES::Prepare(')
        direct = re.search(r'if \(!m_hdr10 && allowPacked.*?\n\s*\{', prepare, re.S).group(0)
        prepared = re.search(r'  m_prepared = m_direct \|\| .*?;', prepare, re.S).group(0)
        composite = body(window, 'void CWinSystemGbmGLESContext::CompositeGui(')
        gui_empty = composite[composite.index('    const bool guiEmpty ='):composite.index('    m_guiFboClean = guiEmpty;')]
        draw_tail = composite[composite.index('  if (!m_guiFboClean'):]
        sdr_draw = draw_tail[:draw_tail.index('\n  {')]
        constants = sorted((set(re.findall(r'\bGL_[A-Z0-9_]+\b', merge)) | {'GL_VIEWPORT'}) - {'GL_NO_ERROR', 'GL_FALSE', 'GL_TRUE'})
        calls = set(re.findall(r'\b(gl[A-Z]\w+)\(', merge))
        special = {'glGetError','glIsEnabled','glGetIntegerv','glGetBooleanv','glGenBuffers','glGenVertexArrays','glDrawArrays'}
        boundary = '\n'.join('template<class... T> void '+name+'(T...) {}' for name in sorted(calls-special))
        program = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <iterator>
#define HAVE_DVBRIDGE 1
using GLenum=unsigned;using GLuint=unsigned;using GLint=int;using GLfloat=float;using GLboolean=bool;
enum {GL_NO_ERROR=0,GL_FALSE=0,GL_TRUE=1,@@CONSTANTS@@};
unsigned draws=0;GLenum error=0;bool failDraw=false;
GLenum glGetError(){auto e=error;error=0;return e;}bool glIsEnabled(GLenum){return false;}
void glGetIntegerv(GLenum key,GLint* p){std::fill_n(p,key==GL_VIEWPORT?4:1,0);}
void glGetBooleanv(GLenum,GLboolean* p){std::fill_n(p,4,true);}
void glGenBuffers(int,GLuint* p){*p=1;}void glGenVertexArrays(int,GLuint* p){*p=2;}
void glDrawArrays(GLenum,int,int){++draws;if(failDraw)error=99;}
@@BOUNDARY@@
enum {DVBRIDGE_MODE_MASTER_REFERENCE=5,DVBRIDGE_MODE_ENHANCED_DV=3};
struct CDVBridgeGLES {static bool CanComposeSDRGUI(bool enabled,bool hdr10,bool capture,int width,int height,unsigned pqDraws) @@COMPOSE@@};
struct CRect {};
struct FBO{bool IsValid(){return true;}bool BeginRender(){return true;}GLuint Texture(){return 1;}};
struct Shader{const float* projection=nullptr;void SetInputPQ(bool){}void SetProjection(const float*p){projection=p;}
 int GetPosLoc(){return 0;}int GetTexLoc(){return 1;}bool Enable(){return true;}void Disable(){}};
struct Window {
 bool m_dvPQGuiMergeAttempted=false,m_dvPQGuiComposed=false,m_guiWillRender=true,m_hdrConversion=false;
 bool m_dvPQSubtitleCleared=false,m_cb1FramePending=false,m_dvFrame=false,m_dvNativeGui=false;
 unsigned m_dvGUIContentGeneration=0,m_dvSubtitleDraws=0,m_dvPQSubtitleDraws=0,m_dvSubtitleContent=0,count=0;
 int m_guiFboWidth=8,m_guiFboHeight=6,m_nWidth=8,m_nHeight=6,m_dvPQSubtitleWidth=8,m_dvPQSubtitleHeight=6;
 FBO m_guiFbo,m_dvPQSubtitleFbo;Shader shader;Shader* m_compositeShader=&shader;CRect m_dvSubtitleBounds;
 struct{struct{int mode=1;}policy;}m_dvSelection;
 struct{bool Captured(){return true;}}m_dvState;
 unsigned GetGUIElementCount(){return count;}
 void Redraw(){@@RESET@@}
 bool ComposeDVPQGUI() @@MERGE@@
 bool GUIIsClean(){bool hasPQSubtitles=m_dvPQSubtitleDraws!=0;@@GUI_EMPTY@@return guiEmpty;}
 bool SDRConsumed(){bool hasPQSubtitles=m_dvPQSubtitleDraws!=0;bool m_guiFboClean=GUIIsClean();@@SDR_DRAW@@
 {return false;}return true;}
 bool Ready(bool pgs,unsigned gui,int mode){
  count=1+gui;m_dvSubtitleDraws=1;m_dvPQSubtitleDraws=pgs?1:0;m_dvSelection.policy.mode=mode;
  bool capturing=false,masterCapture=false;struct{bool optimizedDV=true;}preferences;
  struct Meta{void*Data(){return (void*)1;}int Size(){return 1;}}metadata;
  @@ROUTE@@
  (void)enhancedSubtitles;(void)pqSubtitles;
  // Valid native wrapping is the external boundary; retain the shipped direct/RGB selection.
  bool allowPacked=fullGUI||subtitlesOnly,m_hdr10=false,m_directUsable=true,m_scanout=true,m_direct=false,m_prepared=false,hdr10plus=false;
  int m_effectiveMode=mode,m_renderer=0,hdrSession=0;int*m_hdr10Session=&hdrSession;
  struct{int frame=0;}bl;struct{double pts=0;}base;double elPts=0;
  struct{int x=0,y=0,width=8,height=6,target_width=8,target_height=6;}geometry;
  auto dvbridge_render_hdr10_rgb=[](auto...){return true;};auto dvbridge_render_rgb=[](auto...){return true;};
  @@DIRECT@@m_direct=true;}
  @@PREPARED@@
  return m_prepared;
 }
};
int main(){
 Window w;w.Redraw();assert(w.Ready(false,0,5));assert(w.Ready(false,3,5));assert(w.Ready(true,0,5));assert(w.Ready(true,3,1));
 w.Redraw();assert(w.Ready(true,3,5)&&"Master PGS+GUI must prepare");const auto once=draws;
 assert(!w.GUIIsClean()&&"merging must not mark the physically dirty SDR source clean");
 assert(once==1);assert(w.Ready(true,3,5)&&draws==once&&"same GUI generation must not blend twice");
 assert(w.shader.projection==nullptr&&"shared shader must not retain stack projection");
 w.Redraw();assert(w.Ready(true,3,5)&&draws==once+1&&"paused redraw must merge exactly once again");
 w.Redraw();assert(w.Ready(true,0,5)&&draws==once+1&&"menu close returns to PGS-only without stale GUI");
 w.Redraw();assert(w.Ready(true,3,1)&&draws==once+1);assert(w.Ready(true,3,5)&&draws==once+2&&"actual selected mode must admit first Master frame");
 assert(w.Ready(true,3,1)&&w.SDRConsumed()&&"same-generation Master-to-Standard must consume merged PQ once, not redraw SDR");
 w.Redraw();assert(w.Ready(true,3,1)&&!w.SDRConsumed()&&"ordinary Standard generation retains its two-layer compositor");
 w.Redraw();failDraw=true;assert(!w.Ready(true,3,5)&&!w.m_dvPQGuiComposed);const auto failed=draws;
 failDraw=false;assert(!w.Ready(true,3,5)&&draws==failed&&"failed generation cannot accumulate");
 w.Redraw();assert(w.Ready(true,3,5)&&draws==failed+1);
}
'''
        for key, value in {'CONSTANTS': ','.join(constants), 'BOUNDARY': boundary,
                           'COMPOSE': body(header, 'static constexpr bool CanComposeSDRGUI('),
                           'RESET': reset, 'MERGE': merge, 'ROUTE': route, 'DIRECT': direct,
                           'PREPARED': prepared, 'GUI_EMPTY': gui_empty, 'SDR_DRAW': sdr_draw}.items():
            program = program.replace('@@'+key+'@@', value)
        with tempfile.TemporaryDirectory() as temporary:
            source, binary = Path(temporary)/'check.cpp', Path(temporary)/'check'
            source.write_text(program)
            built = subprocess.run(['c++','-std=c++20',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__ == '__main__':
    unittest.main()
