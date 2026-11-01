"""Execute native sink configure/unconfigure failure branches with protocol boundaries doubled."""
from pathlib import Path
import unittest
from test_native_video_source import TREE, body
import test_audio_information_wiring as wiring


class AudioSinkLifecycle(unittest.TestCase):
    run_cpp = wiring.AudioInformationWiring.run_cpp
    def test_disconnect_and_failed_configuration_hide_the_previous_output(self):
        native = (TREE/'xbmc/cores/AudioEngine/Engines/ActiveAE/ActiveAE.cpp').read_text()
        try:
            invalid = body(native, 'void CEngineStats::InvalidateCurrentSinkInfo(')
        except ValueError:
            self.fail('Native output report is not invalidated during sink teardown')
        code = r'''
#include <cassert>
#include <chrono>
#include <mutex>
#include <string>
using namespace std::chrono_literals;
constexpr int AE_FMT_RAW=1,AE_FMT_INVALID=-1,MODE_RAW=1,MODE_TRANSCODE=2,LOGERROR=0;
struct AEAudioFormat {int m_dataFormat=0;};
namespace AE{enum class SinkMode{Unknown,PCM,Passthrough,Transcoded};struct SinkInfo{AEAudioFormat format;SinkMode mode=SinkMode::Unknown;};}
struct CLog {template<class... T>static void Log(T...){}};
struct AESinkDevice{std::string driver="ALSA",name="HDMI";};
struct CAESinkFactory{static AESinkDevice ParseDevice(const std::string&){return {};}};
struct CEngineStats{std::mutex m_lock;AEAudioFormat m_sinkFormat;AE::SinkMode m_sinkMode=AE::SinkMode::Unknown;
 void SetCurrentSinkFormat(const AEAudioFormat& SinkFormat,AE::SinkMode mode=AE::SinkMode::Unknown) SET
 AE::SinkInfo GetCurrentSinkInfo() GET
 void InvalidateCurrentSinkInfo() INVALID
 void SetSinkCacheTotal(double){}void SetSinkLatency(double){}void SetSinkNeedIec(bool){}
};
struct SinkConfig{AEAudioFormat format;CEngineStats* stats;std::string* device;};
struct SinkReply{AEAudioFormat format;std::string* device=nullptr;bool hasVolume=false;double cacheTotal=0,latency=0;};
struct Message{int signal=0;void* data=nullptr;void Release(){}};
struct CSinkControlProtocol{enum{SETNOISETYPE,SETSILENCETIMEOUT,CONFIGURE,UNCONFIGURE,ACC};};
struct Port{bool timeout=false;Message reply;
 template<class... T>void SendOutMessage(T...){}
 template<class... T>bool SendOutMessageSync(int,Message** value,T...){*value=&reply;return !timeout;}};
struct Sink{Port m_controlPort;bool NeedIecPack(){return true;}};
struct Event{void Reset(){}};
struct CActiveAE{Sink m_sink;CEngineStats m_stats;AEAudioFormat m_sinkRequestFormat,m_sinkFormat;
 struct Settings{std::string passthroughdevice="HDMI",device="HDMI";bool streamNoise=false;int silenceTimeoutMinutes=0;}m_settings;
 bool m_extError=false,m_sinkHasVolume=false,m_currentDeviceFollowsDefault=true;
 int m_mode=MODE_RAW;std::string m_openedDriver,m_openedDevice,m_currDevice;Event m_inMsgEvent;
 bool InitSink() INIT
 void UnconfigureSink() UNCONFIGURE
 bool GetCurrentSinkInfo(AE::SinkInfo& info) SNAPSHOT
};
int main(){
 CActiveAE engine;SinkReply data;data.format.m_dataFormat=AE_FMT_RAW;
 auto& port=engine.m_sink.m_controlPort;
 AE::SinkInfo report;
 const auto success=[&]{port.timeout=false;port.reply.signal=CSinkControlProtocol::ACC;port.reply.data=&data;assert(engine.InitSink());assert(engine.GetCurrentSinkInfo(report));assert(report.mode==AE::SinkMode::Passthrough);};
 success();engine.UnconfigureSink();assert(!engine.GetCurrentSinkInfo(report));
 success();port.reply.signal=-1;assert(!engine.InitSink());assert(!engine.GetCurrentSinkInfo(report));
 success();port.timeout=true;assert(!engine.InitSink());assert(!engine.GetCurrentSinkInfo(report));
 success();port.reply.data=nullptr;engine.InitSink();assert(!engine.GetCurrentSinkInfo(report));
 success();port.timeout=true;engine.UnconfigureSink();assert(!engine.GetCurrentSinkInfo(report));
 // Reporting invalidation never changes the retained legacy format used by timing.
 assert(engine.m_stats.m_sinkFormat.m_dataFormat==AE_FMT_RAW);
}
'''
        for token, signature in [(' SET','void CEngineStats::SetCurrentSinkFormat('),
                                 (' GET','AE::SinkInfo CEngineStats::GetCurrentSinkInfo('),
                                 (' INVALID','void CEngineStats::InvalidateCurrentSinkInfo('),
                                 (' INIT','bool CActiveAE::InitSink('),
                                 (' UNCONFIGURE','void CActiveAE::UnconfigureSink('),
                                 (' SNAPSHOT','bool CActiveAE::GetCurrentSinkInfo(')]:
            code = code.replace(token, body(native,signature))
        self.run_cpp(code)
