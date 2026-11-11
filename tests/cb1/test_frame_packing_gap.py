"""Verify the native GBM pre-swap clear on a real GLES backbuffer."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get("KODI_NATIVE_SOURCE_TREE"), "Requires patched Kodi sources")
class FramePackingGap(unittest.TestCase):
    def test_clears_only_active_space_before_swapping(self):
        tree = Path(os.environ["KODI_NATIVE_SOURCE_TREE"])
        source = (tree / "xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp").read_text()
        ordinary = source.split("if (rendered || videoLayer)", 1)[1]
        pre_fence = ordinary.split("if (rendered)", 1)[1].split(
            "#if defined(EGL_ANDROID_native_fence_sync)", 1)[0]
        program = r'''
#include <cassert>
#include <EGL/egl.h>
#include <GLES2/gl2.h>

enum class RenderStereoMode { OFF, SPLIT_HORIZONTAL };
struct Context {
  RenderStereoMode stereo = RenderStereoMode::SPLIT_HORIZONTAL;
  auto GetStereoMode() const { return stereo; }
};
struct Display {
  struct Mode { int iScreenHeight = 2205, iBlanking = 45; } mode;
  auto GetCurrentMode() const { return mode; }
};
struct Window {
  Context context;
  Display display;
  Display* m_DRM = &display;
  int m_nWidth = 8, m_nHeight = 2205;
  auto& GetGfxContext() { return context; }
  void BeforeFence() PRE_FENCE }
};

void paint(int y, int h, float r, float g, float b) {
  glScissor(0, y, 8, h);
  glClearColor(r, g, b, 1);
  glClear(GL_COLOR_BUFFER_BIT);
}

void expect(int x, int y, int r, int g, int b) {
  unsigned char pixel[4]{};
  glReadPixels(x, y, 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel);
  assert(pixel[0] == r && pixel[1] == g && pixel[2] == b && pixel[3] == 255);
}

int main() {
  EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
  assert(eglInitialize(display, nullptr, nullptr) && eglBindAPI(EGL_OPENGL_ES_API));
  const EGLint attrs[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE,
                          EGL_OPENGL_ES2_BIT, EGL_RED_SIZE, 8, EGL_GREEN_SIZE, 8,
                          EGL_BLUE_SIZE, 8, EGL_ALPHA_SIZE, 8, EGL_NONE};
  EGLConfig config{};
  EGLint count{};
  assert(eglChooseConfig(display, attrs, &config, 1, &count) && count == 1);
  const EGLint size[] = {EGL_WIDTH, 8, EGL_HEIGHT, 2205, EGL_NONE};
  EGLSurface surface = eglCreatePbufferSurface(display, config, size);
  const EGLint client[] = {EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE};
  EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, client);
  assert(eglMakeCurrent(display, surface, surface, context));

  Window window;
  for (int seed = 0; seed < 2; ++seed) {
    glEnable(GL_SCISSOR_TEST);
    paint(0, 2205, seed, 1, 0);
    paint(0, 1080, 0, 0, 1);
    paint(1125, 1080, 1, 0, 0);
    if (seed)
      glDisable(GL_SCISSOR_TEST);
    window.BeforeFence();
    for (int y = 1080; y < 1125; ++y) {
      expect(0, y, 0, 0, 0);
      expect(7, y, 0, 0, 0);
    }
    expect(4, 1079, 0, 0, 255);
    expect(4, 1125, 255, 0, 0);
    GLint scissors[4]{};
    GLfloat color[4]{};
    glGetIntegerv(GL_SCISSOR_BOX, scissors);
    glGetFloatv(GL_COLOR_CLEAR_VALUE, color);
    assert(scissors[1] == 1125 && scissors[3] == 1080);
    assert(color[0] == 1 && color[1] == 0 && color[2] == 0 && color[3] == 1);
    assert(glIsEnabled(GL_SCISSOR_TEST) == !seed);
  }
  glEnable(GL_SCISSOR_TEST);
  paint(1080, 45, 0, 1, 0);
  window.display.mode.iBlanking = 0;
  window.BeforeFence();
  expect(4, 1100, 0, 255, 0);
  window.display.mode.iBlanking = 45;
  window.context.stereo = RenderStereoMode::OFF;
  window.BeforeFence();
  expect(4, 1100, 0, 255, 0);
  assert(glGetError() == GL_NO_ERROR);
  assert(eglMakeCurrent(display, EGL_NO_SURFACE, EGL_NO_SURFACE, EGL_NO_CONTEXT));
  eglDestroyContext(display, context);
  eglDestroySurface(display, surface);
  eglTerminate(display);
}
'''.replace("PRE_FENCE", pre_fence)
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "check")
            build = subprocess.run(
                ["c++", "-std=c++20", "-x", "c++", "-", "-lEGL", "-lGLESv2", "-o", binary],
                input=program, text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run(
                [binary], env=dict(os.environ, EGL_PLATFORM="surfaceless", LIBGL_ALWAYS_SOFTWARE="1"),
                text=True, capture_output=True,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
