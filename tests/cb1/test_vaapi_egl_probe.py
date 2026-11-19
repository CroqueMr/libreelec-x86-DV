"""Exercise the shipped VAAPI startup probe against explicit DMA-BUF layout."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_gbm_colour_owner import method


@unittest.skipUnless(os.environ.get("KODI_NATIVE_SOURCE_TREE"), "Requires patched Kodi sources")
class VaapiEglProbe(unittest.TestCase):
    def test_tiled_surface_is_probed_with_its_exported_modifier(self):
        root = Path(os.environ["KODI_NATIVE_SOURCE_TREE"]) / "xbmc"
        source = (root / "cores/VideoPlayer/VideoRenderers/HwDecRender/VaapiEGL.cpp").read_text()
        header = (root / "utils/EGLUtils.h").read_text()
        start = header.index("template<std::size_t AttributeCount>\nclass CEGLAttributes\n")
        attributes = header[start:header.index("class CEGLContextUtils", start)]
        program = r'''
#include <array>
#include <cassert>
#include <cerrno>
#include <cstdint>
#include <cstring>
#include <stdexcept>
#include <fcntl.h>
#include <unistd.h>
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <libdrm/drm_fourcc.h>
#include <va/va.h>
#include <va/va_drmcommon.h>

ATTRIBUTES
constexpr uint64_t tiled = DRM_FORMAT_MOD_NVIDIA_BLOCK_LINEAR_2D(0, 1, 2, 6, 4);
bool modifiers = true;
int exportedFd = -1;
unsigned surfaces = 0, images = 0;
namespace CEGLUtils {
bool HasExtension(EGLDisplay, const char* name) {
  assert(!std::strcmp(name, "EGL_EXT_image_dma_buf_import_modifiers"));
  return modifiers;
}
}
struct CVaapi2Texture {
  static bool TestEsh(VADisplay, EGLDisplay, std::uint32_t, std::int32_t);
};
EGLImageKHR EGLAPIENTRY createImage(EGLDisplay, EGLContext, EGLenum target,
                                     EGLClientBuffer, const EGLint* a) {
  assert(target == EGL_LINUX_DMA_BUF_EXT);
  unsigned parts = 0;
  uint64_t modifier = 0;
  for (; *a != EGL_NONE; a += 2) {
    if (a[0] == EGL_DMA_BUF_PLANE0_MODIFIER_LO_EXT) {
      modifier |= static_cast<uint32_t>(a[1]);
      parts |= 1;
    } else if (a[0] == EGL_DMA_BUF_PLANE0_MODIFIER_HI_EXT) {
      modifier |= static_cast<uint64_t>(static_cast<uint32_t>(a[1])) << 32;
      parts |= 2;
    }
  }
  if (modifiers ? parts != 3 || modifier != tiled : parts != 0)
    return EGL_NO_IMAGE_KHR;
  ++images;
  return reinterpret_cast<EGLImageKHR>(1);
}
EGLBoolean EGLAPIENTRY destroyImage(EGLDisplay, EGLImageKHR) {
  --images;
  return EGL_TRUE;
}
__eglMustCastToProperFunctionPointerType EGLAPIENTRY eglGetProcAddress(const char* name) {
  if (!std::strcmp(name, "eglCreateImageKHR"))
    return reinterpret_cast<__eglMustCastToProperFunctionPointerType>(createImage);
  assert(!std::strcmp(name, "eglDestroyImageKHR"));
  return reinterpret_cast<__eglMustCastToProperFunctionPointerType>(destroyImage);
}
VAStatus vaCreateSurfaces(VADisplay, unsigned, unsigned, unsigned, VASurfaceID* ids,
                          unsigned, VASurfaceAttrib*, unsigned) {
  *ids = ++surfaces;
  return VA_STATUS_SUCCESS;
}
VAStatus vaDestroySurfaces(VADisplay, VASurfaceID*, int) {
  --surfaces;
  return VA_STATUS_SUCCESS;
}
VAStatus vaExportSurfaceHandle(VADisplay, VASurfaceID, uint32_t, uint32_t, void* out) {
  auto* desc = static_cast<VADRMPRIMESurfaceDescriptor*>(out);
  *desc = {};
  desc->num_objects = desc->num_layers = 1;
  exportedFd = open("/dev/null", O_RDONLY);
  assert(exportedFd >= 0);
  desc->objects[0].fd = exportedFd;
  desc->objects[0].drm_format_modifier = tiled;
  desc->layers[0].drm_format = DRM_FORMAT_R16;
  desc->layers[0].pitch[0] = 3840;
  return VA_STATUS_SUCCESS;
}
namespace CLog {
template<class... Args> void Log(int, Args...) {}
}
constexpr int LOGERROR = 0;
PROBE
int main() {
  for (bool supports : {true, false}) {
    modifiers = supports;
    assert(CVaapi2Texture::TestEsh(nullptr, nullptr, VA_RT_FORMAT_YUV420_10, VA_FOURCC_P010));
    assert(surfaces == 0 && images == 0);
    assert(fcntl(exportedFd, F_GETFD) == -1 && errno == EBADF);
  }
}
'''.replace("ATTRIBUTES", attributes).replace("PROBE", method(source, "CVaapi2Texture::TestEsh"))
        with tempfile.TemporaryDirectory() as directory:
            binary = str(Path(directory) / "check")
            build = subprocess.run(
                ["c++", "-std=c++20", "-x", "c++", "-", "-o", binary],
                input=program, text=True, capture_output=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([binary], text=True, capture_output=True)
            self.assertEqual(run.returncode, 0, run.stderr)
