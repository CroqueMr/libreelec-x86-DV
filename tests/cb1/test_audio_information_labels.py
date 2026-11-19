"""Run the native InfoLabel cases against distinct source and sink states."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AudioInformationLabels(unittest.TestCase):
    def test_native_labels_distinguish_source_pcm_raw_core_and_transcode(self):
        text = (TREE/'xbmc/guilib/guiinfo/PlayerGUIInfo.cpp').read_text()
        try:
            start = text.index('    case PLAYER_PROCESS_AUDIOSOURCETITLE:')
        except ValueError:
            self.fail('Native source/output audio InfoLabels are not implemented')
        branch = text[start:text.index('    case PLAYER_PROCESS_AUDIODECODER:', start)]
        names = ['AUDIOSOURCETITLE','AUDIOSOURCEFORMAT','AUDIOSOURCECHANNELS','AUDIOBEDOBJECTSLABEL',
                 'AUDIOBEDOBJECTS','AUDIOPRESENTATION','AUDIODIALNORM','AUDIOSOURCELANGUAGE',
                 'AUDIOSOURCEBITRATE','AUDIOOUTPUTTRANSPORT','AUDIOOUTPUTCODEC','AUDIOOUTPUTDATA','AUDIOOUTPUTCHANNELS']
        ids = '\n'.join('constexpr int PLAYER_PROCESS_'+name+'='+str(n)+';' for n,name in enumerate(names))
        util = (TREE/'xbmc/cores/AudioEngine/Utils/AEUtil.cpp').read_text()
        code = r'''
#include "cores/AudioEngine/Utils/AEAudioSourceInfo.h"
#include "cores/AudioEngine/Utils/AEChannelData.h"
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/channel_layout.h>
}
#include <cassert>
#include <memory>
#include <string>
#include <fmt/format.h>
IDS
constexpr int CURRENT_STREAM=-1,FLAG_COMMENT=8,FLAG_VISUAL_IMPAIRED=256;
struct Language {std::string value="English";std::string GetEnglishName()const{return value;}};
struct AudioStreamInfo{bool valid=true;AE::AudioSourceInfo source;Language language;int bitrate=0,flags=0;};
struct CAEChannelInfo {uint64_t mask=AV_CH_LAYOUT_STEREO;unsigned count=2;unsigned Count()const{return count;}};
struct CAEStreamInfo{enum DataType{STREAM_TYPE_NULL,STREAM_TYPE_AC3,STREAM_TYPE_DTS_512,STREAM_TYPE_DTS_1024,STREAM_TYPE_DTS_2048,STREAM_TYPE_DTSHD,STREAM_TYPE_DTSHD_CORE,STREAM_TYPE_EAC3,STREAM_TYPE_MLP,STREAM_TYPE_TRUEHD,STREAM_TYPE_DTSHD_MA};
 DataType m_type=STREAM_TYPE_NULL;};
struct AEAudioFormat{AEDataFormat m_dataFormat=AE_FMT_S24NE4;unsigned m_sampleRate=48000;CAEChannelInfo m_channelLayout;CAEStreamInfo m_streamInfo;};
namespace AE{enum class SinkMode{Unknown,PCM,Passthrough,Transcoded};struct SinkInfo{AEAudioFormat format;SinkMode mode=SinkMode::Unknown;};}
struct CAEUtil {
 static unsigned DataFormatToBits(AEDataFormat dataFormat) BITS
 static unsigned DataFormatToUsedBits(AEDataFormat dataFormat) USED
 static uint64_t GetAVChannelLayout(const CAEChannelInfo& channels){return channels.mask;}
};
struct StringUtils {template<typename... T>static std::string Format(fmt::format_string<T...> pattern,T&&... args){return fmt::format(pattern,std::forward<T>(args)...);}};
AudioStreamInfo selected;
struct App {bool hasAudio=true,playing=true;bool HasAudio()const{return hasAudio;}bool IsPlaying()const{return playing;}
 void GetAudioStreamInfo(int index,AudioStreamInfo& info){assert(index==CURRENT_STREAM);info=selected;}};
struct Engine {AE::SinkInfo current;bool GetCurrentSinkInfo(AE::SinkInfo& value){value=current;return current.mode!=AE::SinkMode::Unknown && current.format.m_dataFormat!=AE_FMT_INVALID;}} engine;
struct Cache{AE::AudioSourceInfo source;int bitrate=0;auto GetAudioSourceInfo(){return source;}int GetAudioLiveBitRate(){return bitrate;}}cache;
struct CServiceBroker{static Engine* GetActiveAE(){return &engine;}static Cache& GetDataCacheCore(){return cache;}};
struct Info {int id;int GetInfo()const{return id;}};
struct Provider{std::shared_ptr<App> m_appPlayer=std::make_shared<App>();
 bool get(Info info,std::string& value){switch(info.GetInfo()){BRANCH default:return false;}return false;}
 std::string label(int id){std::string value;if(!get({id},value))return {};return value;}};
int main(){
 Provider p;auto& s=selected.source;s.valid=true;s.codec=AV_CODEC_ID_TRUEHD;s.profile=AV_PROFILE_TRUEHD_ATMOS;
 s.uniqueId=4;s.demuxerId=9;s.channels=8;s.channelMask=AV_CH_LAYOUT_7POINT1;s.bitsPerSample=24;s.sampleRate=48000;
 s.bedChannels=6;s.objects=11;s.presentation=16;s.dialnorm=-27;
 cache.source=s;cache.bitrate=4200000;
 assert(p.label(PLAYER_PROCESS_AUDIOSOURCETITLE)=="TrueHD Atmos");
 assert(p.label(PLAYER_PROCESS_AUDIOSOURCEFORMAT)=="24-bit / 48 kHz");
 assert(p.label(PLAYER_PROCESS_AUDIOSOURCECHANNELS)=="7.1");
 assert(p.label(PLAYER_PROCESS_AUDIOBEDOBJECTS)=="6 / 11");
 assert(p.label(PLAYER_PROCESS_AUDIOPRESENTATION)=="16 elements");
 assert(p.label(PLAYER_PROCESS_AUDIODIALNORM)=="-27 LKFS");
 assert(p.label(PLAYER_PROCESS_AUDIOSOURCELANGUAGE)=="English");
 assert(p.label(PLAYER_PROCESS_AUDIOSOURCEBITRATE)=="4.2 Mb/s");
 engine.current.mode=AE::SinkMode::Passthrough;engine.current.format.m_sampleRate=192000;
 engine.current.format.m_channelLayout={0,8};engine.current.format.m_streamInfo.m_type=CAEStreamInfo::STREAM_TYPE_TRUEHD;
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTTRANSPORT)=="Passthrough");
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTDATA)=="RAW");
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTCHANNELS).empty());
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTCODEC).empty());
 engine.current.mode=AE::SinkMode::PCM;engine.current.format.m_sampleRate=48000;
 engine.current.format.m_channelLayout={AV_CH_LAYOUT_STEREO,2};
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTTRANSPORT)=="PCM decoded");
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTDATA)=="24-bit / 48 kHz");
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTCHANNELS)=="stereo");
 assert(p.label(PLAYER_PROCESS_AUDIOSOURCETITLE)=="TrueHD Atmos");
 s.codec=AV_CODEC_ID_PCM_S24LE;assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTTRANSPORT)=="Native PCM");
 s.codec=AV_CODEC_ID_AAC;engine.current.mode=AE::SinkMode::Transcoded;
 engine.current.format.m_streamInfo.m_type=CAEStreamInfo::STREAM_TYPE_AC3;
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTTRANSPORT)=="Transcoded");
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTCODEC)=="Dolby Digital");
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTDATA)=="RAW");
 s.codec=AV_CODEC_ID_DTS;s.profile=AV_PROFILE_DTS_HD_MA;
 engine.current.mode=AE::SinkMode::Passthrough;engine.current.format.m_streamInfo.m_type=CAEStreamInfo::STREAM_TYPE_DTSHD_CORE;
 assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTCODEC)=="DTS core");
 engine.current.mode=AE::SinkMode::Unknown;assert(p.label(PLAYER_PROCESS_AUDIOOUTPUTTRANSPORT).empty());
 s.objects=-1;s.bedChannels=-1;s.presentation=-1;s.dialnorm.reset();
 assert(p.label(PLAYER_PROCESS_AUDIOBEDOBJECTS).empty() && p.label(PLAYER_PROCESS_AUDIODIALNORM).empty());
 cache.source.uniqueId=7;selected.bitrate=800000;
 assert(p.label(PLAYER_PROCESS_AUDIOSOURCEBITRATE)=="800 Kb/s (stream)");
 selected.flags=FLAG_COMMENT;assert(p.label(PLAYER_PROCESS_AUDIOSOURCELANGUAGE)=="English (commentary)");
 p.m_appPlayer->hasAudio=false;
 for(int id=0;id<13;++id)assert(p.label(id).empty());
}
'''.replace('IDS',ids).replace('BRANCH',branch).replace('BITS',body(util,'unsigned int CAEUtil::DataFormatToBits(')).replace('USED',body(util,'unsigned int CAEUtil::DataFormatToUsedBits('))
        prefix=Path(os.environ.get('FFMPEG_AUDIO_TEST_PREFIX',os.environ['FFMPEG_TEST_PREFIX']))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'check.cpp').write_text(code)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined','-I'+str(TREE/'xbmc'),
                '-I'+str(prefix/'include'),str(root/'check.cpp'),
                str(TREE/'xbmc/cores/AudioEngine/Utils/AEAudioSourceInfo.cpp'),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lfmt','-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr[-6000:])
            run=subprocess.run([str(root/'check')],env=dict(os.environ,LD_LIBRARY_PATH=str(prefix/'lib')),capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr[-5000:])
