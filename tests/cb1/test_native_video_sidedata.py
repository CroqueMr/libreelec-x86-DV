"""Compile the production source snapshot and native cache; no GPU or Kodi runtime."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class SideDataTests(unittest.TestCase):
    def test_production_picture_copy_reset_and_decoder_capture_without_bridge(self):
        header=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodec.h').read_text()
        picture='struct VideoPicture '+body(header,'struct VideoPicture')+';'
        codec=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodec.cpp').read_text()
        methods='\n'.join(signature+body(codec,signature) for signature in (
            'VideoPicture::~VideoPicture()', 'void VideoPicture::Reset()',
            'VideoPicture& VideoPicture::CopyRef(const VideoPicture &pic)',
            'VideoPicture& VideoPicture::SetParams(const VideoPicture &pic)'))
        decoder=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        self.assertTrue('void CDVDVideoCodecFFmpeg::CaptureSourceSideData(' in decoder,
                        'native source static metadata owner is missing')
        capture=body(decoder,'void CDVDVideoCodecFFmpeg::CaptureSourceSideData(')
        self.compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include <cassert>
#include <optional>
constexpr double DVD_NOPTS_VALUE=-1;
enum class StreamHdrType {HDR_TYPE_NONE};
struct CVideoBuffer {int refs=1; void Release(){--refs;} void Acquire(){++refs;}};
@@PICTURE@@
@@METHODS@@
struct Decoder {
 uint64_t m_videoProcessingGeneration=123,m_videoSourceSerial=0;
 std::optional<AVMasteringDisplayMetadata> m_sourceMasteringMetadata;
 std::optional<AVContentLightMetadata> m_sourceLightMetadata;
 struct {AVDOVIDecoderConfigurationRecord dovi{};
   std::unique_ptr<AVMasteringDisplayMetadata> masteringMetadata;
   std::unique_ptr<AVContentLightMetadata> contentLightMetadata;
 } m_hints;
 struct {AVCodecID codec_id=AV_CODEC_ID_HEVC;} context;
 decltype(context)* m_pCodecContext=&context;
 AVFrame* m_pFrame=av_frame_alloc();
 ~Decoder(){av_frame_free(&m_pFrame);}
 void Capture(VideoPicture* pVideoPicture) @@CAPTURE@@
};
int main(){
 VideoPicture first{},second{},params{}; Decoder decoder;
 auto* inband=av_frame_new_side_data(decoder.m_pFrame,AV_FRAME_DATA_CONTENT_LIGHT_LEVEL,sizeof(AVContentLightMetadata));
 *reinterpret_cast<AVContentLightMetadata*>(inband->data)={1000,400};
 decoder.Capture(&first); assert(first.sourceSideData && first.sourceSideData->Generation()==123);
 assert(first.sourceSideData->Serial()==1 && first.sourceSideData->JSON().find("cll")!=std::string::npos);
 std::weak_ptr<const VideoSourceSideData> weak=first.sourceSideData;
 second.CopyRef(first); params.SetParams(first); assert(second.sourceSideData==params.sourceSideData);
 first.Reset(); assert(!first.sourceSideData && !weak.expired());
 second.Reset(); assert(!weak.expired()); params.Reset(); assert(weak.expired());
 av_frame_remove_side_data(decoder.m_pFrame,AV_FRAME_DATA_CONTENT_LIGHT_LEVEL); decoder.Capture(&first);
 assert(first.sourceSideData->Serial()==2 && first.sourceSideData->JSON().find("cll")!=std::string::npos);
 decoder.m_sourceLightMetadata.reset(); decoder.Capture(&first);
 assert(first.sourceSideData->Serial()==3 && first.sourceSideData->JSON()=="{}");
}
'''.replace('@@PICTURE@@',picture).replace('@@METHODS@@',methods).replace('@@CAPTURE@@',capture))

    def test_native_label_is_registered_and_reads_accepted_cache(self):
        manager=(TREE/'xbmc/GUIInfoManager.cpp').read_text()
        self.assertTrue('{"video.sidedata", PLAYER_PROCESS_VIDEOSIDEDATA}' in manager,
                      'source payload getter is not registered')
        labels=(TREE/'xbmc/guilib/guiinfo/GUIInfoLabels.h').read_text()
        import re
        definitions='\n'.join(re.findall(r'^constexpr uint32_t PLAYER_PROCESS_.*?;',labels,re.M))
        reader=(TREE/'xbmc/guilib/guiinfo/PlayerGUIInfo.cpp').read_text()
        self.assertIn('if (processingId == PLAYER_PROCESS_VIDEOSIDEDATA)',reader)
        branch=body(reader,'if (processingId == PLAYER_PROCESS_VIDEOSIDEDATA)')
        self.compile_run(r'''
#include <cassert>
#include <string>
#include <cstdint>
LABELS
struct Cache { std::string GetVideoSourceSideData() {return "accepted-source";} };
struct CServiceBroker {static Cache& GetDataCacheCore() {static Cache cache; return cache;}};
bool read(std::string& value) BRANCH
int main() {std::string value; assert(read(value)); assert(value=="accepted-source");}
'''.replace('LABELS',definitions).replace('BRANCH',branch))

    def test_presentation_stages_selected_source_and_accepts_only_success(self):
        renderer=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        self.assertTrue('m.sourceSideData = picture.sourceSideData;' in renderer,
                      'renderer slot does not retain source ownership')
        window=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        self.assertTrue('void CWinSystemGbmGLESContext::PublishVideoSource(' in window,
                      'accepted presentation source hook missing')
        code=body(window,'void CWinSystemGbmGLESContext::PublishVideoSource(')
        self.compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include <cassert>
struct Cache {
 std::shared_ptr<const VideoSourceSideData> accepted;
 bool SetVideoSourceSideData(uint64_t gen,std::shared_ptr<const VideoSourceSideData> source) {
  assert(gen==source->Generation()); accepted=std::move(source); return true;
 }
} cache;
struct CServiceBroker {static Cache& GetDataCacheCore() {return cache;}};
struct CWinSystemGbmGLESContext {
 void PublishVideoSource(bool accepted,const std::shared_ptr<const VideoSourceSideData>& source);
};
void CWinSystemGbmGLESContext::PublishVideoSource(bool accepted,const std::shared_ptr<const VideoSourceSideData>& source) @@METHOD@@
int main() {
 CWinSystemGbmGLESContext window;
 auto a=VideoSourceSideData::Capture(1,1,AV_CODEC_ID_H264,nullptr,nullptr);
 auto b=VideoSourceSideData::Capture(1,2,AV_CODEC_ID_H264,nullptr,nullptr);
 window.PublishVideoSource(false,a); assert(!cache.accepted);
 window.PublishVideoSource(true,a); assert(cache.accepted==a);
 window.PublishVideoSource(false,b); assert(cache.accepted==a);
}
'''.replace('@@METHOD@@',code))

    def compile_run(self, program):
        helper = TREE / 'xbmc/cores/VideoSourceSideData.cpp'
        self.assertTrue(helper.exists(), 'native source snapshot producer is missing')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'test.cpp').write_text(program)
            writer=(TREE/'xbmc/utils/JSONVariantWriter.cpp').read_text()
            writer=writer.replace('"JSONVariantWriter.h"','"utils/JSONVariantWriter.h"')
            position=writer.index('{',writer.index('bool CJSONVariantWriter::Write('))+1
            writer=writer[:position]+'\n++native_json_serializations; if(native_json_barrier) native_json_barrier();\n'+writer[position:]
            writer='#include <atomic>\nstd::atomic<unsigned> native_json_serializations{};\nvoid (*native_json_barrier)() = nullptr;\n'+writer
            (root/'writer.cpp').write_text(writer)
            command = ['c++', '-std=c++20', '-pthread', '-fsanitize=address,undefined',
                       '-fno-omit-frame-pointer', '-I' + str(TREE / 'xbmc'),
                       '-I' + str(prefix / 'include'),
                       '-I' + os.environ.get('CB1_FMT_INCLUDE', '/usr/include'),
                       str(root / 'test.cpp'), str(helper),
                       str(TREE / 'xbmc/utils/Base64.cpp'),
                       str(TREE / 'xbmc/utils/Variant.cpp'),
                       str(root/'writer.cpp'),
                       '-L' + str(prefix / 'lib'), '-lavutil', '-lm', '-o', str(root / 'test')]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-6000:])
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-6000:])

    def test_fixed_formats_raw_source_and_lazy_shared_ownership(self):
        self.compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include "utils/Base64.h"
#include <nlohmann/json.hpp>
#include <cassert>
#include <thread>
#include <vector>
#include <atomic>
extern std::atomic<unsigned> native_json_serializations;
using nlohmann::json;
std::string bytes(const json& j, const char* key) {return Base64::Decode(j.at(key).get<std::string>());}
int main() {
 AVFrame* frame=av_frame_alloc(); assert(frame);
 auto* raw=av_frame_new_side_data(frame,AV_FRAME_DATA_DOVI_RPU_BUFFER,6);
 const uint8_t rpu[]={0x19,0,0,3,1,0x80}; std::memcpy(raw->data,rpu,6);
 AVDOVIDecoderConfigurationRecord config{};
 config.dv_version_major=1; config.dv_profile=8; config.dv_level=35;
 config.rpu_present_flag=config.bl_present_flag=1;
 config.dv_bl_signal_compatibility_id=1; config.dv_md_compression=2;
 AVMasteringDisplayMetadata mastering{}; mastering.has_primaries=mastering.has_luminance=1;
 mastering.display_primaries[0][0]={1,2}; mastering.display_primaries[0][1]={1,4};
 mastering.display_primaries[1][0]={1,5}; mastering.display_primaries[1][1]={1,10};
 mastering.display_primaries[2][0]={3,5}; mastering.display_primaries[2][1]={3,10};
 mastering.white_point[0]={1,4}; mastering.white_point[1]={1,2};
 mastering.max_luminance={1000,1}; mastering.min_luminance={1,10000};
 AVContentLightMetadata light{1000,400};
 auto snapshot=VideoSourceSideData::Capture(7,9,AV_CODEC_ID_HEVC,frame,&config,&mastering,&light);
 assert(snapshot && snapshot->Generation()==7 && snapshot->Serial()==9 && !snapshot->RejectedSections());
 std::memset(raw->data,0xff,raw->size); av_frame_free(&frame);
 std::vector<std::thread> readers;
 const std::string* address=&snapshot->JSON();
 for(int i=0;i<16;++i) readers.emplace_back([&]{for(int n=0;n<100;++n) assert(&snapshot->JSON()==address);});
 for(auto& thread:readers) thread.join();
 assert(native_json_serializations==1);
 const auto j=json::parse(*address);
 const auto conf=bytes(j,"dovi.config"); assert(conf.size()==24);
 const uint8_t expected[]={1,0,0x11,0x1d,0x18}; assert(!std::memcmp(conf.data(),expected,5));
 for(size_t i=5;i<conf.size();++i) assert(conf[i]==0);
 assert(bytes(j,"dovi.rpu")==std::string("\x7c\x01\x19\x00\x00\x03\x01\x80",8));
 assert(bytes(j,"cll")==std::string("\x03\xe8\x01\x90",4));
 const uint8_t mdcv[]={0x27,0x10,0x13,0x88,0x75,0x30,0x3a,0x98,0x61,0xa8,0x30,0xd4,
                     0x30,0xd4,0x61,0xa8,0,0x98,0x96,0x80,0,0,0,1};
 assert(bytes(j,"mdcv")==std::string(reinterpret_cast<const char*>(mdcv),24));
 assert(!j.contains("flags") && !j.contains("structure"));
 std::weak_ptr<const VideoSourceSideData> weak=snapshot; auto held=snapshot; snapshot.reset();
 assert(!weak.expired()); held.reset(); assert(weak.expired());
 auto sdr=VideoSourceSideData::Capture(8,1,AV_CODEC_ID_H264,nullptr,nullptr);
 assert(sdr->JSON()=="{}");
 light.MaxCLL=65536; mastering.white_point[0].den=0;
 auto invalid=VideoSourceSideData::Capture(8,2,AV_CODEC_ID_HEVC,nullptr,&config,&mastering,&light);
 auto invalidJSON=json::parse(invalid->JSON());
 assert(invalidJSON.contains("dovi.config") && !invalidJSON.contains("mdcv") && !invalidJSON.contains("cll"));
 assert(invalid->RejectedSections());
 light={0,0}; auto zeros=VideoSourceSideData::Capture(8,3,AV_CODEC_ID_HEVC,nullptr,nullptr,nullptr,&light);
 assert(bytes(json::parse(zeros->JSON()),"cll")==std::string(4,'\0'));
 frame=av_frame_alloc(); raw=av_frame_new_side_data(frame,AV_FRAME_DATA_DOVI_RPU_BUFFER,1024*1024+1);
 auto tooBig=VideoSourceSideData::Capture(8,4,AV_CODEC_ID_HEVC,frame,nullptr,nullptr,&light);
 assert(!json::parse(tooBig->JSON()).contains("dovi.rpu") && json::parse(tooBig->JSON()).contains("cll"));
 av_frame_free(&frame);
 frame=av_frame_alloc(); raw=av_frame_new_side_data(frame,AV_FRAME_DATA_DOVI_RPU_BUFFER,9);
 const uint8_t av1[]={0xb5,0,0x3b,0,0,8,0,0x19,0x80}; std::memcpy(raw->data,av1,9);
 auto obu=VideoSourceSideData::Capture(8,5,AV_CODEC_ID_AV1,frame,nullptr);
 assert(bytes(json::parse(obu->JSON()),"dovi.rpu")==std::string(reinterpret_cast<const char*>(av1),9));
 av_frame_free(&frame);
}
''')

    def test_hdr10plus_native_serializer_and_unsupported_forms(self):
        self.compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include "utils/Base64.h"
#include <nlohmann/json.hpp>
#include <cassert>
using nlohmann::json;
int main() {
 AVFrame* frame=av_frame_alloc();
 auto* hdr=av_dynamic_hdr_plus_create_side_data(frame); assert(hdr);
 hdr->application_version=1; hdr->num_windows=1;
 hdr->targeted_system_display_maximum_luminance={1000,1};
 auto& p=hdr->params[0];
 for(auto& max:p.maxscl) max={50000,100000};
 p.average_maxrgb={30000,100000}; p.fraction_bright_pixels={5,1000};
 p.num_distribution_maxrgb_percentiles=1;
 p.distribution_maxrgb[0].percentage=99; p.distribution_maxrgb[0].percentile={70000,100000};
 p.tone_mapping_flag=1; p.knee_point_x={123,4095}; p.knee_point_y={456,4095};
 p.num_bezier_curve_anchors=1; p.bezier_curve_anchors[0]={543,1023};
 auto snapshot=VideoSourceSideData::Capture(1,1,AV_CODEC_ID_HEVC,frame,nullptr);
 const auto j=json::parse(snapshot->JSON()); assert(j.contains("hdr10plus"));
 const auto bytes=Base64::Decode(j.at("hdr10plus").get<std::string>());
 assert(bytes.size()>8 && !std::memcmp(bytes.data(),"\xb5\x00\x3c\x00\x01\x04",6));
 AVDynamicHDRPlus decoded{};
 assert(av_dynamic_hdr_plus_from_t35(&decoded,reinterpret_cast<const uint8_t*>(bytes.data())+6,bytes.size()-6)==0);
 assert(decoded.application_version==1 && decoded.params[0].num_bezier_curve_anchors==1);
 assert(decoded.params[0].distribution_maxrgb[0].percentile.num==70000);
 assert(decoded.params[0].knee_point_x.num==123 && decoded.params[0].bezier_curve_anchors[0].num==543);
 hdr->num_windows=4;
 auto invalid=VideoSourceSideData::Capture(1,2,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(!json::parse(invalid->JSON()).contains("hdr10plus") && invalid->RejectedSections());
 hdr->num_windows=1; hdr->application_version=0;
 auto unsupported=VideoSourceSideData::Capture(1,3,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(!json::parse(unsupported->JSON()).contains("hdr10plus"));
 av_frame_free(&frame);
}
''')

    def test_actual_cache_rejects_late_frames_and_clears_source_on_epoch(self):
        text = (TREE / 'xbmc/cores/DataCacheCore.cpp').read_text()
        signatures = (
            'uint64_t CDataCacheCore::ResetVideoProcessingInfo()',
            'uint64_t CDataCacheCore::GetVideoProcessingGeneration()',
            'bool CDataCacheCore::SetVideoSourceSideData(',
            'std::string CDataCacheCore::GetVideoSourceSideData()')
        methods=[]
        for signature in signatures:
            self.assertIn(signature, text, 'native accepted source cache method is missing')
            start=text.index(signature); brace=text.index('{', start)
            methods.append(text[start:brace]+body(text,signature))
        self.compile_run(r'''
#include "cores/VideoSourceSideData.h"
#include "cores/VideoProcessingInfo.h"
#include <cassert>
#include <mutex>
#include <thread>
#include <condition_variable>
extern void (*native_json_barrier)();
std::mutex barrierMutex; std::condition_variable barrierCV;
bool barrierEntered=false,barrierReleased=false;
void serializeBarrier() {
 std::unique_lock lock(barrierMutex); barrierEntered=true; barrierCV.notify_all();
 barrierCV.wait(lock,[]{return barrierReleased;});
}
struct CDataCacheCore {
 std::mutex m_videoPlayerSection;
 VideoProcessingInfo m_videoProcessingInfo;
 std::shared_ptr<const VideoSourceSideData> m_videoSourceSideData;
 uint64_t m_videoProcessingGeneration{}; bool m_hasAVInfoChanges{};
 uint64_t ResetVideoProcessingInfo(); uint64_t GetVideoProcessingGeneration();
 bool SetVideoSourceSideData(uint64_t generation,std::shared_ptr<const VideoSourceSideData> source);
 std::string GetVideoSourceSideData();
};
METHODS
int main() {
 CDataCacheCore cache; const auto generation=cache.ResetVideoProcessingInfo();
 assert(cache.GetVideoSourceSideData().empty());
 AVContentLightMetadata light{1000,400};
 auto a=VideoSourceSideData::Capture(generation,1,AV_CODEC_ID_HEVC,nullptr,nullptr,nullptr,&light);
 auto b=VideoSourceSideData::Capture(generation,2,AV_CODEC_ID_H264,nullptr,nullptr);
 assert(cache.SetVideoSourceSideData(generation,a));
 const auto first=cache.GetVideoSourceSideData(); assert(first.find("cll")!=std::string::npos);
 assert(cache.SetVideoSourceSideData(generation,b)); assert(cache.GetVideoSourceSideData()=="{}");
 assert(!cache.SetVideoSourceSideData(generation,a));
 const auto next=cache.ResetVideoProcessingInfo(); assert(next!=generation);
 assert(cache.GetVideoSourceSideData().empty());
 assert(!cache.SetVideoSourceSideData(next,a)); assert(!cache.SetVideoSourceSideData(generation,b));
 auto blocked=VideoSourceSideData::Capture(next,3,AV_CODEC_ID_HEVC,nullptr,nullptr,nullptr,&light);
 assert(cache.SetVideoSourceSideData(next,blocked)); native_json_barrier=serializeBarrier;
 std::string stale;
 std::thread blockedReader([&]{stale=cache.GetVideoSourceSideData();});
 {std::unique_lock lock(barrierMutex); barrierCV.wait(lock,[]{return barrierEntered;});}
 cache.ResetVideoProcessingInfo();
 {std::unique_lock lock(barrierMutex); barrierReleased=true; barrierCV.notify_all();}
 blockedReader.join(); native_json_barrier=nullptr;
 assert(stale.empty() && cache.GetVideoSourceSideData().empty());
 for(int i=0;i<1000;++i) {
  auto current=cache.GetVideoProcessingGeneration();
  auto snapshot=VideoSourceSideData::Capture(current,i+1,AV_CODEC_ID_HEVC,nullptr,nullptr,nullptr,&light);
  assert(cache.SetVideoSourceSideData(current,snapshot));
  std::thread reader([&]{cache.GetVideoSourceSideData();}); cache.ResetVideoProcessingInfo(); reader.join();
  assert(cache.GetVideoSourceSideData().empty());
 }
}
'''.replace('METHODS','\n'.join(methods)))


if __name__ == '__main__':
    unittest.main()
