/* SPDX-License-Identifier: GPL-2.0-or-later */
/* The Python runner supplies the actual shipped CompositeGui body. */
#include <EGL/egl.h>
#include <GLES3/gl31.h>
#include <array>
#include <cassert>
#include <cmath>
#include <cstring>
#include <fstream>
#include <iostream>
#include <memory>
#include <sstream>
#include <string>
#include "cb1_dv_enhanced_shader.h"
#define HAVE_DVBRIDGE 1

constexpr int width=8,height=2;
GLuint guiTexture,degammaTexture,pqTexture,finalFramebuffer,pqFramebuffer;
GLuint nativeProgram;
std::array<float,width*height*4> film{},gui{};

GLuint shader(GLenum kind,const std::string& text)
{
  GLuint value=glCreateShader(kind);const char* p=text.c_str();
  glShaderSource(value,1,&p,nullptr);glCompileShader(value);
  GLint ok;glGetShaderiv(value,GL_COMPILE_STATUS,&ok);
  if(!ok){char log[4096];glGetShaderInfoLog(value,sizeof(log),nullptr,log);std::cerr<<log;assert(ok);}
  return value;
}
GLuint program(const std::string& fragment,bool modern=false)
{
  const std::string vertex=modern?
      "#version 300 es\nin vec2 a_pos;void main(){gl_Position=vec4(a_pos,0,1);}":
      "attribute vec2 a_pos;attribute vec2 a_tex;varying vec2 v_tex;uniform mat4 u_proj;"
      "void main(){gl_Position=u_proj*vec4(a_pos,0,1);v_tex=a_tex;}";
  GLuint value=glCreateProgram();glAttachShader(value,shader(GL_VERTEX_SHADER,vertex));
  glAttachShader(value,shader(GL_FRAGMENT_SHADER,fragment));glLinkProgram(value);
  GLint ok;glGetProgramiv(value,GL_LINK_STATUS,&ok);assert(ok);return value;
}
GLuint texture(int w,int h,const float* pixels,GLint format=GL_RGBA32F)
{
  GLuint value;glGenTextures(1,&value);glBindTexture(GL_TEXTURE_2D,value);
  glTexImage2D(GL_TEXTURE_2D,0,format,w,h,0,GL_RGBA,GL_FLOAT,pixels);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_S,GL_CLAMP_TO_EDGE);
  glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_WRAP_T,GL_CLAMP_TO_EDGE);
  return value;
}
GLuint framebuffer(GLuint tex)
{
  GLuint value;glGenFramebuffers(1,&value);glBindFramebuffer(GL_FRAMEBUFFER,value);
  glFramebufferTexture2D(GL_FRAMEBUFFER,GL_COLOR_ATTACHMENT0,GL_TEXTURE_2D,tex,0);
  assert(glCheckFramebufferStatus(GL_FRAMEBUFFER)==GL_FRAMEBUFFER_COMPLETE);return value;
}
struct GUIFramebuffer {
  bool IsValid()const{return true;} bool IsBound()const{return true;}
  GLuint Texture()const{return guiTexture;}
};
struct CompositeShader {
  const GLfloat* m_proj{};bool m_inputPQ{};float m_outputScale=1,m_outputOffset=0,m_ootfGamma=0;
  GLuint m_lutDegammaTexId=degammaTexture,m_lutTFTexId=pqTexture;
  GLint m_hProj=glGetUniformLocation(nativeProgram,"u_proj");
  GLint m_hOotfGamma=glGetUniformLocation(nativeProgram,"u_ootfGamma");
  GLint m_hInputPQ=glGetUniformLocation(nativeProgram,"u_inputPQ");
  GLint m_hOutputRange=glGetUniformLocation(nativeProgram,"u_outputRange");
  void SetProjection(const GLfloat* p){m_proj=p;}
  void SetInputPQ(bool p){m_inputPQ=p;}
  void SetOutputRange(float s,float o){m_outputScale=s;m_outputOffset=o;}
  GLint GetPosLoc(){return glGetAttribLocation(nativeProgram,"a_pos");}
  GLint GetTexLoc(){return glGetAttribLocation(nativeProgram,"a_tex");}
  bool Enable(){
    glUseProgram(nativeProgram);
    glUniform1i(glGetUniformLocation(nativeProgram,"u_samp"),0);
    glUniform1i(glGetUniformLocation(nativeProgram,"u_lutDegamma"),1);
    glUniform1i(glGetUniformLocation(nativeProgram,"u_lutTF"),2);
    return OnEnabled();
  }
  bool OnEnabled() GUI_SHADER_ENABLE_BODY
  void Disable(){glUseProgram(0);}
};
struct Bridge {
  bool m_hdr10=true,m_prepared=true,m_direct=true,m_live=true,m_guiComposed=false;
  void* m_scanout=this;
  unsigned m_outputBits=10,m_scanoutFramebuffer=finalFramebuffer,pqQueries=0;
  GLuint GetPQFramebuffer(){++pqQueries;return m_direct?0:pqFramebuffer;}
  bool GetHDR10OutputTarget(unsigned& framebuffer,unsigned& bits) GUI_HDR_TARGET_BODY
};
struct DRM {void* GetVideoPlane(){return nullptr;} void* GetGuiPlane(){return nullptr;}};
struct State {bool Captured()const{return false;}};
struct CWinSystemGbmGLESContext {
  GUIFramebuffer m_guiFbo,m_dvPQSubtitleFbo;
  bool m_guiWillRender=true,m_guiFboClean=false,m_dvNativeGui=false;
  bool m_hdrConversion=true,m_dvFrame=true,limited=false;
  unsigned m_dvPQSubtitleDraws=0;bool m_dvPQGuiComposed=false;
  int m_guiFboWidth=width,m_guiFboHeight=height,m_nWidth=width,m_nHeight=height;
  State m_dvState;std::unique_ptr<DRM> m_DRM=std::make_unique<DRM>();
  std::unique_ptr<Bridge> m_dvBridge=std::make_unique<Bridge>();
  std::unique_ptr<CompositeShader> m_compositeShader=std::make_unique<CompositeShader>();
  bool HasDVBridgeScreenshot()const{return m_dvPQSubtitleDraws!=0;}
  unsigned GetGUIElementCount()const{return 2;}
  bool UseLimitedColor()const{return limited;}
  void CompositeGui() GUI_COMPOSITE_BODY
};

int main(int argc,char** argv)
{
  assert(argc==2);
  EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);assert(eglInitialize(display,nullptr,nullptr));
  assert(eglBindAPI(EGL_OPENGL_ES_API));
  EGLint attr[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
  EGLConfig config;EGLint count;assert(eglChooseConfig(display,attr,&config,1,&count)&&count);
  EGLint size[]={EGL_WIDTH,width,EGL_HEIGHT,height,EGL_NONE},version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
  EGLSurface surface=eglCreatePbufferSurface(display,config,size);
  EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
  assert(eglMakeCurrent(display,surface,surface,context));
  std::ifstream file(argv[1]);std::stringstream content;content<<file.rdbuf();assert(!content.str().empty());
  nativeProgram=program(content.str());
  const float degamma[]={.5,.5,.5,1},pq[]={.8,.8,.8,1};
  degammaTexture=texture(1,1,degamma);pqTexture=texture(1,1,pq);
  // Dyadic PQ inputs isolate range/alpha from the existing mediump GUI rounding.
  gui[4]=.75;gui[5]=.25;gui[6]=.125;gui[7]=1;
  gui[8]=0;gui[9]=0;gui[10]=0;gui[11]=.5;
  gui[12]=1;gui[13]=.3;gui[14]=.6;gui[15]=0; // RGB garbage with zero coverage.
  gui[(width+4)*4]=.25;gui[(width+4)*4+1]=.125;gui[(width+4)*4+2]=.375;gui[(width+4)*4+3]=.5;
  guiTexture=texture(width,height,gui.data());
  auto targetTexture=texture(width,height,film.data());finalFramebuffer=framebuffer(targetTexture);
  auto pqTargetTexture=texture(width,height,film.data());pqFramebuffer=framebuffer(pqTargetTexture);
  unsigned failures=0;
  for(unsigned bits:{10u,12u})for(bool limited:{false,true})for(bool inputPQ:{false,true})for(bool direct:{false,true}){
    const unsigned maximum=(1u<<bits)-1,span=direct&&limited?219u<<(bits-8):maximum,offset=direct&&limited?16u<<(bits-8):0;
    for(unsigned i=0;i<width*height;i++)for(unsigned c=0;c<4;c++)
      film[i*4+c]=c==3?1:float(offset+span*(c+1)/4)/maximum;
    glBindTexture(GL_TEXTURE_2D,direct?targetTexture:pqTargetTexture);
    glTexSubImage2D(GL_TEXTURE_2D,0,0,0,width,height,GL_RGBA,GL_FLOAT,film.data());
    glBindFramebuffer(GL_FRAMEBUFFER,pqFramebuffer);glViewport(0,0,width,height);
    CWinSystemGbmGLESContext window;window.limited=limited;window.m_dvBridge->m_outputBits=bits;
    window.m_dvBridge->m_direct=direct;
    if(inputPQ)window.m_dvPQSubtitleDraws=2,window.m_dvPQGuiComposed=true;
    window.CompositeGui();
    if(!window.m_dvFrame || window.m_dvBridge->pqQueries!=(direct?0u:1u)){
      std::cerr<<"direct HDR GUI requested a PQ intermediate\n";++failures;
    }
    GLint restored;glGetIntegerv(GL_FRAMEBUFFER_BINDING,&restored);assert(GLuint(restored)==pqFramebuffer);
    glBindFramebuffer(GL_FRAMEBUFFER,direct?finalFramebuffer:pqFramebuffer);std::array<float,width*height*4> actual{};
    glReadPixels(0,0,width,height,GL_RGBA,GL_FLOAT,actual.data());
    if(direct&&!window.m_dvBridge->m_guiComposed){std::cerr<<"GUI composition did not invalidate equal-PTS film reuse\n";++failures;}
    // A delayed handoff preserves this finished GUI; it must not blend twice.
    if(direct){
      window.CompositeGui();std::array<float,width*height*4> repeated{};
      glReadPixels(0,0,width,height,GL_RGBA,GL_FLOAT,repeated.data());
      if(std::memcmp(actual.data(),repeated.data(),sizeof(actual))){std::cerr<<"pending GUI alpha compounded\n";++failures;}
    }
    for(unsigned i=0;i<width*height;i++)for(unsigned c=0;c<3;c++){
      const unsigned sourceIndex=direct?i:(height-1-i/width)*width+i%width;
      const float alpha=gui[sourceIndex*4+3];
      if(alpha==0){assert(!std::memcmp(&actual[i*4+c],&film[i*4+c],sizeof(float)));continue;}
      const double source=inputPQ?gui[sourceIndex*4+c]:.8*alpha;
      const double expected=(source*span+alpha*offset)/maximum+film[i*4+c]*(1-alpha);
      if(std::abs(actual[i*4+c]-expected)*maximum>1.01){
        std::cerr<<"HDR GUI range/blend/orientation mismatch bits="<<bits<<" limited="<<limited
                 <<" pq="<<inputPQ<<" pixel="<<i<<" got="<<actual[i*4+c]<<" want="<<expected<<'\n';++failures;
      }
    }
    assert(window.m_compositeShader->m_outputScale==1 && window.m_compositeShader->m_outputOffset==0);
    // The GUI FBO is unchanged, but the following movie picture must be fresh.
    for(unsigned i=0;i<width*height;i++)for(unsigned c=0;c<3;c++)film[i*4+c]*=.5f;
    glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,direct?targetTexture:pqTargetTexture);
    glTexSubImage2D(GL_TEXTURE_2D,0,0,0,width,height,GL_RGBA,GL_FLOAT,film.data());
    window.m_guiWillRender=false;window.m_dvNativeGui=false;
    window.CompositeGui();glReadPixels(0,0,width,height,GL_RGBA,GL_FLOAT,actual.data());
    for(unsigned i=0;i<width*height;i++)for(unsigned c=0;c<3;c++){
      const unsigned j=direct?i:(height-1-i/width)*width+i%width;const float alpha=gui[j*4+3];
      if(alpha==0){assert(!std::memcmp(&actual[i*4+c],&film[i*4+c],sizeof(float)));continue;}
      const double source=inputPQ?gui[j*4+c]:.8*alpha;
      const double expected=(source*span+alpha*offset)/maximum+film[i*4+c]*(1-alpha);
      assert(std::abs(actual[i*4+c]-expected)*maximum<=1.01);
    }
  }
  // Execute the production compute compose function with transfer-fetch counters.
  std::string compose=dve_shader;
  compose=compose.substr(compose.find("vec3 compose"),compose.find("void pack_pair")-compose.find("vec3 compose"));
  for(const auto& item:{std::pair{"texture(gui_degamma,","counted_degamma("},
                       std::pair{"texture(gui_pq,","counted_pq("}}){
    size_t at=0;while((at=compose.find(item.first,at))!=std::string::npos){compose.replace(at,std::strlen(item.first),item.second);at+=std::strlen(item.second);}
  }
  const std::string instrumented="#version 300 es\nprecision highp float;uniform sampler2D gui,gui_degamma,gui_pq;"
      "uniform vec4 gui_rect;uniform bool gui_visible,gui_is_pq;out vec4 result;int transfers;"
      "vec4 counted_degamma(vec2 p){++transfers;return texture(gui_degamma,p);}"
      "vec4 counted_pq(vec2 p){++transfers;return texture(gui_pq,p);}"+compose+
      "void main(){transfers=0;vec3 q=compose(vec3(.2,.4,.6),vec2(gl_FragCoord.x*480.,2160.-gl_FragCoord.y*1080.));"
      "result=vec4(q,float(transfers));}";
  GLuint computeCompose=program(instrumented,true);glUseProgram(computeCompose);
  glUniform1i(glGetUniformLocation(computeCompose,"gui"),0);
  glUniform1i(glGetUniformLocation(computeCompose,"gui_degamma"),1);
  glUniform1i(glGetUniformLocation(computeCompose,"gui_pq"),2);
  glUniform1i(glGetUniformLocation(computeCompose,"gui_visible"),1);
  glUniform4f(glGetUniformLocation(computeCompose,"gui_rect"),0,0,3840,2160);
  glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,guiTexture);
  glActiveTexture(GL_TEXTURE1);glBindTexture(GL_TEXTURE_2D,degammaTexture);
  glActiveTexture(GL_TEXTURE2);glBindTexture(GL_TEXTURE_2D,pqTexture);
  glBindFramebuffer(GL_FRAMEBUFFER,finalFramebuffer);glViewport(0,0,width,height);glDisable(GL_BLEND);
  const float vertices[]={-1,-1,1,-1,-1,1,1,1};GLint pos=glGetAttribLocation(computeCompose,"a_pos");
  glVertexAttribPointer(pos,2,GL_FLOAT,GL_FALSE,0,vertices);glEnableVertexAttribArray(pos);
  glDrawArrays(GL_TRIANGLE_STRIP,0,4);std::array<float,width*height*4> actual{};
  glReadPixels(0,0,width,height,GL_RGBA,GL_FLOAT,actual.data());
  for(unsigned i=0;i<width*height;i++)if(gui[i*4+3]==0){
    if(actual[i*4+3]!=0){std::cerr<<"transparent compute GUI performed "<<actual[i*4+3]<<" transfer fetches\n";++failures;}
    for(unsigned c=0;c<3;c++)assert(actual[i*4+c]==float((c+1)*.2));
  }
  assert(glGetError()==GL_NO_ERROR);
  if(failures)return 1;
  std::cout<<"PASS actual HDR GUI shader: direct target, 10/12-bit full/limited, SDR/PQ alpha, orientation, exact uncovered film; compute alpha0 performs no transfers\n";
}
