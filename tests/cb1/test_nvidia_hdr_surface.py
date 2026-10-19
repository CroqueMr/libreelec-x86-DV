"""Execute EGL format choice without a GPU; rejected deep formats stay rejected."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code


class NvidiaHDRSurface(unittest.TestCase):
    def test_float_requires_nvidia_capability_and_never_admits_eight_bit(self):
        path='xbmc/windowing/gbm/WinSystemGbmEGLContext.cpp'
        override=os.environ.get('CB1_DRM_STATE_SOURCE')
        source=(Path(override)/path).read_text() if override else shipped_code(path)
        method=re.search(r'bool CWinSystemGbmEGLContext::ChooseEGLConfig.*?^}',source,re.S|re.M).group()
        program=r'''
#include <algorithm>
#include <cassert>
#include <functional>
#include <vector>
#include <iterator>
using EGLint=int;
constexpr unsigned DRM_FORMAT_ABGR16161616F=4;
struct outputformat {unsigned drm; int bpp,alpha; bool active;};
struct DRM {
  std::vector<outputformat> formats={{1,8,8,true},{2,10,2,true},{4,16,16,true}};
  auto GetOutputFormats() {return formats;}
};
struct EGL {
  unsigned accepted=4, selected=0;
  bool ChooseConfig(int,unsigned format,bool,int,bool=false) {
    if(format!=accepted) return false;
    selected=format; return true;
  }
};
struct CWinSystemGbmEGLContext {
  DRM drm; DRM* m_DRM=&drm; EGL m_eglContext; bool nvidia=false;
  bool m_floatOutputBlocked=false;
  bool FloatOutputUsable() const {return nvidia;}
  bool ChooseEGLConfig(EGLint,int);
};
METHOD
int main() {
  CWinSystemGbmEGLContext window;
  assert(!window.ChooseEGLConfig(1,10));
  window.nvidia=true;
  assert(window.ChooseEGLConfig(1,10));
  assert(window.m_eglContext.selected==4);
  window.m_eglContext.accepted=1;
  assert(!window.ChooseEGLConfig(1,10));
  assert(window.ChooseEGLConfig(1,8));
  assert(window.m_eglContext.selected==1);
  window.nvidia=false; window.m_eglContext.accepted=2;
  assert(window.ChooseEGLConfig(1,10));
  assert(window.m_eglContext.selected==2);
}
'''.replace('METHOD',method)
        with tempfile.TemporaryDirectory() as directory:
            code=Path(directory)/'check.cpp'; code.write_text(program)
            binary=Path(directory)/'check'
            result=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_refused_float_output_restores_ordinary_surface_and_signal(self):
        path='xbmc/windowing/gbm/WinSystemGbmEGLContext.cpp'
        override=os.environ.get('CB1_DRM_STATE_SOURCE')
        source=(Path(override)/path).read_text() if override else shipped_code(path)
        found=re.search(r'void CWinSystemGbmEGLContext::CheckFloatOutput.*?^}',source,re.S|re.M)
        self.assertIsNotNone(found, 'float rejection recovery is missing')
        program=r'''
#include <cassert>
#include <memory>
struct VideoPicture {};
struct CWinSystemGbmEGLContext {
  bool m_floatOutputBlocked=false, floating=true, restore=true;
  unsigned rebuilds=0,requeues=0;
  std::unique_ptr<VideoPicture> m_floatOutputPicture=std::make_unique<VideoPicture>();
  bool HasFloatOutput() const {return floating;}
  bool SetVideoOutput(VideoPicture*) {++rebuilds; if(restore) floating=false; return restore;}
  bool RequeueOutputProperties() {++requeues;return true;}
  void CheckFloatOutput(bool);
};
METHOD
int main() {
  CWinSystemGbmEGLContext window;
  window.CheckFloatOutput(true); assert(!window.m_floatOutputBlocked && !window.rebuilds);
  window.CheckFloatOutput(false);
  assert(window.m_floatOutputBlocked && window.rebuilds==1 && window.requeues==1);
  window.CheckFloatOutput(false); assert(window.rebuilds==1);
  window.floating=true;window.restore=false;window.CheckFloatOutput(false);
  assert(window.rebuilds==2 && window.requeues==1);
}
'''.replace('METHOD',found.group())
        with tempfile.TemporaryDirectory() as directory:
            code=Path(directory)/'check.cpp';code.write_text(program)
            binary=Path(directory)/'check'
            result=subprocess.run(['c++','-std=c++20',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
