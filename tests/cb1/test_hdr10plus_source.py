"""The HDMI consumer must retain the selected frame's immutable FFmpeg metadata."""
import unittest
from test_native_video_sidedata import SideDataTests as SnapshotChecks
from test_native_video_source import TREE, body
from pathlib import Path


class HDR10PlusSourceTests(unittest.TestCase):
    def test_only_selected_pq_frame_is_staged_and_stale_metadata_is_cleared(self):
        source=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        signature='void CWinSystemGbmGLESContext::StageNativeHDR10Plus(bool overlay)'
        implementation=body(source,signature) if signature in source else '{}'
        serializer=Path(__file__).resolve().parents[2]/'CB1/src/cb1_hdr10plus.c'
        SnapshotChecks().compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include <cassert>
#include <array>
#include <optional>
#include <string>
#include <vector>
#define FMT_HEADER_ONLY
#include <fmt/format.h>
#include "SERIALIZER"
namespace KODI::UTILS {enum class Eotf {PQ,TRADITIONAL_SDR};}
struct DRM {virtual ~DRM()=default;};
struct Connector {bool supported=true; bool SupportsProperty(const char*) const {return supported;}};
struct CDRMAtomic:DRM {
 Connector connector;
 std::optional<std::array<uint8_t,31>> packet;
 uint64_t generation{};
 Connector* GetConnector(){return &connector;}
 void StageHDR10Plus(std::optional<std::array<uint8_t,31>> p,uint64_t g){packet=p;generation=g;}
};
struct Display {int version=1; int HDR10PlusVersion() const {return version;}};
struct Cache {uint64_t generation=7; uint64_t GetVideoProcessingGeneration(){return generation;}};
struct CServiceBroker {static inline Cache cache;static Cache& GetDataCacheCore(){return cache;}};
enum {LOGINFO=1};
struct CLog {template<class... A>static void Log(A...) {}};
namespace DVBRIDGE {
inline std::vector<std::string> messages;
template<class... A>bool DiagnosticLog(int,fmt::format_string<A...> f,A&&...args){
 messages.push_back(fmt::format(f,std::forward<A>(args)...));return true;
}
}
struct CWinSystemGbmGLESContext {
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<const VideoSourceSideData> m_videoSourceSideData;
 Display display;KODI::UTILS::Eotf eotf=KODI::UTILS::Eotf::PQ;
 std::string m_hdr10plusReason;
 int depth=10;int GetOutputBitDepth()const{return depth;}
 const Display* GetDisplayInfo() const {return &display;}
 auto GetEotf() const {return eotf;}
 void StageNativeHDR10Plus(bool overlay) BODY
};
int main() {
 CWinSystemGbmGLESContext w;auto drm=std::dynamic_pointer_cast<CDRMAtomic>(w.m_DRM);
 AVFrame* frame=av_frame_alloc();auto* hdr=av_dynamic_hdr_plus_create_side_data(frame);
 hdr->itu_t_t35_country_code=0xb5;hdr->application_version=1;hdr->num_windows=1;
 hdr->targeted_system_display_maximum_luminance={1000,1};auto& p=hdr->params[0];
 for(auto& m:p.maxscl)m={5000,100000};p.average_maxrgb={1600,100000};p.fraction_bright_pixels={0,1};
 const int perc[]={1,5,10,25,50,75,90,95,99};p.num_distribution_maxrgb_percentiles=9;
 for(int i=0;i<9;++i)p.distribution_maxrgb[i]={(uint8_t)perc[i],{i==1?0:i==2?255:5000,100000}};
 w.m_videoSourceSideData=VideoSourceSideData::Capture(7,1,AV_CODEC_ID_HEVC,frame,nullptr);
 w.StageNativeHDR10Plus(false);assert(drm->packet && drm->generation==7);
 assert((*drm->packet)[30]==0x40 && (*drm->packet)[8]==10);
 auto first=*drm->packet;
 assert(!DVBRIDGE::messages.empty());
 assert(DVBRIDGE::messages.back().find("app_version=1")!=std::string::npos);
 const auto logs=DVBRIDGE::messages.size();
 w.StageNativeHDR10Plus(false);assert(*drm->packet==first);
 assert(DVBRIDGE::messages.size()==logs); // Repeated status does not log per frame.
 // Real decoded V1 variants may reach the strict reserved-field gate.
 p.distribution_maxrgb[1].percentile={2940,100000};
 w.m_videoSourceSideData=VideoSourceSideData::Capture(7,2,AV_CODEC_ID_HEVC,frame,nullptr);
 w.StageNativeHDR10Plus(false);
 assert(!drm->packet && w.m_hdr10plusReason=="unrepresentable-metadata");
 assert(DVBRIDGE::messages.back().find("slot5=2940/100000")!=std::string::npos);
 assert(DVBRIDGE::messages.back().find("slot10=255/100000")!=std::string::npos);
 assert(p.distribution_maxrgb[1].percentile.num==2940);
 p.distribution_maxrgb[1].percentile={0,100000};
 w.m_videoSourceSideData=VideoSourceSideData::Capture(7,3,AV_CODEC_ID_HEVC,frame,nullptr);
 w.StageNativeHDR10Plus(true);assert((*drm->packet)[30]==0xc0);
 w.depth=8;w.StageNativeHDR10Plus(false);assert(!drm->packet && w.m_hdr10plusReason=="output-buffer-below-10-bit");
 w.depth=10;w.StageNativeHDR10Plus(false);assert(drm->packet);
 w.depth=16;w.StageNativeHDR10Plus(false);assert(drm->packet);
 w.eotf=KODI::UTILS::Eotf::TRADITIONAL_SDR;w.StageNativeHDR10Plus(false);assert(!drm->packet);
 w.eotf=KODI::UTILS::Eotf::PQ;w.display.version=0;w.StageNativeHDR10Plus(false);assert(!drm->packet);
 w.display.version=1;drm->connector.supported=false;w.StageNativeHDR10Plus(false);assert(!drm->packet);
 drm->connector.supported=true;CServiceBroker::cache.generation=8;w.StageNativeHDR10Plus(false);assert(!drm->packet);
 w.m_videoSourceSideData.reset();w.StageNativeHDR10Plus(false);assert(!drm->packet);
 av_frame_free(&frame);
}
'''.replace('SERIALIZER',str(serializer)).replace('BODY',implementation))

    def test_owned_metadata_survives_decoder_reuse_and_supports_v0(self):
        SnapshotChecks().compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include <cassert>
int main() {
 AVFrame* frame=av_frame_alloc();
 auto* hdr=av_dynamic_hdr_plus_create_side_data(frame); assert(hdr);
 hdr->itu_t_t35_country_code=0xb5; hdr->application_version=1; hdr->num_windows=1;
 hdr->targeted_system_display_maximum_luminance={1000,1};
 auto& p=hdr->params[0];
 for(auto& max:p.maxscl) max={0,1};
 p.average_maxrgb={2000,100000}; p.fraction_bright_pixels={0,1};
 auto a=VideoSourceSideData::Capture(7,1,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(a && a->HDR10Plus() && a->HDR10Plus()->params[0].average_maxrgb.num==2000);
 hdr->params[0].average_maxrgb={3000,100000}; hdr->application_version=0;
 auto b=VideoSourceSideData::Capture(7,2,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(b && b->HDR10Plus() && b->HDR10Plus()->application_version==0);
 assert(a->HDR10Plus()->application_version==1 && a->HDR10Plus()->params[0].average_maxrgb.num==2000);
 av_frame_remove_side_data(frame,AV_FRAME_DATA_DYNAMIC_HDR_PLUS);
 auto c=VideoSourceSideData::Capture(8,1,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(c && !c->HDR10Plus());
 av_frame_free(&frame);
 assert(b->HDR10Plus()->params[0].average_maxrgb.num==3000);
}
''')


if __name__ == '__main__':
    unittest.main()
