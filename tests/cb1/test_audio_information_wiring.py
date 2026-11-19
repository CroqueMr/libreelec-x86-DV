"""Run native cache/selected-source/sink contracts with only OS boundaries doubled."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AudioInformationWiring(unittest.TestCase):
    def run_cpp(self, code):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root/'check.cpp'
            source.write_text(code)
            result = subprocess.run(['c++', '-std=c++20', '-pthread', '-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'), str(source), '-o', str(root/'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-5000:])
            result = subprocess.run([str(root/'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-5000:])

    def test_native_audio_reset_clears_same_codec_track_metadata(self):
        native = (TREE/'xbmc/cores/DataCacheCore.cpp').read_text()
        try:
            set_source = body(native, 'void CDataCacheCore::SetAudioSourceInfo(')
            get_source = body(native, 'AE::AudioSourceInfo CDataCacheCore::GetAudioSourceInfo(')
        except ValueError:
            self.fail('Native audio-source cache contract is not implemented')
        code = r'''
#include "cores/AudioEngine/Utils/AEAudioSourceInfo.h"
#include <cassert>
#include <mutex>
struct CDataCacheCore {
 std::recursive_mutex m_audioPlayerSection;
 bool m_hasAVInfoChanges=false;
 struct Audio {AE::AudioSourceInfo source;} m_playerAudioInfo;
 void SetAudioSourceInfo(const AE::AudioSourceInfo& source) SET
 AE::AudioSourceInfo GetAudioSourceInfo() GET
 void ResetAudioCache() RESET
};
int main(){
 CDataCacheCore cache; AE::AudioSourceInfo a;
 a.valid=true;a.codec=86060;a.uniqueId=4;a.demuxerId=9;a.objects=11;a.dialnorm=-27;
 cache.SetAudioSourceInfo(a);assert(cache.GetAudioSourceInfo().objects==11);
 cache.ResetAudioCache();auto empty=cache.GetAudioSourceInfo();
 assert(!empty.valid && empty.objects==-1 && !empty.dialnorm);
 AE::AudioSourceInfo b;b.valid=true;b.codec=a.codec;b.uniqueId=5;b.demuxerId=9;
 cache.SetAudioSourceInfo(b);assert(cache.GetAudioSourceInfo().objects==-1);
 cache.SetAudioSourceInfo({});assert(!cache.GetAudioSourceInfo().valid);
}
'''.replace(' SET', set_source).replace(' GET', get_source).replace(' RESET', body(native, 'void CDataCacheCore::ResetAudioCache('))
        self.run_cpp(code)

    def test_selected_audio_stream_never_takes_metadata_from_another_track(self):
        native = body((TREE/'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text(),
                      'void CVideoPlayer::GetAudioStreamInfo(')
        code = r'''
#include "cores/AudioEngine/Utils/AEAudioSourceInfo.h"
#include <cassert>
#include <mutex>
#include <string>
#include <vector>
constexpr int CURRENT_STREAM=-1;
enum class StreamType{NONE,AUDIO};
struct AudioStreamInfo {bool valid=false;std::string language,name,codecName,codecDesc;
 int bitrate=0,channels=0,samplerate=0,bitspersample=0,flags=0;AE::AudioSourceInfo source;};
struct SelectionStream {StreamType type=StreamType::AUDIO;std::string language,name,codec,codecDesc;
 int bitrate=0,channels=0,samplerate=0,bitspersample=0,flags=0,profile=-99,codecId=1,id=4;
 int64_t demuxerId=9;uint64_t channellayout=0;AE::AudioSourceInfo audioSource;};
struct Cache {AE::AudioSourceInfo current;auto GetAudioSourceInfo(){return current;}} cache;
struct CServiceBroker {static Cache& GetDataCacheCore(){return cache;}};
struct Selections {std::vector<SelectionStream> streams;const auto& Get(StreamType,int index)const{return streams[index];}};
struct CVideoPlayer {struct Content{mutable std::recursive_mutex m_section;int m_audioIndex=0;Selections m_selectionStreams;}m_content;
 struct Current{int id=4;int64_t demuxerId=9;}m_currentAudio;
 int GetAudioStreamCount()const{return m_content.m_selectionStreams.streams.size();}
 void GetAudioStreamInfo(int index,AudioStreamInfo& info)const BODY
};
int main(){
 CVideoPlayer player;SelectionStream stream;stream.channels=8;stream.samplerate=48000;
 stream.bitspersample=24;stream.channellayout=0x63f;
 stream.id=128; // navigation id differs from the underlying demux source id
 stream.audioSource.valid=true;stream.audioSource.uniqueId=4;stream.audioSource.demuxerId=9;
 stream.audioSource.codec=1;stream.audioSource.sampleRate=48000;stream.audioSource.bitsPerSample=24;
 player.m_content.m_selectionStreams.streams={stream,stream};
 auto& accepted=cache.current;accepted.valid=true;accepted.uniqueId=4;accepted.demuxerId=9;
 accepted.codec=1;
 accepted.channels=8;accepted.sampleRate=48000;accepted.bitsPerSample=24;accepted.objects=11;
 AudioStreamInfo info;player.GetAudioStreamInfo(CURRENT_STREAM,info);
 assert(info.valid && info.samplerate==48000 && info.bitspersample==24 && info.source.objects==11);
 accepted.uniqueId=5;player.GetAudioStreamInfo(CURRENT_STREAM,info);assert(info.source.objects==-1);
 accepted.uniqueId=4;accepted.demuxerId=10;player.GetAudioStreamInfo(CURRENT_STREAM,info);assert(info.source.objects==-1);
 accepted.demuxerId=9;player.GetAudioStreamInfo(1,info);assert(info.source.objects==-1);
 player.GetAudioStreamInfo(99,info);assert(!info.valid && !info.source.valid);
 player.m_content.m_audioIndex=-1;player.GetAudioStreamInfo(CURRENT_STREAM,info);assert(!info.valid);
}
'''.replace('BODY', native)
        self.run_cpp(code)

    def test_sink_format_and_transport_are_one_atomic_native_snapshot(self):
        native = (TREE/'xbmc/cores/AudioEngine/Engines/ActiveAE/ActiveAE.cpp').read_text()
        try:
            snapshot = body(native, 'AE::SinkInfo CEngineStats::GetCurrentSinkInfo(')
        except ValueError:
            self.fail('Atomic native sink information is not implemented')
        setter = body(native, 'void CEngineStats::SetCurrentSinkFormat(')
        code = r'''
#include <cassert>
#include <atomic>
#include <mutex>
#include <thread>
struct AEAudioFormat{int tag=0;};
namespace AE{enum class SinkMode{Unknown,PCM,Passthrough,Transcoded};
 struct SinkInfo{AEAudioFormat format;SinkMode mode=SinkMode::Unknown;};}
struct CEngineStats{std::mutex m_lock;AEAudioFormat m_sinkFormat;AE::SinkMode m_sinkMode=AE::SinkMode::Unknown;
 void SetCurrentSinkFormat(const AEAudioFormat& SinkFormat, AE::SinkMode mode=AE::SinkMode::Unknown) SET
 AE::SinkInfo GetCurrentSinkInfo() GET
};
int main(){
 CEngineStats stats;assert(stats.GetCurrentSinkInfo().mode==AE::SinkMode::Unknown);
 stats.SetCurrentSinkFormat({48},AE::SinkMode::PCM);
 std::atomic<bool> done=false;
 std::thread producer([&]{for(int n=0;n<5000;++n){stats.SetCurrentSinkFormat({192},AE::SinkMode::Passthrough);stats.SetCurrentSinkFormat({48},AE::SinkMode::PCM);}done=true;});
 while(!done){auto s=stats.GetCurrentSinkInfo();assert((s.format.tag==48 && s.mode==AE::SinkMode::PCM)||(s.format.tag==192 && s.mode==AE::SinkMode::Passthrough));}
 producer.join();stats.SetCurrentSinkFormat({});assert(stats.GetCurrentSinkInfo().mode==AE::SinkMode::Unknown);
}
'''.replace(' SET',setter).replace(' GET',snapshot)
        self.run_cpp(code)
