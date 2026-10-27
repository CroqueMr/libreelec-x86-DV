"""A rejected HDR request must not retain a previous HDR blob or PQ GUI state."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class HDRAdmissionStateTests(unittest.TestCase):
    def test_rejected_and_accepted_metadata_requests(self):
        code = body((TREE / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text(),
                    'bool CWinSystemGbm::SetHDR(')
        program = r'''
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <memory>
#include <optional>
enum { AVCOL_TRC_BT709=1, AVCOL_TRC_SMPTE2084=16, AVCOL_TRC_ARIB_STD_B67=18,
       LOGDEBUG, LOGWARNING, LOGVIDEO, SETTING_WINSYSTEM_IS_HDR_DISPLAY };
struct AVRational {int num,den;};
double av_q2d(AVRational q) {return double(q.num)/q.den;}
struct AVMasteringDisplayMetadata {
 AVRational display_primaries[3][2]{},white_point[2]{},min_luminance{},max_luminance{};
 bool has_primaries=false,has_luminance=false;
};
struct AVContentLightMetadata {unsigned MaxCLL,MaxFALL;};
struct VideoPicture {int color_transfer=AVCOL_TRC_SMPTE2084;};
namespace KODI::UTILS {
 enum class Eotf {TRADITIONAL_SDR=0,PQ=2,HLG=3};
 constexpr int HDMI_STATIC_METADATA_TYPE1=0;
 Eotf GetEOTF(const VideoPicture& p) {return p.color_transfer==16 ? Eotf::PQ : Eotf::HLG;}
 AVMasteringDisplayMetadata mastering;
 AVContentLightMetadata light{3500,500};
 const auto* GetMasteringDisplayMetadata(const VideoPicture&) {return &mastering;}
 const auto* GetContentLightMetadata(const VideoPicture&) {return &light;}
}
struct hdr_output_metadata {
 unsigned metadata_type{};
 struct {uint8_t eotf{},metadata_type{};
 struct {uint16_t x{},y{};} display_primaries[3],white_point;
 uint16_t max_display_mastering_luminance{},min_display_mastering_luminance{},max_cll{},max_fall{};
 } hdmi_metadata_type1;
};
struct CDRMPropertyBlob {
 static inline bool allocation=true;
 static inline hdr_output_metadata payload;
 unsigned id{};
 CDRMPropertyBlob()=default;
 CDRMPropertyBlob(int,const void* data,unsigned) {payload=*static_cast<const hdr_output_metadata*>(data);id=allocation?17:0;}
 void Reset() {id=0;} bool IsValid() const {return id!=0;} unsigned Get() const {return id;}
};
struct Connector {bool metadata=true;bool SupportsProperty(const char*) {return metadata;}};
struct DRM {virtual ~DRM()=default;};
struct CDRMAtomic : DRM {
 Connector connector;bool connected=true,accept=true,pending=false;unsigned queued=999;int active=0;
 void SetSDRRestorePending(bool value){pending=value;}
 Connector* GetConnector() {return connected?&connector:nullptr;}
 int GetFileDescriptor() {return 3;}
 bool AddProperty(Connector*,const char*,unsigned id) {if(!accept)return false;queued=id;return true;}
 void SetActive(bool) {++active;}
};
struct DisplayInfo {
 bool metadata=true,eotf=true;
 bool SupportsHDRStaticMetadataType1() {return metadata;}
 bool SupportsEOTF(KODI::UTILS::Eotf) {return eotf;}
};
struct Settings {bool enabled=true;bool GetBool(int) {return enabled;}};
struct SettingsComponent {
 std::shared_ptr<Settings> settings=std::make_shared<Settings>();
 auto GetSettings() {return settings;}
};
struct CServiceBroker {static inline auto component=std::make_shared<SettingsComponent>();
 static auto GetSettingsComponent() {return component;}};
struct CLog {template<class... T>static void Log(T...) {} template<class... T>static void LogF(T...) {}};
struct CWinSystemGbm {
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<DisplayInfo> m_info=std::make_shared<DisplayInfo>();
 std::optional<uint64_t> m_queuedHdrMetadata;
 CDRMPropertyBlob m_hdrBlob;
 KODI::UTILS::Eotf m_eotf=KODI::UTILS::Eotf::TRADITIONAL_SDR;
 bool SetHDR(const VideoPicture* videoPicture) BODY
};
int main(int argc,char** argv) {
 assert(argc==2);int scenario=std::atoi(argv[1]);
 using KODI::UTILS::Eotf;
 CWinSystemGbm window;VideoPicture picture;
 auto drm=std::dynamic_pointer_cast<CDRMAtomic>(window.m_DRM);
 auto& md=KODI::UTILS::mastering;
 md.has_luminance=true;md.max_luminance={4000,1};md.min_luminance={1,10000};
 if(scenario==0) {
   drm->connector.metadata=false;
   assert(!window.SetHDR(&picture));
   assert(window.m_eotf==Eotf::TRADITIONAL_SDR);
 } else if(scenario==1) {
   assert(window.SetHDR(&picture));
   drm->connector.metadata=false;
   assert(!window.SetHDR(&picture));
   assert(!window.m_hdrBlob.IsValid() && window.m_eotf==Eotf::TRADITIONAL_SDR);
 } else if(scenario==2) {
   drm->accept=false;
   assert(!window.SetHDR(&picture));
   assert(window.m_eotf==Eotf::TRADITIONAL_SDR && !window.m_hdrBlob.IsValid());
 } else if(scenario==3) {
   CDRMPropertyBlob::allocation=false;
   assert(!window.SetHDR(&picture));
   assert(window.m_eotf==Eotf::TRADITIONAL_SDR && drm->active==0);
 } else if(scenario==4) {
   for(auto transfer : {AVCOL_TRC_SMPTE2084,AVCOL_TRC_ARIB_STD_B67}) {
     picture.color_transfer=transfer;
     assert(window.SetHDR(&picture) && drm->queued==17 && *window.m_queuedHdrMetadata==17);
     assert(window.m_eotf==(transfer==16?Eotf::PQ:Eotf::HLG));
     const auto& signal=CDRMPropertyBlob::payload.hdmi_metadata_type1;
     assert(signal.max_display_mastering_luminance==4000 && signal.min_display_mastering_luminance==1);
     assert(signal.max_cll==3500 && signal.max_fall==500);
   }
   assert(!window.SetHDR(nullptr));
   assert(drm->queued==0 && window.m_eotf==Eotf::TRADITIONAL_SDR && !window.m_hdrBlob.IsValid());
 } else if(scenario==5) {
   assert(window.SetHDR(&picture));window.m_info->eotf=false;
   assert(!window.SetHDR(&picture) && window.m_eotf==Eotf::TRADITIONAL_SDR);
 } else if(scenario==6) {
   assert(window.SetHDR(&picture));CServiceBroker::component->settings->enabled=false;
   assert(!window.SetHDR(&picture) && window.m_eotf==Eotf::TRADITIONAL_SDR);
 } else if(scenario==7) {
   assert(window.SetHDR(&picture));picture.color_transfer=AVCOL_TRC_BT709;
   assert(!window.SetHDR(&picture) && window.m_eotf==Eotf::TRADITIONAL_SDR);
 } else if(scenario==8) {
   assert(window.SetHDR(&picture));CServiceBroker::component->settings->enabled=false;
   assert(!window.SetHDR(nullptr) && drm->pending);
 } else if(scenario==9) {
   assert(!window.SetHDR(nullptr) && drm->pending);
   drm->accept=false;assert(!window.SetHDR(&picture) && drm->pending);
   drm->accept=true;assert(window.SetHDR(&picture) && !drm->pending && drm->queued==17);
 } else if(scenario==10) {
   assert(!window.SetHDR(nullptr) && drm->pending);
   picture.color_transfer=AVCOL_TRC_BT709;
   assert(!window.SetHDR(&picture) && drm->pending);
 } else if(scenario==11) {
   drm->connected=false;
   assert(!window.SetHDR(nullptr) && drm->pending);
 }
}
'''.replace('BODY', code)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root / 'test.cpp'),
                                    '-o', str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            for scenario in range(12):
                with self.subTest(scenario=scenario):
                    run = subprocess.run([str(root / 'test'), str(scenario)], capture_output=True, text=True)
                    self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
