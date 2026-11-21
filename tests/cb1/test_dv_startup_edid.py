"""An empty EDID during a recent Master Reference handoff is provisional."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from shipped_kodi import shipped_code
from test_native_video_source import body


class DVStartupEdid(unittest.TestCase):
    def test_first_open_wait_is_bounded_and_owned_by_the_current_connector(self):
        source = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        signature = 'void CWinSystemGbmGLESContext::BeginDVStartupEdidWait()'
        self.assertIn(signature, source, 'The existing open-time refresh has no transient state')
        program = r'''#include <atomic>
#include <cassert>
#include <cstdint>
#include <vector>
namespace DVBRIDGE {
uint64_t now = 3000;
uint64_t DiagnosticNowMs() { return now; }
}
struct CLog { template<class... Args> static void Log(Args...) {} };
constexpr int LOGDEBUG = 0;
struct Connector { uint32_t id{42}; uint32_t GetId() const { return id; } };
struct DRM { Connector *connector{}; Connector *GetConnector() { return connector; } };
struct Timer { template<class T> void Set(T) {} };
#include <chrono>
using namespace std::chrono_literals;
struct CWinSystemGbmGLESContext {
  DRM *m_DRM{};
  uint32_t m_lastMasterConnector{42};
  uint64_t m_lastMasterPresentationMs{2900};
  std::vector<int> m_displayEdid;
  bool GetDisplayInfo() const { return !m_displayEdid.empty(); }
  std::atomic<uint64_t> m_dvStartupEdidUntil{};
  Timer m_lldvEdidRefresh;
  void BeginDVStartupEdidWait() BODY
  bool PendingDVStartupEdid() const PENDING
};
int main() {
  Connector connector;
  DRM drm{&connector};
  CWinSystemGbmGLESContext window;
  window.m_DRM = &drm;
  window.BeginDVStartupEdidWait();
  assert(window.PendingDVStartupEdid());
  DVBRIDGE::now = 4499;
  assert(window.PendingDVStartupEdid());
  ++DVBRIDGE::now;
  assert(!window.PendingDVStartupEdid());
  window.m_lastMasterPresentationMs = 4499;
  connector.id = 43;
  window.BeginDVStartupEdidWait();
  assert(!window.PendingDVStartupEdid());
  connector.id = 42;
  window.m_displayEdid = {1};
  window.BeginDVStartupEdidWait();
  assert(!window.PendingDVStartupEdid());
  window.m_displayEdid.clear();
  DVBRIDGE::now = 7000;
  window.BeginDVStartupEdidWait();
  assert(!window.PendingDVStartupEdid());
}
'''.replace('BODY', body(source, signature)).replace(
            'PENDING', body(source, 'bool CWinSystemGbmGLESContext::PendingDVStartupEdid() const'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / 'check.cpp'
            fixture.write_text(program)
            binary = root / 'check'
            subprocess.run(['c++', '-std=c++20', str(fixture), '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True)
