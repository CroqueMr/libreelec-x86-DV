"""CB1 consumes Kodi's filter choice without a second Auto policy."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class NativeSpatialContractTests(unittest.TestCase):
    def test_native_zoom_and_fractional_placement_are_preserved(self):
        text = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp").read_text()
        geometry = body(text, "dvbridge_geometry CRendererVAAPIGLES::DVBridgeGeometry()")
        guard = body(text, "bool CRendererVAAPIGLES::DVBridgeOrientationSupported(")
        self.run_program(r'''
#include <algorithm>
#include <cassert>
#include <cmath>
struct CRect {float x1,y1,x2,y2;float Width()const{return x2-x1;}float Height()const{return y2-y1;}
 void Intersect(const CRect& r){x1=std::max(x1,r.x1);y1=std::max(y1,r.y1);x2=std::min(x2,r.x2);y2=std::min(y2,r.y2);} };
struct Context {int GetWidth()const{return 1920;}int GetHeight()const{return 1080;}};
struct Window {int w=3840,h=2160;Context c;int GetWidth()const{return w;}int GetHeight()const{return h;}const Context& GetGfxContext()const{return c;}} window;
struct CServiceBroker {static Window* GetWinSystem(){return &window;}};
struct dvbridge_geometry{int source_width,source_height,x,y,width,height,target_width,target_height;float crop[4],placement[4];};
struct Test {int m_sourceWidth=1920,m_sourceHeight=800;struct {int m_Orientation=90;}m_videoSettings;
 CRect dest{-336,0,2256,1080};
 void GetVideoRect(CRect& s,CRect& d,CRect& v){s={0,0,float(m_sourceWidth),float(m_sourceHeight)};d=dest;v={0,0,1920,1080};}
 dvbridge_geometry run() GEOMETRY
 bool rotation(unsigned int orientation)const GUARD
};
int main(){Test t;auto g=t.run();assert(g.x==0 && g.width==3840);
 assert(std::abs(g.crop[0]-248.88889f)<.001f && std::abs(g.crop[2]-1671.1111f)<.001f);
 t.dest={0,140,1920,940};window.w=2560;window.h=1440;g=t.run();
 assert(std::abs(g.placement[1]-186.66667f)<.001f && std::abs(g.placement[3]-1253.3333f)<.001f);
 assert(t.rotation(0));assert(!t.rotation(90) && !t.rotation(180) && !t.rotation(270));}
'''.replace("GEOMETRY", geometry).replace("GUARD", guard))

    def test_screenshot_readback_uses_current_surface_size(self):
        text = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp").read_text()
        capture = body(text, "bool CDVBridgeGLES::ReadScreenshot(")
        prefix = capture[1:capture.index("  if (!read)")]
        self.run_program(r'''
#include <cassert>
constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=5,GL_READ_FRAMEBUFFER_BINDING=1,GL_READ_FRAMEBUFFER=2;
using GLint=int;void glGetIntegerv(int,int* p){*p=0;}void glBindFramebuffer(int,unsigned){}
namespace KODI::RENDERING::CAPTURE {
 struct ReadbackBuffer{int width=0,height=0;};
 bool ReadFramebufferRegion(int,int,int w,int h,int,bool,ReadbackBuffer& p){p.width=w;p.height=h;return true;}
}
struct Test{
 int m_effectiveMode=1;bool m_prepared=true,m_direct=true;unsigned m_scanoutFramebuffer=0;
 struct Texture{struct{int w=1920,h=1080;}params;} texture;Texture* m_scanout=&texture;
 unsigned GetPQFramebuffer(){return 2;}
 bool run(){ PREFIX return read && pixels.width==texture.params.w && pixels.height==texture.params.h;}
};
int main(){Test t;assert(t.run());t.m_effectiveMode=5;assert(t.run());
 t.texture.params={2560,1440};assert(t.run());t.m_scanout=nullptr;assert(!t.run());}
'''.replace("PREFIX",prefix))

    def test_direct_hdr_admission_uses_actual_target(self):
        text = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp").read_text()
        prepare = body(text, "bool CDVBridgeGLES::Prepare(")
        start = prepare.index("  if (m_hdr10 && !hdr10plus && allowPacked")
        condition = prepare[start:prepare.index("  {", start)]
        self.run_program(r'''
#include <cassert>
bool admit(int width,int height,bool whole=true){
 bool m_hdr10=true,hdr10plus=false,allowPacked=true,m_directUsable=true,m_scanout=true;
 struct {int x,y,width,height,target_width,target_height;} geometry{0,0,whole?width:width-2,height,width,height};
 CONDITION return true;return false;
}
int main(){assert(admit(1920,1080) && admit(2560,1440) && admit(3840,2160));
 assert(!admit(1920,1080,false));}
'''.replace("CONDITION",condition))

    def test_dv_mode_admission_accepts_native_targets_not_stale_uhd_only(self):
        text = (TREE / "xbmc/windowing/gbm/WinSystemGbm.cpp").read_text()
        function = body(text, "bool CWinSystemGbm::SupportsDVOutputMode(")
        start = function.index("  const auto usable =")
        predicate = function[start:function.index("  if (usable(", start)]
        self.run_program(r'''
#include <cassert>
#include <cstdint>
constexpr int DRM_MODE_FLAG_INTERLACE=1,DRM_MODE_FLAG_DBLSCAN=2;
struct drmModeModeInfo {int hdisplay,vdisplay,clock=148500,htotal=2200,vtotal=1125,flags=0;};
struct CResolutionUtils {static bool IsCB1RefreshRate(double value){return value>=10 && value<=60;}};
int main(){PREDICATE
 assert(!usable(nullptr));
 for(int width: {1280,1920,2560,3840}){drmModeModeInfo mode{width,width*9/16};assert(usable(&mode));}
 drmModeModeInfo invalid{4096,2160};assert(!usable(&invalid));
 invalid={1921,1080};assert(!usable(&invalid));invalid={1920,0};assert(!usable(&invalid));
 invalid={1920,1080};invalid.flags=DRM_MODE_FLAG_INTERLACE;assert(!usable(&invalid));
 invalid.flags=0;invalid.clock*=2;assert(!usable(&invalid));
}
'''.replace("PREDICATE", predicate).replace("#include <cstdint>", "#include <cstdint>\n#include <initializer_list>"))

    def test_overlay_wrap_and_bounds_follow_current_scanout(self):
        text = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp").read_text()
        overlay = body(text, "bool CDVBridgeGLES::SetNativeOverlay(")
        self.run_program(r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <iterator>
constexpr int GL_R16F=1,GL_RGBA16F=2,GL_RGBA8=3;
struct Texture {struct {int w,h;}params;};using pl_tex=Texture*;
struct pl_opengl_wrap_params {unsigned texture=0;int width=0,height=0,iformat=0;};
void pl_tex_destroy(int,pl_tex* t){delete *t;*t=nullptr;}
pl_tex pl_opengl_wrap(int,const pl_opengl_wrap_params* p){return new Texture{{p->width,p->height}};}
struct CRect {float x1,y1,x2,y2;bool IsEmpty()const{return x1==x2||y1==y2;}};
struct Test {
 struct {int gpu=1;} gl;decltype(&gl) m_gl=&gl;
 Texture scanout{{1920,1080}};pl_tex m_scanout=&scanout;
 struct {float rect[4]{};bool input_pq=false;pl_tex texture=nullptr,degamma=nullptr,pq=nullptr;} m_nativeOverlay;
 bool m_nativeOverlayEnabled=false;uint64_t m_nativeOverlayRevision=0,m_nativeOverlayContent=0;
 unsigned m_nativeOverlayTextures[3]{};
 bool SetNativeOverlay(unsigned texture,unsigned degamma,unsigned pq,const CRect& bounds,uint64_t content,bool inputPQ) OVERLAY
 ~Test(){pl_tex_destroy(1,&m_nativeOverlay.texture);pl_tex_destroy(1,&m_nativeOverlay.degamma);pl_tex_destroy(1,&m_nativeOverlay.pq);}
};
int main(){Test t;
 assert(t.SetNativeOverlay(1,2,3,{0,0,3840,2160},1,false));
 assert(t.m_nativeOverlay.texture->params.w==1920 && t.m_nativeOverlay.texture->params.h==1080);
 assert(t.m_nativeOverlay.rect[2]==1920 && t.m_nativeOverlay.rect[3]==1080);
 auto revision=t.m_nativeOverlayRevision;t.scanout.params={1280,720};
 assert(t.SetNativeOverlay(1,2,3,{0,0,3840,2160},1,false));
 assert(t.m_nativeOverlayRevision>revision);
 assert(t.m_nativeOverlay.texture->params.w==1280 && t.m_nativeOverlay.texture->params.h==720);
 assert(t.m_nativeOverlay.degamma->params.w==256 && t.m_nativeOverlay.degamma->params.h==1);
 t.m_scanout=nullptr;assert(!t.SetNativeOverlay(1,2,3,{0,0,1280,720},1,false));
}
'''.replace("OVERLAY", overlay))

    def test_scanout_size_comes_from_current_egl_surface(self):
        text = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp").read_text()
        rebind = body(text, "bool CDVBridgeGLES::RebindOutputSurface(")
        prefix = rebind[1:rebind.index("  GLint draw,")]
        self.run_program(r'''
#include <cassert>
using EGLint=int;
constexpr int EGL_DRAW=1,EGL_WIDTH=2,EGL_HEIGHT=3,EGL_NO_DISPLAY=0,EGL_NO_SURFACE=0;
int display=1,surface=1,w=1920,h=1080;bool valid=true;
int eglGetCurrentDisplay(){return display;}int eglGetCurrentSurface(int){return surface;}
bool eglQuerySurface(int,int,int attr,int* out){*out=attr==EGL_WIDTH?w:h;return valid;}
struct pl_opengl_wrap_params{int width=0,height=0;};
struct Test {bool m_gl=true,m_pending=false,m_prepared=false;
 bool run(){ PREFIX
 return output.width==w && output.height==h;
 }};
int main(){Test t;assert(t.run());w=2560;h=1440;assert(t.run());w=3840;h=2160;assert(t.run());
 w=0;assert(!t.run());w=1921;assert(!t.run());w=1920;h=0;assert(!t.run());
 h=1080;valid=false;assert(!t.run());valid=true;surface=0;assert(!t.run());
 surface=1;display=0;assert(!t.run());}
'''.replace("PREFIX", prefix))

    def test_native_carrier_pack_accepts_current_target_and_rejects_stale_target(self):
        text = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp").read_text()
        pack = body(text, "bool CDVBridgeGLES::Pack(")
        program = r'''
#include <cassert>
#include <cstdint>
constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=5;
struct Texture {struct {int w,h;} params{1920,1080};};
struct Identity{};
struct Submission {Identity id;Texture* texture;uint64_t serial,sequence;bool eligible;};
struct Output {uint64_t resolve_serial=3;};
static Output result;
bool dvbridge_render_dv_policy_resolve(void*,Texture*,unsigned,bool){return true;}
Output* dvbridge_render_dv_policy_output(void*){return &result;}
void* dvbridge_render_candidate(void*){return nullptr;}
const uint32_t* dvbridge_packets(void*,unsigned* count){*count=0;return nullptr;}
bool dvbridge_gl_pack(void*,unsigned,unsigned,int,int,const uint32_t*,unsigned,bool){return true;}
struct CDVBridgeGLES {
 bool m_packed=false,m_prepared=true,m_advanced=false,m_dvPolicyActive=false;
 bool m_direct=true,m_live=true,m_asyncEligible=true,m_directUsable=true;
 unsigned m_scanoutFramebuffer=0;Texture texture;Texture* m_scanout=&texture;
 void* m_renderer=nullptr;void* m_packer=nullptr;int m_effectiveMode=5;
 Identity m_pendingIdentity;uint64_t m_submissionSequence=0;Submission m_submission{};
 bool Failure(const char*){return false;}unsigned GetPQTexture(){return 0;}
 bool Pack(unsigned framebuffer,int width,int height,bool flipY) PACK
};
int main(){
 for(auto size: {1280,1920,2560,3840}) {
  CDVBridgeGLES r;r.texture.params={size,size*9/16};
  assert(r.Pack(0,size,size*9/16,true));
  assert(!r.Pack(0,size+2,size*9/16,true));
  assert(!r.Pack(0,size,size*9/16,false));
  r.m_advanced=r.m_dvPolicyActive=true;
  assert(r.Pack(0,size,size*9/16,true));
  assert(!r.Pack(0,size+2,size*9/16,true));
 }
}
'''.replace("PACK", pack).replace("#include <cstdint>", "#include <cstdint>\n#include <initializer_list>")
        self.run_program(program)

    def run_program(self, program):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "test.cpp").write_text(program)
            built = subprocess.run(["c++", "-std=c++20", str(root / "test.cpp"),
                                    "-o", str(root / "test")], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / "test")], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_original_filter_choice_survives_shared_resolution(self):
        text = (TREE / "xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp").read_text()
        signature = "ESCALINGMETHOD CLinuxRendererGLES::SelectScalingMethod() const"
        if signature in text:
            policy = body(text, signature)
        else:
            original = body(text, "void CLinuxRendererGLES::UpdateVideoFilter()")
            supported = original[original.index("  if(!Supports(m_scalingMethod))"):
                                 original.index("  if (m_pVideoFilterShader)")]
            auto = original[original.index("  if (m_scalingMethod == VS_SCALINGMETHOD_AUTO)"):
                            original.index("  if (m_scalingMethod != previousMethod)")]
            policy = "{ auto method=m_videoSettings.m_ScalingMethod;\n" + (
                supported + auto).replace("m_scalingMethod", "method") + "return method; }"
        program = r'''
#include <cassert>
#include "cores/VideoSettings.h"
constexpr int LOGWARNING=1;
struct CLog { template<class... T>static void Log(T&&...){} };
struct Advanced { float m_videoAutoScaleMaxFps=30; };
struct Component { Advanced a; Advanced* GetAdvancedSettings(){ return &a; } };
struct CServiceBroker { static Component* GetSettingsComponent(){static Component c; return &c;} };
struct CLinuxRendererGLES {
 struct { ESCALINGMETHOD m_ScalingMethod=VS_SCALINGMETHOD_AUTO; } m_videoSettings;
 float m_sourceWidth=640,m_sourceHeight=360,m_fps=24;
 struct { float Width()const{return 3840;} float Height()const{return 2160;} } m_viewRect;
 bool supported=true;
 bool Supports(ESCALINGMETHOD)const{return supported;}
 ESCALINGMETHOD SelectScalingMethod() const POLICY
};
int main() {
 CLinuxRendererGLES r;
 assert(r.SelectScalingMethod()==VS_SCALINGMETHOD_LANCZOS3_FAST);
 r.m_fps=60;assert(r.SelectScalingMethod()==VS_SCALINGMETHOD_LINEAR);
 r.m_fps=24;r.m_sourceWidth=1920;r.m_sourceHeight=1080;
 assert(r.SelectScalingMethod()==VS_SCALINGMETHOD_LINEAR);
 r.m_videoSettings.m_ScalingMethod=VS_SCALINGMETHOD_LANCZOS3;
 assert(r.SelectScalingMethod()==VS_SCALINGMETHOD_LANCZOS3);
 r.supported=false;assert(r.SelectScalingMethod()==VS_SCALINGMETHOD_LINEAR);
 r.m_videoSettings.m_ScalingMethod=VS_SCALINGMETHOD_AUTO;
 assert(r.SelectScalingMethod()==VS_SCALINGMETHOD_LINEAR);
 r.supported=true;r.m_videoSettings.m_ScalingMethod=VS_SCALINGMETHOD_NEAREST;
 assert(r.SelectScalingMethod()==VS_SCALINGMETHOD_NEAREST);
}
'''.replace("POLICY", policy)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "test.cpp").write_text(program)
            built = subprocess.run(["c++", "-std=c++20", "-I" + str(TREE / "xbmc"),
                                    str(root / "test.cpp"), "-o", str(root / "test")],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / "test")], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == "__main__":
    unittest.main()
