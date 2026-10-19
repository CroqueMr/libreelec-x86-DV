"""Exercise the shipped ordinary-output transaction for SDR, PQ and HLG."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class OrdinaryGUITransferTests(unittest.TestCase):
    def test_only_hdr_video_enables_hdr_gui_compositing(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        function = body(source, 'bool CWinSystemGbmGLESContext::StageOrdinaryDVOutput(')
        program = r'''
#include <cassert>
#include <memory>
#include <optional>
enum {AVCOL_TRC_BT709=1, AVCOL_TRC_UNSPECIFIED=2,
      AVCOL_TRC_SMPTE2084=16, AVCOL_TRC_ARIB_STD_B67=18};
struct VideoPicture {int color_transfer;};
struct DRM {virtual ~DRM()=default;};
struct CDRMAtomic : DRM {int GetConnector(){return 0;}
 bool AddProperty(int,const char*,int){return true;}};
struct State {bool Captured(){return false;} bool Stage(CDRMAtomic&,bool){return true;}};
struct CWinSystemGbmGLESContext {
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>(); State m_dvState;
 std::optional<int> m_hdrDeepColorPrevious; bool m_dvOrdinaryFrame=false;
 int gui=-1; const VideoPicture* color{}; const VideoPicture* hdr{};
 void SetColorimetry(const VideoPicture* p){color=p;}
 void SetHDR(const VideoPicture* p){hdr=p;}
 void SetGuiCompositing(int transfer){gui=transfer;}
 bool RejectDVOutputSurface(){return false;}
 bool StageOrdinaryDVOutput(const VideoPicture* picture);
};
bool CWinSystemGbmGLESContext::StageOrdinaryDVOutput(const VideoPicture* picture) BODY
int main() {
 CWinSystemGbmGLESContext window;
 for(int transfer : {AVCOL_TRC_BT709,AVCOL_TRC_UNSPECIFIED,
                    AVCOL_TRC_SMPTE2084,AVCOL_TRC_ARIB_STD_B67}) {
   VideoPicture picture{transfer};
   assert(window.StageOrdinaryDVOutput(&picture));
   assert(window.gui == ((transfer==16 || transfer==18) ? transfer : 0));
   assert(window.hdr==&picture && window.color==&picture && window.m_dvOrdinaryFrame);
 }
 assert(window.StageOrdinaryDVOutput(nullptr) && window.gui==0);
 window.m_DRM.reset(); window.gui=-1;
 assert(!window.StageOrdinaryDVOutput(nullptr) && window.gui==-1);
}
'''.replace('BODY', function)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'),
                                    '-o', str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
