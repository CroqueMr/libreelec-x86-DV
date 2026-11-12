"""Check the GLES copy used by the Pascal HDR10 scanout."""
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

from shipped_kodi import shipped_code


class PascalHDR10Scanout(unittest.TestCase):
    def test_gpu_flip_keeps_ten_bit_codes(self):
        source = shipped_code("xbmc/windowing/gbm/PascalHDR10Scanout.cpp")
        method = re.search(r"bool FlipHDR10Frame\(.*?^}", source, re.S | re.M)
        self.assertIsNotNone(method, "Pascal scanout has no GLES flip")
        bindings = re.search(r"struct FramebufferBindings\n\{.*?^};", source, re.S | re.M)
        self.assertIsNotNone(bindings, "GLES blit must restore the framebuffer bindings")
        program = r'''
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <cassert>

METHOD

int main()
{
  const EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
  assert(eglInitialize(display, nullptr, nullptr));
  assert(eglBindAPI(EGL_OPENGL_ES_API));
  const EGLint attributes[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT,
                              EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_NONE};
  EGLConfig config;
  EGLint count;
  assert(eglChooseConfig(display, attributes, &config, 1, &count) && count);
  const EGLint contextAttributes[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
  const auto context = eglCreateContext(display, config, EGL_NO_CONTEXT, contextAttributes);
  const EGLint pbufferAttributes[] = {EGL_WIDTH, 2, EGL_HEIGHT, 2, EGL_NONE};
  const auto surface = eglCreatePbufferSurface(display, config, pbufferAttributes);
  assert(eglMakeCurrent(display, surface, surface, context));

  GLuint fb[2], textures[2];
  glGenFramebuffers(2, fb);
  glGenTextures(2, textures);
  for (int i = 0; i < 2; ++i)
  {
    glBindTexture(GL_TEXTURE_2D, textures[i]);
    glTexStorage2D(GL_TEXTURE_2D, 1, GL_RGB10_A2, 2, 2);
    glBindFramebuffer(GL_FRAMEBUFFER, fb[i]);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, textures[i], 0);
    assert(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
  }
  glBindFramebuffer(GL_FRAMEBUFFER, fb[0]);
  glClearColor(0, 0, 0, 1);
  glClear(GL_COLOR_BUFFER_BIT);
  glEnable(GL_SCISSOR_TEST);
  glScissor(0, 0, 2, 1);
  glClearColor(65.f / 1023, 513.f / 1023, 937.f / 1023, 1);
  glClear(GL_COLOR_BUFFER_BIT);
  assert(FlipHDR10Frame(fb[0], fb[1], 2, 2));
  assert(glIsEnabled(GL_SCISSOR_TEST));
  GLint bound;
  glGetIntegerv(GL_DRAW_FRAMEBUFFER_BINDING, &bound);
  assert(static_cast<GLuint>(bound) == fb[0]);
  glBindFramebuffer(GL_READ_FRAMEBUFFER, fb[1]);
  GLuint pixels[2];
  glReadPixels(0, 0, 1, 2, GL_RGBA, GL_UNSIGNED_INT_2_10_10_10_REV, pixels);
  assert(glGetError() == GL_NO_ERROR);
  assert((pixels[0] & 0x3fffffff) == 0);
  assert(pixels[1] == (65u | (513u << 10) | (937u << 20) | (3u << 30)));
  eglTerminate(display);
}
'''.replace("METHOD", bindings.group() + "\n" + method.group())
        with tempfile.TemporaryDirectory() as tmp:
            code = Path(tmp) / "flip.cpp"
            binary = Path(tmp) / "flip"
            code.write_text(program)
            subprocess.run(["c++", "-std=c++17", str(code), "-o", str(binary),
                            "-lEGL", "-lGLESv2"], check=True)
            subprocess.run(["env", "EGL_PLATFORM=surfaceless", "LIBGL_ALWAYS_SOFTWARE=1",
                            str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
