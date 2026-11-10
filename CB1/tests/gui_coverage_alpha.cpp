/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Appended to gui_final_hdr10.cpp's EGL/actual CompositeGui fixture. */
#include <algorithm>
#include <vector>
#ifdef CB1_TEST_DISABLE_DV
#undef HAVE_DVBRIDGE
#endif
namespace Drawing {
struct CWinSystemBase {
  bool m_guiCompositing=true;
  virtual bool IsHdrComposite()const{return m_guiCompositing;}
  virtual bool UseGuiCoverageAlpha()const @@NATIVE_POLICY@@
};
struct Window:CWinSystemBase {
  bool m_cb1RestoringPreferences=false,m_dvOrdinaryFrame=false,m_hdrConversion=false;
  void* m_dvContext=nullptr;
  struct{bool captured=false;bool Captured()const{return captured;}}m_dvState;
  bool UseGuiCoverageAlpha()const override @@CB1_POLICY@@
} window;
enum class ShaderMethodGLES {SM_FONTS,SM_FONTS_SHADER_CLIP,SM_MULTI_111R_111R_BLENDCOLOR,
  SM_MULTI_RGBA_111R_BLENDCOLOR,SM_MULTI_RGBA_111R,SM_MULTI_BLENDCOLOR,SM_MULTI,
  SM_TEXTURE_111R,SM_TEXTURE,SM_TEXTURE_NOBLEND};
GLuint fontProgram,textureProgram,inputTexture;
struct RenderBase{virtual ~RenderBase()=default;};
struct CRenderSystemGLES:RenderBase {
  bool ScissorsCanEffectClipping(){return true;} void ResetScissors(){}
  void EnableGUIShader(ShaderMethodGLES method){
    GLuint p=method==ShaderMethodGLES::SM_FONTS?fontProgram:textureProgram;
    glUseProgram(p);glUniform1i(glGetUniformLocation(p,"m_samp0"),0);
    glUniform4f(glGetUniformLocation(p,"test_colour"),.8,.8,.8,1);
    glUniform4f(glGetUniformLocation(p,"m_unicol"),.8,.8,.8,1);
  }
} render;
struct Texture {
  void LoadToGPU(){} bool HasAlpha()const{return true;}
  int GetSwizzle()const{return 0;} void BindToUnit(unsigned u){glActiveTexture(GL_TEXTURE0+u);glBindTexture(GL_TEXTURE_2D,inputTexture);}
  int GetWidth()const{return 1;} int GetHeight()const{return 1;} int GetPitch()const{return 4;}
  const unsigned char* GetPixels()const{return nullptr;}
};
using CTexture=Texture;
struct CServiceBroker {
  static RenderBase* GetRenderSystem(){return &render;}static Window* GetWinSystem(){return &window;}
  struct GUI{GUI& GetTextureManager(){return *this;}void ReleaseHwTexture(unsigned){}};
  static GUI* GetGUI(){static GUI g;return &g;}
};
void VerifyGLState(){assert(glGetError()==GL_NO_ERROR);}
enum {TEXTURE_REALLOCATED,TEXTURE_VOID,TEXTURE_UPDATED,TEXTURE_READY,KD_TEX_SWIZ_111R};
struct CGUIFontTTFGLES {
  bool m_scissorClip=false;int m_textureStatus=TEXTURE_READY,m_updateY1=0,m_updateY2=0;
  GLuint m_nTexture=inputTexture;Texture storage;Texture* m_texture=&storage;
  bool FirstBegin() @@FONT_BEGIN@@
};
namespace KODI::UTILS {
namespace COLOR {using Color=uint32_t;}
namespace GL {enum class ColorChannel{R,G,B,A};
unsigned char GetChannelFromARGB(ColorChannel c,COLOR::Color value){
  return value >> (c==ColorChannel::R?16:c==ColorChannel::G?8:c==ColorChannel::B?0:24);
}}
}
struct Textures {
  std::vector<std::shared_ptr<Texture>> m_textures;
  size_t size()const{return m_textures.size();}
};
struct CGUITextureGLES {
  Textures m_texture{{std::make_shared<Texture>()}},m_diffuse;
  unsigned m_currentFrame=0;unsigned char m_col[4]{};bool m_isGLES20=false;
  CRenderSystemGLES* m_renderSystem=&render;std::vector<int> m_packedVertices;
  void Begin(KODI::UTILS::COLOR::Color color) @@TEXTURE_BEGIN@@
};
GLuint guiProgram(const std::string& fragment){
  const char* vertex="attribute vec2 a_pos;varying vec4 m_cord0;varying lowp vec4 m_colour;uniform vec4 test_colour;"
    "void main(){gl_Position=vec4(a_pos,0,1);m_cord0=vec4(.5,.5,0,1);m_colour=test_colour;}";
  GLuint p=glCreateProgram();glAttachShader(p,shader(GL_VERTEX_SHADER,vertex));
  glAttachShader(p,shader(GL_FRAGMENT_SHADER,fragment));glLinkProgram(p);
  GLint linked;glGetProgramiv(p,GL_LINK_STATUS,&linked);assert(linked);return p;
}
std::string read(const std::string& path){std::ifstream f(path);std::stringstream s;s<<f.rdbuf();assert(f);return s.str();}
void draw(int x,bool font,float alpha){
  glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,inputTexture);
  const float pixel[]={1,1,1,alpha};glTexSubImage2D(GL_TEXTURE_2D,0,0,0,1,1,GL_RGBA,GL_FLOAT,pixel);
  if(font){CGUIFontTTFGLES glyph;assert(glyph.FirstBegin());}
  else {CGUITextureGLES image;image.Begin(0xffcccccc);}
  glViewport(x,0,1,1);const float vertices[]={-1,-1,1,-1,-1,1,1,1};
  const GLuint p=font?fontProgram:textureProgram;const GLint pos=glGetAttribLocation(p,"a_pos");
  glVertexAttribPointer(pos,2,GL_FLOAT,GL_FALSE,0,vertices);glEnableVertexAttribArray(pos);
  glDrawArrays(GL_TRIANGLE_STRIP,0,4);glDisableVertexAttribArray(pos);
}
}
int main(int argc,char**argv){
  // Sampled existing cb1-glass.png edge, between its alpha0 corner and alpha255 interior.
  constexpr float roundedEdge=131.f/255;
  assert(argc==2);EGLDisplay display=eglGetDisplay(EGL_DEFAULT_DISPLAY);assert(eglInitialize(display,nullptr,nullptr));
  assert(eglBindAPI(EGL_OPENGL_ES_API));
  EGLint attr[]={EGL_SURFACE_TYPE,EGL_PBUFFER_BIT,EGL_RENDERABLE_TYPE,EGL_OPENGL_ES3_BIT,EGL_NONE};
  EGLConfig config;EGLint count;assert(eglChooseConfig(display,attr,&config,1,&count)&&count);
  EGLint size[]={EGL_WIDTH,width,EGL_HEIGHT,height,EGL_NONE},version[]={EGL_CONTEXT_CLIENT_VERSION,3,EGL_NONE};
  EGLSurface surface=eglCreatePbufferSurface(display,config,size);EGLContext context=eglCreateContext(display,config,EGL_NO_CONTEXT,version);
  assert(eglMakeCurrent(display,surface,surface,context));
  std::string shaders=argv[1];nativeProgram=program(Drawing::read(shaders+"/gles_gui_composite.frag"));
  Drawing::fontProgram=Drawing::guiProgram(Drawing::read(shaders+"/gles_shader_fonts.frag"));
  Drawing::textureProgram=Drawing::guiProgram(Drawing::read(shaders+"/gles_shader_texture.frag"));
  const float lut[]={.8,.8,.8,1},input[]={1,1,1,.5};
  degammaTexture=texture(1,1,lut);pqTexture=texture(1,1,lut);Drawing::inputTexture=texture(1,1,input);
  GLuint target=texture(width,height,film.data());finalFramebuffer=framebuffer(target);
  unsigned failures=0;
  auto check=[&](bool pass,const char* reason){if(!pass){std::cerr<<reason<<'\n';++failures;}};
  for(GLint format:{GL_RGBA32F,GL_RGBA8})for(bool font:{true,false})for(int mode=0;mode<8;mode++){
    auto&w=Drawing::window;w.m_guiCompositing=mode!=4;w.m_dvState.captured=mode==1||mode==6||mode==7;
    w.m_hdrConversion=mode==2||mode==3;w.m_dvContext=mode==5?&w:nullptr;
    w.m_cb1RestoringPreferences=mode==6;w.m_dvOrdinaryFrame=mode==7;
    bool coverage=mode==1||mode==2||mode==3||mode==4;
#ifdef CB1_TEST_DISABLE_DV
    coverage=mode==4;
#endif
    if(format==GL_RGBA8){
      glGenTextures(1,&guiTexture);glBindTexture(GL_TEXTURE_2D,guiTexture);
      glTexImage2D(GL_TEXTURE_2D,0,format,width,height,0,GL_RGBA,GL_UNSIGNED_BYTE,nullptr);
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MIN_FILTER,GL_NEAREST);
      glTexParameteri(GL_TEXTURE_2D,GL_TEXTURE_MAG_FILTER,GL_NEAREST);
    }else guiTexture=texture(width,height,gui.data(),format);
    const GLuint guiFbo=framebuffer(guiTexture);
    auto readGUI=[&](std::array<float,width*height*4>& pixels){
      if(format==GL_RGBA8){
        std::array<unsigned char,width*height*4> bytes{};
        glReadPixels(0,0,width,height,GL_RGBA,GL_UNSIGNED_BYTE,bytes.data());
        for(unsigned i=0;i<bytes.size();i++)pixels[i]=bytes[i]/255.f;
      }else glReadPixels(0,0,width,height,GL_RGBA,GL_FLOAT,pixels.data());
    };
    auto redraw=[&]{
      glBindFramebuffer(GL_FRAMEBUFFER,guiFbo);glViewport(0,0,width,height);glDisable(GL_SCISSOR_TEST);
      glClearColor(0,0,0,0);glClear(GL_COLOR_BUFFER_BIT);
      glEnable(GL_SCISSOR_TEST);glScissor(0,0,1,1);glClearColor(.1,.2,.3,1);glClear(GL_COLOR_BUFFER_BIT);
      glScissor(4,0,1,1);glClear(GL_COLOR_BUFFER_BIT);glDisable(GL_SCISSOR_TEST);
      Drawing::draw(0,font,.5);Drawing::draw(1,font,.5);
      Drawing::draw(3,false,roundedEdge);Drawing::draw(4,font,.5);Drawing::draw(4,font,.5);
    };
    redraw();std::array<float,width*height*4> pixels{};
    readGUI(pixels);
    const float tolerance=format==GL_RGBA8?1.1f/255:1e-5f;
    check(std::abs(pixels[3]-(coverage?1.f:.75f))<=tolerance,"AA drawing changed opaque panel alpha");
    check(std::abs(pixels[7]-(coverage?.5f:.25f))<=tolerance,"standalone AA coverage is wrong");
    check(pixels[11]==0,"uncovered outside gained opacity");
    const float edge=roundedEdge;
    // The shipped mediump shader rounds a non-dyadic asset-edge sample.
    const float shaderTolerance=std::max(tolerance,1.f/2048);
    check(std::abs(pixels[15]-(coverage?edge:edge*edge))<=shaderTolerance,"rounded edge lost its partial coverage");
    check(std::abs(pixels[19]-(coverage?1.f:.625f))<=tolerance,"repeated AA drawing punched panel opacity");
    for(unsigned c=0;c<3;c++)check(std::abs(pixels[c]-(.4f+.5f*(c+1)*.1f))<=shaderTolerance,"source RGB accumulation changed");
    std::array<float,2> final{};
    for(unsigned frame=0;frame<2;frame++){
      for(unsigned i=0;i<width*height;i++)for(unsigned c=0;c<4;c++)film[i*4+c]=c==3?1:frame?.8f:.2f;
      glActiveTexture(GL_TEXTURE0);glBindTexture(GL_TEXTURE_2D,target);
      glTexSubImage2D(GL_TEXTURE_2D,0,0,0,width,height,GL_RGBA,GL_FLOAT,film.data());
      CWinSystemGbmGLESContext composite;composite.m_guiWillRender=frame==0;composite.CompositeGui();
      glBindFramebuffer(GL_FRAMEBUFFER,finalFramebuffer);std::array<float,width*height*4> result{};
      glReadPixels(0,0,width,height,GL_RGBA,GL_FLOAT,result.data());final[frame]=result[0];
      check(result[8]==film[8],"transparent outside changed the movie");
    }
    const float leak=std::abs(final[1]-final[0]);
    check(std::abs(leak-(coverage?0.f:.15f))<=2*tolerance,"cached opaque panel reveals changed film");
    glBindFramebuffer(GL_FRAMEBUFFER,guiFbo);std::array<float,width*height*4> cached{};
    readGUI(cached);
    check(pixels==cached,"final composition changed cached GUI pixels");redraw();
    readGUI(cached);check(pixels==cached,"redraw changed GUI coverage");
    std::cout<<(font?"font":"texture")<<" format="<<(format==GL_RGBA8?8:32)<<" mode="<<mode
      <<" panel="<<pixels[3]<<" glyph="<<pixels[7]<<" outside="<<pixels[11]<<" edge="<<pixels[15]
      <<" cached_film_delta="<<leak<<std::endl;
    glDeleteFramebuffers(1,&guiFbo);glDeleteTextures(1,&guiTexture);
  }
  assert(glGetError()==GL_NO_ERROR);return failures?1:0;
}
