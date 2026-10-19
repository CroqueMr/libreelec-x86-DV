"""A failed video-start EDID read cannot erase the last usable display."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class DisplayRefreshTests(unittest.TestCase):
    def test_actual_refresh_preserves_valid_information(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
        self.assertIn('bool CWinSystemGbm::RefreshDisplayInfoForVideo()', source,
                      'video-start display refresh is missing')
        method = body(source, 'bool CWinSystemGbm::RefreshDisplayInfoForVideo()')
        program = r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <vector>
constexpr int LOGINFO=0;
namespace DVBRIDGE {template<class... T> void DiagnosticLog(T&&...) {}}
namespace UTILS {struct CDisplayInfo {
 int value;
 static std::unique_ptr<CDisplayInfo> Create(const std::vector<uint8_t>& bytes) {
  return bytes.empty() || bytes[0]==255 ? nullptr : std::make_unique<CDisplayInfo>(bytes[0]);
 }
};}
struct Connector {
 std::vector<uint8_t> next; int reads{};
 std::vector<uint8_t> GetEDID(bool refresh) {assert(refresh); ++reads; return next;}
 unsigned GetId() const {return 7;}
};
struct DRM {Connector connector; Connector* GetConnector() {return &connector;}};
struct CWinSystemGbm {
 std::unique_ptr<DRM> m_DRM=std::make_unique<DRM>();
 std::unique_ptr<UTILS::CDisplayInfo> m_info=std::make_unique<UTILS::CDisplayInfo>(1);
 std::vector<uint8_t> m_displayEdid{1};
 bool RefreshDisplayInfoForVideo() METHOD
};
int main() {
 CWinSystemGbm window;
 auto* original=window.m_info.get();
 assert(!window.RefreshDisplayInfoForVideo() && window.m_info.get()==original);
 window.m_DRM->connector.next={255};
 assert(!window.RefreshDisplayInfoForVideo() && window.m_info.get()==original);
 window.m_DRM->connector.next={1};
 assert(!window.RefreshDisplayInfoForVideo() && window.m_info.get()==original);
 window.m_DRM->connector.next={2};
 assert(window.RefreshDisplayInfoForVideo() && window.m_info->value==2);
 assert(window.m_displayEdid==std::vector<uint8_t>{2});
 window.m_DRM.reset();
 assert(!window.RefreshDisplayInfoForVideo() && window.m_info->value==2);
}
'''.replace('METHOD', method)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__': unittest.main()
