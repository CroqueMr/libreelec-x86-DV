"""Check both renderer entry points against the current playback generation."""

import os
from pathlib import Path
import resource
import subprocess
import tempfile
import unittest

from test_native_video_source import body


@unittest.skipUnless(os.environ.get("KODI_NATIVE_SOURCE_TREE"), "Set patched Kodi tree")
class SeekVideoGeneration(unittest.TestCase):
    def test_stale_decoded_and_prepared_pictures_keep_the_existing_scanout(self):
        tree = Path(os.environ["KODI_NATIVE_SOURCE_TREE"])
        renderer = tree / "xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp"
        window = tree / "xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp"
        render = body(renderer.read_text(), "bool CLinuxRendererGLES::Render(unsigned int")
        present = body(window.read_text(), "void CWinSystemGbmGLESContext::PresentFrame(")
        render = render.split("  // obtain current field")[0] + "  return true;\n}"
        present = present.split("  if (auto drm")[0] + "  Commit();\n}"
        code = r"""
#include <cassert>
#include <cstdint>
#include <memory>
#define HAVE_DVBRIDGE
struct CServiceBroker {
  static CServiceBroker GetDataCacheCore() { return {}; }
  uint64_t GetVideoProcessingGeneration() const { return 8; }
};
struct Picture {
  struct { uint64_t informationGeneration; } doviSourceInfo;
};
struct Renderer {
  struct { std::shared_ptr<Picture> doviSourcePicture; } m_buffers[1];
  bool Render(int index) RENDER
};
struct Window {
  struct Bridge {
    uint64_t generation = 7;
    uint64_t PendingSourceGeneration() const { return generation; }
  };
  std::unique_ptr<Bridge> m_dvBridge = std::make_unique<Bridge>();
  bool m_dvFrame = true, m_cb1FramePending = false, discarded = false;
  int submitted = 0;
  void DiscardDVBridgeFrame() { discarded = true; m_dvFrame = m_cb1FramePending = false; }
  void Commit() { if (m_dvFrame) ++submitted; }
  void Present() PRESENT
};
int main() {
  Renderer renderer;
  assert(renderer.Render(0));
  auto picture = std::make_shared<Picture>(Picture{{7}});
  renderer.m_buffers[0].doviSourcePicture = picture;
  assert(!renderer.Render(0));
  for (auto generation : {0, 8}) {
    picture->doviSourceInfo.informationGeneration = generation;
    assert(renderer.Render(0));
  }

  Window old;
  old.Present();
  assert(old.discarded && old.submitted == 0);
  Window pending;
  pending.m_dvFrame = false;
  pending.m_cb1FramePending = true;
  pending.Present();
  assert(pending.discarded && !pending.m_cb1FramePending);
  for (auto generation : {0, 8}) {
    Window current;
    current.m_dvBridge->generation = generation;
    current.Present();
    assert(!current.discarded && current.submitted == 1);
  }
}
""".replace("RENDER", render).replace("PRESENT", present)
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / "test.cpp").write_text(code)
            subprocess.run(["c++", "-std=c++20", str(path / "test.cpp"), "-o", str(path / "test")],
                           check=True)
            subprocess.run([str(path / "test")], cwd=path, check=True,
                           preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))


if __name__ == "__main__":
    unittest.main()
