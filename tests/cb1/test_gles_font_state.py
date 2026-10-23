"""Cached scrolling glyph batches cannot consume the caller's camera stack."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import body


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi tree')
class FontState(unittest.TestCase):
    def test_scrolling_batches_preserve_saved_camera_and_current_scissor(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree / 'xbmc/guilib/GUIFontTTFGLES.cpp').read_text()
        draw = body(source, 'void CGUIFontTTFGLES::LastEnd()')
        header = (tree / 'xbmc/rendering/MatrixGL.h').read_text()
        stack = header[header.index('class CMatrixGLStack'):header.index('extern CMatrixGLStack')]
        program = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <iostream>
#include <stack>
#include <vector>
using GLint=int; using GLfloat=float; using GLvoid=void;
enum {GL_ARRAY_BUFFER,GL_ELEMENT_ARRAY_BUFFER,GL_FLOAT,GL_UNSIGNED_BYTE,GL_UNSIGNED_SHORT,
      GL_FALSE,GL_TRUE,GL_TRIANGLES};
constexpr size_t ELEMENT_ARRAY_MAX_CHAR_INDEX=1000;
struct CRect {
  float x1=0,y1=0,x2=3840,y2=2160;
  bool IsEmpty() const {return x2<=x1 || y2<=y1;}
  void Intersect(const CRect& b) {x1=std::max(x1,b.x1);y1=std::max(y1,b.y1);
    x2=std::min(x2,b.x2);y2=std::min(y2,b.y2);}
};
struct TransformMatrix {};
struct CMatrixGL {
  int camera=0;
  CMatrixGL()=default; explicit CMatrixGL(TransformMatrix) {}
  void MultMatrixf(const CMatrixGL&) {}
  void Translatef(float,float,float) {} void Scalef(float,float,float) {}
};
@@STACK@@
void CMatrixGLStack::Load() {}
CMatrixGLStack glMatrixProject,glMatrixModview;
struct CGraphicContext {
  CRect scissors;
  CRect StereoCorrection(CRect r) {return r;}
  CRect GetScissors() {return scissors;}
  float GetGUIScaleX(){return 1;} float GetGUIScaleY(){return 1;}
  TransformMatrix GetGUIMatrix(){return {};}
  float ScaleFinalXCoord(float x,float){return x;}
  float ScaleFinalYCoord(float,float y){return y;}
  float GetTransformDepth(){return 0;}
};
struct RenderBase {virtual ~RenderBase()=default;};
struct CRenderSystemGLES:RenderBase {
  CRect scissor;
  int GUIShaderGetPos(){return 0;} int GUIShaderGetCol(){return 1;}
  int GUIShaderGetCoord0(){return 2;} int GUIShaderGetClip(){return 3;}
  int GUIShaderGetCoordStep(){return 4;} int GUIShaderGetMatrix(){return 5;}
  int GUIShaderGetDepth(){return 6;}
  CRect ClipRectToScissorRect(CRect r){return r;}
  void SetScissors(CRect r){scissor=r;}
  void ResetScissors(){scissor=CRect{};}
  void DisableGUIShader(){}
} renderer;
struct CWinSystemBase {CGraphicContext context; CGraphicContext& GetGfxContext(){return context;}} window;
struct CServiceBroker {
  static CWinSystemBase* GetWinSystem(){return &window;}
  static RenderBase* GetRenderSystem(){return &renderer;}
};
struct CRenderSystemBase {inline static unsigned m_GUIElementCount=0;};
unsigned draws=0;
void glEnableVertexAttribArray(int){} void glDisableVertexAttribArray(int){}
void glBindBuffer(int,unsigned){} void glUniform4fv(int,int,const float*){}
void glUniformMatrix4fv(int,int,int,const CMatrixGL&){} void glUniform1f(int,float){}
void glVertexAttribPointer(int,int,int,int,size_t,const void*){}
void glDrawElements(int,size_t,int,int){++draws;}
struct Buffer {unsigned bufferHandle=1; size_t size=5;};
struct Translation {Buffer* m_vertexBuffer;CRect m_clip;
  float m_translateX=0,m_translateY=0,m_offsetX=0,m_offsetY=0;};
struct CGUIFontTTFGLES {
  struct SVertex {float x,y,z;unsigned char r,g,b,a;float u,v;};
  std::vector<int> m_vertex;
  std::vector<Translation> m_vertexTrans;
  bool m_scissorClip=true;
  unsigned m_elementArrayHandle=1,m_textureWidth=64,m_textureHeight=64;
  void CreateStaticVertexBuffers(){}
  void LastEnd() @@DRAW@@
};
int main(){
  glMatrixModview.Get().camera=17;glMatrixModview.Push();
  glMatrixModview.Get().camera=23;
  window.context.scissors={0,0,3840,2160};
  Buffer glyphs;CGUIFontTTFGLES font;
  // A scrolling label batches shadow, text and wrapping suffix together.
  for(int i=0;i<4;++i)font.m_vertexTrans.push_back({&glyphs,{2800,40,3700,100}});
  font.LastEnd();
  assert(draws==4);
  assert(glMatrixModview.Get().camera==23 && "font consumed saved caller camera");
  assert(renderer.scissor.x1==0 && renderer.scissor.y2==2160);
  glMatrixModview.Pop();assert(glMatrixModview.Get().camera==17);
  // No caller stack, shader clipping and empty batches remain valid.
  font.m_scissorClip=false;font.LastEnd();assert(draws==8);
  font.m_vertexTrans.clear();font.LastEnd();assert(draws==8);
  std::cout<<"scrolling font preserves caller camera and restores scissors\n";
}
'''.replace('@@STACK@@', stack).replace('@@DRAW@@', draw)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'check.cpp'),
                                    '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
