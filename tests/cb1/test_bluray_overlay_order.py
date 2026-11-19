"""Exercise the native overlay container's source ordering and subtitle quota."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class BlurayOverlayOrder(unittest.TestCase):
    def test_menu_layers_stay_above_subtitles_and_do_not_consume_their_quota(self):
        path = TREE / 'xbmc/cores/VideoPlayer/DVDOverlayContainer.cpp'
        source = path.read_text()
        methods = {}
        for signature in (
            'void CDVDOverlayContainer::ProcessAndAddOverlayIfValid',
            'void CDVDOverlayContainer::Clear(DVDOverlaySource source)',
            'size_t CDVDOverlayContainer::GetSize(DVDOverlaySource source)',
        ):
            methods[signature] = body(source, signature) if signature in source else '{}'
        program = r'''
#include <algorithm>
#include <cassert>
#include <memory>
#include <mutex>
#include <vector>
enum class DVDOverlaySource { SUBTITLE, MENU };
struct CDVDOverlay {
  DVDOverlaySource source;
  double iPTSStartTime{};
  double iPTSStopTime{};
  bool replace{true};
  DVDOverlaySource GetSource() const { return source; }
};
struct CDVDOverlayContainer : std::recursive_mutex {
  std::vector<std::shared_ptr<CDVDOverlay>> m_overlays;
  void ProcessAndAddOverlayIfValid(const std::shared_ptr<CDVDOverlay>& pOverlay);
  void Clear(DVDOverlaySource source);
  size_t GetSize(DVDOverlaySource source);
};
void CDVDOverlayContainer::ProcessAndAddOverlayIfValid(const std::shared_ptr<CDVDOverlay>& pOverlay)
ADD
void CDVDOverlayContainer::Clear(DVDOverlaySource source)
CLEAR
size_t CDVDOverlayContainer::GetSize(DVDOverlaySource source)
COUNT
int main() {
  using enum DVDOverlaySource;
  CDVDOverlayContainer container;
  auto menu = std::make_shared<CDVDOverlay>(CDVDOverlay{MENU});
  auto subtitle = std::make_shared<CDVDOverlay>(CDVDOverlay{SUBTITLE, 1000, 3000});
  auto nextMenu = std::make_shared<CDVDOverlay>(CDVDOverlay{MENU, 2000});
  container.ProcessAndAddOverlayIfValid(menu);
  container.ProcessAndAddOverlayIfValid(subtitle);
  assert(container.m_overlays.front() == subtitle);
  assert(container.m_overlays.back() == menu && menu->iPTSStopTime == 0);
  container.ProcessAndAddOverlayIfValid(nextMenu);
  assert(container.m_overlays[1] == menu && container.m_overlays.back() == nextMenu);
  assert(menu->iPTSStopTime == 2000 && subtitle->iPTSStopTime == 3000);
  assert(container.GetSize(SUBTITLE) == 1 && container.GetSize(MENU) == 2);
  container.Clear(SUBTITLE);
  assert(container.GetSize(SUBTITLE) == 0 && container.m_overlays.size() == 2);
}
'''
        program = (program.replace('\nADD\n', methods[next(iter(methods))])
                   .replace('\nCLEAR\n', methods['void CDVDOverlayContainer::Clear(DVDOverlaySource source)'])
                   .replace('\nCOUNT\n', methods['size_t CDVDOverlayContainer::GetSize(DVDOverlaySource source)']))
        with tempfile.TemporaryDirectory() as directory:
            source_file = Path(directory) / 'test.cpp'
            binary = Path(directory) / 'test'
            source_file.write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(source_file), '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
