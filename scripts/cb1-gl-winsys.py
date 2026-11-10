#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Generate WinSystemGbmGLContext.{h,cpp} from the DV-patched WinSystemGbmGLESContext.{h,cpp}.

Usage: scripts/cb1-gl-winsys.py <kodi tree>
The pristine GL and GLES contexts differ only in names, EGL setup and renderer registration, so
the GL one is the GLES one with those swapped. Rerun after each new DV release.
"""
import re, sys

tree = sys.argv[1].rstrip("/")
base = f"{tree}/xbmc/windowing/gbm/"

NAMES = [
    ("WinSystemGbmGLESContext", "WinSystemGbmGLContext"),
    ("rendering/gles/RenderSystemGLES.h", "rendering/gl/RenderSystemGL.h"),
    ("CRenderSystemGLES", "CRenderSystemGL"),
    ("rendering/gles/GuiCompositeShaderGLES.h", "rendering/gl/GuiCompositeShaderGL.h"),
    ("CGuiCompositeShaderGLES", "CGuiCompositeShaderGL"),
    ("rendering/gles/ScreenshotSurfaceGLES.h", "rendering/gl/ScreenshotSurfaceGL.h"),
    ("CScreenshotSurfaceGLES", "CScreenshotSurfaceGL"),
    ("VideoRenderers/LinuxRendererGLES.h", "VideoRenderers/LinuxRendererGL.h"),
    ("CLinuxRendererGLES", "CLinuxRendererGL"),
    ("RPRendererDMAOpenGLES", "RPRendererDMAOpenGL"),
    ("CRendererFactoryDMAOpenGLES", "CRendererFactoryDMAOpenGL"),
    ("RPRendererOpenGLES", "RPRendererOpenGL"),
    ("CRendererFactoryOpenGLES", "CRendererFactoryOpenGL"),
    ("VAAPIRegisterRenderGLES", "VAAPIRegisterRenderGL"),
]

def swap_names(s):
    for a, b in NAMES:
        s = s.replace(a, b)
    return s

def sub_once(s, old, new, what):
    n = s.count(old)
    if n != 1:
        sys.exit(f"{what}: expected 1 match, found {n}")
    return s.replace(old, new)

h = swap_names(open(base + "WinSystemGbmGLESContext.h").read())
cpp = swap_names(open(base + "WinSystemGbmGLESContext.cpp").read())

# DRM PRIME rendering is GLES-only in Kodi; the GL context never registered it.
cpp = re.sub(r'#include "cores/VideoPlayer/VideoRenderers/HwDecRender/RendererDRMPRIMEGLES.h"\n', "", cpp)
cpp = sub_once(cpp, "  CRendererDRMPRIMEGLES::Register();\n  CRendererDRMPRIME::Register();\n  CDVDVideoCodecDRMPRIME::Register();\n",
               "", "DRM PRIME registration")

# EGL: desktop OpenGL instead of OpenGL ES 3 with an ES 2 fallback.
egl = re.search(r"  // GLES 3\.0 required.*?\n  if \(!CWinSystemGbmEGLContext::InitWindowSystemEGL\(EGL_OPENGL_ES3_BIT, EGL_OPENGL_ES_API\)\)\n  \{\n.*?\n  \}\n", cpp, re.S)
if not egl:
    sys.exit("EGL init block not found")
cpp = cpp.replace(egl.group(0),
    "  if (!CWinSystemGbmEGLContext::InitWindowSystemEGL(EGL_OPENGL_BIT, EGL_OPENGL_API))\n  {\n    return false;\n  }\n")
# DV output checks ask for the modern client API: ES 3 on GLES, desktop GL here.
cpp = cpp.replace("EGL_OPENGL_ES3_BIT", "EGL_OPENGL_BIT")
ctx = re.search(r"bool CWinSystemGbmGLContext::CreateContext\(\)\n\{\n.*?\n\}\n", cpp, re.S)
if not ctx:
    sys.exit("CreateContext not found")
cpp = cpp.replace(ctx.group(0), '''bool CWinSystemGbmGLContext::CreateContext()
{
  const EGLint glMajor = 3;
  const EGLint glMinor = 2;

  CEGLAttributesVec contextAttribs;
  contextAttribs.Add(
      {{EGL_CONTEXT_MAJOR_VERSION_KHR, glMajor},
       {EGL_CONTEXT_MINOR_VERSION_KHR, glMinor},
       {EGL_CONTEXT_OPENGL_PROFILE_MASK_KHR, EGL_CONTEXT_OPENGL_CORE_PROFILE_BIT_KHR}});

  if (!m_eglContext.CreateContext(contextAttribs))
  {
    CEGLAttributesVec fallbackContextAttribs;
    fallbackContextAttribs.Add({{EGL_CONTEXT_CLIENT_VERSION, 2}});

    if (!m_eglContext.CreateContext(fallbackContextAttribs))
    {
      CLog::Log(LOGERROR, "EGL context creation failed");
      return false;
    }
    else
    {
      CLog::Log(LOGWARNING,
                "Your OpenGL drivers do not support OpenGL {}.{} core profile. Kodi will run in "
                "compatibility mode, but performance may suffer.",
                glMajor, glMinor);
    }
  }

  return true;
}
''')

if "BindGUIUnitQuad();" in cpp:
    # The GL render system has no shared unit quad, so the context keeps its own for compositing.
    h = sub_once(h, "  std::unique_ptr<CGuiCompositeShaderGL> m_compositeShader;\n",
                 "  std::unique_ptr<CGuiCompositeShaderGL> m_compositeShader;\n"
                 "  KODI::UTILS::GL::CGLBufferObject m_guiUnitQuad{GL_ARRAY_BUFFER};\n"
                 "  void BindGUIUnitQuad();\n", "unit quad member")
    h = sub_once(h, '#include "rendering/gl/RenderSystemGL.h"\n',
                 '#include "rendering/gl/RenderSystemGL.h"\n#include "utils/GLBufferObject.h"\n',
                 "GLBufferObject include")
    cpp = sub_once(cpp, "bool CWinSystemGbmGLContext::CreateContext()\n", """void CWinSystemGbmGLContext::BindGUIUnitQuad()
{
  // Triangle strip order: top left, top right, bottom left, bottom right.
  static constexpr GLfloat unitQuad[4][2] = {
      {0.0f, 0.0f}, {1.0f, 0.0f}, {0.0f, 1.0f}, {1.0f, 1.0f}};
  m_guiUnitQuad.SetDataOnce(unitQuad);
}

bool CWinSystemGbmGLContext::CreateContext()
""", "BindGUIUnitQuad definition")
else:
    # Core profile GL has no client-side arrays: stream the GUI quad through buffers, as
    # Kodi's own GL context did before the static unit quad.
    cpp = sub_once(cpp,
        "  glVertexAttribPointer(posLoc, 2, GL_FLOAT, GL_FALSE, 0, vert);\n"
        "  glVertexAttribPointer(texLoc, 2, GL_FLOAT, GL_FALSE, 0, tex);\n",
        "  GLuint vbo[3];\n"
        "  glGenBuffers(3, vbo);\n"
        "  glBindBuffer(GL_ARRAY_BUFFER, vbo[0]);\n"
        "  glBufferData(GL_ARRAY_BUFFER, sizeof(vert), vert, GL_STREAM_DRAW);\n"
        "  glVertexAttribPointer(posLoc, 2, GL_FLOAT, GL_FALSE, 0, 0);\n"
        "  glBindBuffer(GL_ARRAY_BUFFER, vbo[1]);\n"
        "  glBufferData(GL_ARRAY_BUFFER, sizeof(tex), tex, GL_STREAM_DRAW);\n"
        "  glVertexAttribPointer(texLoc, 2, GL_FLOAT, GL_FALSE, 0, 0);\n"
        "  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, vbo[2]);\n"
        "  glBufferData(GL_ELEMENT_ARRAY_BUFFER, sizeof(idx), idx, GL_STREAM_DRAW);\n",
        "GUI composite client arrays")
    draw = "    glDrawElements(GL_TRIANGLE_STRIP, 4, GL_UNSIGNED_BYTE, idx);\n"
    if cpp.count(draw) != 2:
        sys.exit(f"GUI composite draws: expected 2 matches, found {cpp.count(draw)}")
    cpp = cpp.replace(draw, "    glDrawElements(GL_TRIANGLE_STRIP, 4, GL_UNSIGNED_BYTE, 0);\n")
    cpp = sub_once(cpp,
        "  glDisableVertexAttribArray(posLoc);\n  glDisableVertexAttribArray(texLoc);\n",
        "  glDisableVertexAttribArray(posLoc);\n  glDisableVertexAttribArray(texLoc);\n"
        "  glBindBuffer(GL_ARRAY_BUFFER, 0);\n"
        "  glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);\n"
        "  glDeleteBuffers(3, vbo);\n",
        "GUI composite buffer release")

left = sorted(set(re.findall(r"\w*GLES\w*", h + cpp)) - {"CDVBridgeGLES", "DVBridgeGLES"})
open(base + "WinSystemGbmGLContext.h", "w").write(h)
open(base + "WinSystemGbmGLContext.cpp", "w").write(cpp)
print("written; GLES names left:", left)
