"""Execute Kodi's Initialize/Rebind methods on a real native 8-bit EGL surface."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE,body

ROOT=Path(__file__).resolve().parents[2]

class SDRNativeSurface(unittest.TestCase):
    def test_native_eight_bit_sdr_initialization_keeps_hdr_and_dv_gates(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        initialize=body(source,'bool CDVBridgeGLES::Initialize(')
        rebind=body(source,'bool CDVBridgeGLES::RebindOutputSurface(')
        vertex=(ROOT/'CB1/src/pack_gles300.vert').read_text()
        fragment=(ROOT/'CB1/src/pack_gles300.frag').read_text()
        program=r'''
#include <cassert>
#include <algorithm>
#include <cstdint>
#include <memory>
#include <utility>
#include <EGL/egl.h>
#include <GLES3/gl3.h>
extern "C" {
#include <libplacebo/opengl.h>
#include <libplacebo/renderer.h>
#include "dvbridge_gl_pack.h"
}
constexpr int LOGINFO=1;
namespace DVBRIDGE {bool DiagnosticsEnabled(){return false;}template<class... T>void DiagnosticLog(T...) {}}
constexpr char DVBRIDGE_VERTEX[]=R"SHADER(VERTEX)SHADER";
constexpr char DVBRIDGE_FRAGMENT[]=R"SHADER(FRAGMENT)SHADER";
struct CDVBridgeGLES {
 // Real OpenGL and libplacebo resources; no successful-initialization stand-in.
 struct Context {
  pl_opengl gl{};pl_renderer renderer{};
  bool Initialize(bool allowSoftware){
   pl_opengl_params p{};p.egl_display=eglGetCurrentDisplay();p.egl_context=eglGetCurrentContext();
   p.get_proc_addr=reinterpret_cast<pl_voidfunc_t(*)(const char*)>(eglGetProcAddress);
   p.allow_software=allowSoftware;gl=pl_opengl_create(nullptr,&p);return gl!=nullptr;
  }
  pl_opengl GL(){return gl;}pl_log Log(){return nullptr;}
  pl_renderer Attach(){renderer=pl_renderer_create(nullptr,gl->gpu);return renderer;}
  ~Context(){if(renderer)pl_renderer_destroy(&renderer);if(gl)pl_opengl_destroy(&gl);}
 };
 std::shared_ptr<Context> m_context;pl_opengl m_gl{};pl_log m_log{};pl_renderer m_renderer{};
 dvbridge_gl_packer* m_packer{};pl_tex m_scanout{};
 bool m_hdr10=false,m_pending=false,m_prepared=false,m_live=true;
 unsigned m_scanoutFramebuffer=99,m_outputBits=0;struct{}m_failedIdentity;
 bool Failure(const char*){return false;}
 bool Initialize(bool allowSoftware,bool hdr10,std::shared_ptr<Context> context={},bool sdr=false) INITIALIZE
 bool RebindOutputSurface(bool hdr10,bool sdr=false) REBIND
 ~CDVBridgeGLES(){if(m_scanout)pl_tex_destroy(m_gl->gpu,&m_scanout);if(m_packer)dvbridge_gl_packer_destroy(m_packer);}
};
int main(){
 EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);assert(display!=EGL_NO_DISPLAY);
 assert(eglInitialize(display,nullptr,nullptr));assert(eglBindAPI(EGL_OPENGL_ES_API));
 const EGLint attrs[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,
  EGL_RED_SIZE,8,EGL_GREEN_SIZE,8,EGL_BLUE_SIZE,8,EGL_ALPHA_SIZE,8,EGL_NONE};
 EGLConfig config{};EGLint count{};assert(eglChooseConfig(display,attrs,&config,1,&count)&&count==1);
 const EGLint surfaceAttrs[]={EGL_WIDTH,64,EGL_HEIGHT,32,EGL_NONE};
 EGLSurface surface=eglCreatePbufferSurface(display,config,surfaceAttrs);assert(surface!=EGL_NO_SURFACE);
 const EGLint contextAttrs[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
 EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,contextAttrs);assert(context!=EGL_NO_CONTEXT);
 assert(eglMakeCurrent(display,surface,surface,context));
 GLint r{},g{},b{};glGetIntegerv(GL_RED_BITS,&r);glGetIntegerv(GL_GREEN_BITS,&g);glGetIntegerv(GL_BLUE_BITS,&b);
 assert(r==8 && g==8 && b==8);
 GLuint draw{},read{};glGenFramebuffers(1,&draw);glGenFramebuffers(1,&read);
 glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);glBindFramebuffer(GL_READ_FRAMEBUFFER,read);
 {
  CDVBridgeGLES sdr;assert(sdr.Initialize(true,true,{},true));
  assert(sdr.m_hdr10 && sdr.m_scanout && sdr.m_outputBits==8 && sdr.m_scanoutFramebuffer==0);
  glBindFramebuffer(GL_DRAW_FRAMEBUFFER,draw);glBindFramebuffer(GL_READ_FRAMEBUFFER,read);
  assert(sdr.RebindOutputSurface(true,true));
  GLint current{};glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING,&current);assert(current==int(draw));
  glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING,&current);assert(current==int(read));
  sdr.m_pending=true;assert(!sdr.RebindOutputSurface(true,true));sdr.m_pending=false;
  sdr.m_prepared=true;assert(!sdr.RebindOutputSurface(true,true));sdr.m_prepared=false;
  CDVBridgeGLES hdr;assert(!hdr.Initialize(true,true)); // Native HDR still requires >=10 bits.
  CDVBridgeGLES dv;assert(dv.Initialize(true,false));assert(dv.m_scanout && dv.m_outputBits==8);
 }
 glBindFramebuffer(GL_FRAMEBUFFER,0);glDeleteFramebuffers(1,&draw);glDeleteFramebuffers(1,&read);
 assert(eglMakeCurrent(display,EGL_NO_SURFACE,EGL_NO_SURFACE,EGL_NO_CONTEXT));
 eglDestroyContext(display,context);eglDestroySurface(display,surface);eglTerminate(display);
}
'''.replace('INITIALIZE',initialize).replace('REBIND',rebind).replace('R"SHADER(VERTEX)SHADER"','R"SHADER('+vertex+')SHADER"').replace('R"SHADER(FRAGMENT)SHADER"','R"SHADER('+fragment+')SHADER"')
        env=dict(os.environ)
        prefix=env.get('FFMPEG_TEST_PREFIX')
        if prefix:
            env['PKG_CONFIG_PATH']=prefix+'/lib/pkgconfig:'+env.get('PKG_CONFIG_PATH','')
            env['LD_LIBRARY_PATH']=prefix+'/lib:'+env.get('LD_LIBRARY_PATH','')
        flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','libplacebo'],env=env,text=True))
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            built=subprocess.run(['cc','-std=c11','-I'+str(ROOT/'CB1/src'),'-c',str(ROOT/'CB1/src/dvbridge_gl_pack.c'),'-o',str(root/'pack.o')],env=env,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            built=subprocess.run(['c++','-std=c++20','-I'+str(ROOT/'CB1/src'),str(root/'test.cpp'),str(root/'pack.o'),*flags,'-lEGL','-lGLESv2','-o',str(root/'test')],env=env,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(root/'test')],env=dict(env,EGL_PLATFORM='surfaceless',LIBGL_ALWAYS_SOFTWARE='1'),capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)

    def test_source_depth_matrix_preserves_hdr_and_dv_restrictions(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        rebind=body(source,'bool CDVBridgeGLES::RebindOutputSurface(')
        start=rebind.index('  if (glCheckFramebufferStatus')
        admission=rebind[start:rebind.index('  glBindFramebuffer(GL_DRAW_FRAMEBUFFER',start)]
        program=r'''
#include <cassert>
#include <initializer_list>
constexpr int GL_FRAMEBUFFER=1,GL_FRAMEBUFFER_COMPLETE=2,GL_LINEAR=3;
int status=GL_FRAMEBUFFER_COMPLETE;
int glCheckFramebufferStatus(int){return status;}
bool pl_opengl_wrap(int,const int*){return true;}
bool admit(bool hdr10,bool sdr,int red,int green,int blue,int samples=0,int encoding=GL_LINEAR){
 struct{int gpu=0;}gl,*m_gl=&gl;int output=0;bool candidate=false;
 ADMISSION
 return candidate;
}
int main(){
 for(int bits:{8,10,12,16}){
  assert(admit(true,true,bits,bits,bits));
  assert(admit(true,false,bits,bits,bits)==(bits>=10));
  assert(admit(false,false,bits,bits,bits)==(bits==8));
 }
 assert(!admit(true,true,7,8,8));assert(!admit(true,true,8,7,8));assert(!admit(true,true,8,8,7));
 assert(!admit(true,true,32,32,32));
 assert(!admit(true,true,8,8,8,4));assert(!admit(true,true,8,8,8,0,0));
 status=0;assert(!admit(true,true,8,8,8));
}
'''.replace('ADMISSION',admission)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'matrix.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(root/'matrix.cpp'),'-o',str(root/'matrix')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'matrix')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__':unittest.main()
