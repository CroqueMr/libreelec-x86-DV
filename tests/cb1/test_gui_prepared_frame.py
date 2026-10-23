"""A delayed prepared picture must retain its GUI and L5 snapshot together."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from shipped_kodi import shipped_code
from test_native_video_source import body


class PreparedGUI(unittest.TestCase):
    def test_delayed_handoff_cannot_redraw_gui_before_prepared_picture_is_submitted(self):
        source = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        begin = body(source, 'bool CWinSystemGbmGLESContext::BeginRender()')
        program = r'''
#include <cassert>
#include <iostream>
struct CRenderSystemGLES {
  unsigned guiPasses=0;
  bool BeginRender() { ++guiPasses; return true; }
};
struct CWinSystemGbmGLESContext : CRenderSystemGLES {
  bool m_cb1FramePending=true,m_dvFrame=true,kmsPending=true;
  unsigned submitted=0;
  bool CompleteDVBridgePage(unsigned) { return !kmsPending; }
  void PresentFrame(bool,bool) {
    if (!CompleteDVBridgePage(8)) return;
    if (m_cb1FramePending && m_dvFrame) {
      ++submitted; m_cb1FramePending=m_dvFrame=false;
    }
  }
  bool BeginRender() @@BEGIN@@
};
int main() {
  CWinSystemGbmGLESContext window;
  // The old KMS page still holds the queue; the next prepared picture owns its GUI.
  assert(!window.BeginRender());
  assert(window.guiPasses==0 && window.submitted==0);
  window.kmsPending=false;
  const bool draw=window.BeginRender();
  assert(!draw && "Submitted prepared picture must not be redrawn in the same pass");
  assert((!draw || window.submitted==1) &&
         "GUI overwrite admitted before prepared picture and its L5 snapshot were submitted");
  assert(window.submitted==1);
  assert(window.BeginRender());
  assert(window.submitted==1);
  // Ordinary rendering does not submit or wait for a CB1 frame.
  CWinSystemGbmGLESContext ordinary;
  ordinary.m_cb1FramePending=ordinary.m_dvFrame=false;
  assert(ordinary.BeginRender() && ordinary.submitted==0);
  // An unfinished GPU preparation may continue through the normal render pass.
  CWinSystemGbmGLESContext preparing;
  preparing.m_dvFrame=false;
  assert(preparing.BeginRender() && preparing.submitted==0);
  std::cout<<"prepared GUI/L5 ownership retained across delayed KMS handoff\n";
}
'''.replace('@@BEGIN@@', begin)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'check.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'check.cpp'),
                                    '-o', str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
