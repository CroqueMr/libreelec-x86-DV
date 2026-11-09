"""Tag normalized SDR captures independently of native/PQ display state."""
from pathlib import Path
import subprocess,tempfile,unittest
from test_native_video_source import TREE,body

class SDRCaptureColorTests(unittest.TestCase):
    def test_normalized_sdr_capture_is_full_range_srgb_without_hdr_tags(self):
        code=body((TREE/'xbmc/rendering/capture/CaptureMetadata.cpp').read_text(),
                  'ImageColorMetadata GetOutputColorMetadata(')
        program=r'''
#include <cassert>
constexpr int AVCOL_PRI_BT709=1,AVCOL_PRI_BT2020=9,AVCOL_PRI_SMPTE170M=6;
constexpr int AVCOL_TRC_BT709=1,AVCOL_TRC_SMPTE170M=6,AVCOL_TRC_IEC61966_2_1=13;
constexpr int AVCOL_TRC_SMPTE2084=16,AVCOL_TRC_ARIB_STD_B67=18,AVCOL_TRC_BT2020_10=14;
constexpr int AVCOL_RANGE_JPEG=2,AVCOL_RANGE_MPEG=1;
namespace KODI::UTILS {enum class Colorimetry{BT709,BT2020_RGB,BT2020_YCC,BT2020_CYCC};
 enum class Eotf{SDR,PQ,HLG};}
struct CWinSystemBase{
 bool custom=true,sdr=true;KODI::UTILS::Eotf eotf=KODI::UTILS::Eotf::PQ;
 KODI::UTILS::Colorimetry GetColorimetry(){return KODI::UTILS::Colorimetry::BT709;}
 auto GetEotf(){return eotf;}auto& GetGfxContext(){return *this;}
 int GetWidth(){return 1920;}int GetHeight(){return 1080;}bool UseLimitedColor(){return true;}
};
namespace KODI::WINDOWING::GBM{
 bool HasDVBridgeScreenshot(CWinSystemBase& window){return window.custom;}
 bool IsDVBridgeScreenshotSDR(CWinSystemBase& window){return window.custom&&window.sdr;}
}
struct ImageColorMetadata{int primaries{},transfer{},range{};};
ImageColorMetadata GetOutputColorMetadata(CWinSystemBase& winSystem) BODY
int main(){
 CWinSystemBase window;auto color=GetOutputColorMetadata(window);
 assert(color.primaries==AVCOL_PRI_BT709 && color.transfer==AVCOL_TRC_IEC61966_2_1 && color.range==AVCOL_RANGE_JPEG);
 window.sdr=false;color=GetOutputColorMetadata(window);
 assert(color.primaries==AVCOL_PRI_BT2020 && color.transfer==AVCOL_TRC_SMPTE2084 && color.range==AVCOL_RANGE_JPEG);
 window.custom=false;window.eotf=KODI::UTILS::Eotf::SDR;color=GetOutputColorMetadata(window);
 assert(color.primaries==AVCOL_PRI_BT709 && color.transfer==AVCOL_TRC_BT709 && color.range==AVCOL_RANGE_MPEG);
}
'''.replace('BODY',code)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-DHAVE_DVBRIDGE',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

if __name__=='__main__':unittest.main()
