"""Log native audio admission facts without changing the selected codec."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class AudioPassthroughDiagnostics(unittest.TestCase):
    def test_selection_logs_settings_and_keeps_native_codec_decisions(self):
        relative = 'xbmc/cores/VideoPlayer/DVDCodecs/DVDFactoryCodec.cpp'
        native = (TREE/relative).read_text()
        candidate = Path(os.environ.get('CB1_AUDIO_NATIVE_SOURCE', TREE/relative)).read_text()
        signature = 'std::unique_ptr<CDVDAudioCodec> CDVDFactoryCodec::CreateAudioCodec('
        program = r'''
#include <cassert>
#include <map>
#include <memory>
#include <string>
#include <utility>
#include <vector>
#include <fmt/format.h>
constexpr int LOGINFO=1;
struct CLog {
 static inline std::vector<std::string> lines;
 template<class... T> static void Log(int, const char* text, T... args) {
   lines.push_back(fmt::vformat(text, fmt::make_format_args(args...)));
 }
};
struct CSettings {
 static constexpr const char *SETTING_AUDIOOUTPUT_PASSTHROUGH="enabled",
 *SETTING_VIDEOPLAYER_USEDISPLAYASCLOCK="sync",
 *SETTING_AUDIOOUTPUT_CONFIG="config", *SETTING_AUDIOOUTPUT_AUDIODEVICE="pcm",
 *SETTING_AUDIOOUTPUT_PASSTHROUGHDEVICE="pt", *SETTING_AUDIOOUTPUT_AC3PASSTHROUGH="ac3",
 *SETTING_AUDIOOUTPUT_EAC3PASSTHROUGH="eac3", *SETTING_AUDIOOUTPUT_DTSPASSTHROUGH="dts",
 *SETTING_AUDIOOUTPUT_DTSHDPASSTHROUGH="dtshd", *SETTING_AUDIOOUTPUT_TRUEHDPASSTHROUGH="truehd";
 std::map<std::string,bool> flags;
 int output=0;
 bool GetBool(const char* key) const {return flags.at(key);}
 int GetInt(const char*) const {return output;}
 std::string GetString(const char* key) const {return std::string(key)=="pcm"?"ALSA:default":"ALSA:hdmi:CARD=PCH,DEV=0";}
};
struct Component {
 std::shared_ptr<CSettings> settings=std::make_shared<CSettings>();
 auto GetSettings(){return settings;}
};
struct CServiceBroker {static inline Component component;static auto* GetSettingsComponent(){return &component;}};
struct CProcessInfo {bool realtime=false;bool IsRealtimeStream()const{return realtime;}};
struct CDVDStreamInfo {int codec=86020,profile=60,samplerate=48000;};
struct CAEStreamInfo {enum DataType {STREAM_TYPE_NULL=0,STREAM_TYPE_DTSHD_CORE=1,STREAM_TYPE_TRUEHD=2};};
struct CDVDCodecOptions {std::vector<std::pair<std::string,std::string>> m_keys;};
struct StringUtils {static std::string SizeToString(int n){return std::to_string(n);}};
bool ptOpens=true,pcmOpens=true;
struct CDVDAudioCodec {
 bool passthrough=false;
 virtual ~CDVDAudioCodec()=default;
 bool NeedPassthrough()const{return passthrough;}
 virtual bool Open(CDVDStreamInfo&,CDVDCodecOptions&){return pcmOpens;}
};
struct CDVDAudioCodecFFmpeg:CDVDAudioCodec {explicit CDVDAudioCodecFFmpeg(CProcessInfo&) {}};
struct CDVDAudioCodecPassthrough:CDVDAudioCodec {
 CDVDAudioCodecPassthrough(CProcessInfo&,CAEStreamInfo::DataType){passthrough=true;}
 bool Open(CDVDStreamInfo&,CDVDCodecOptions&)override{return ptOpens;}
};
struct CDVDFactoryCodec {
 static inline std::map<std::string,int> m_hwAudioCodecs;
 static auto CreateAudioCodecHW(const std::string&, CProcessInfo&){return std::make_unique<CDVDAudioCodec>();}
 static std::unique_ptr<CDVDAudioCodec> CreateAudioCodec(CDVDStreamInfo& hint,CProcessInfo& processInfo,
    bool allowpassthrough,bool allowdtshddecode,CAEStreamInfo::DataType ptStreamType) @CANDIDATE@
 static std::unique_ptr<CDVDAudioCodec> Baseline(CDVDStreamInfo& hint,CProcessInfo& processInfo,
    bool allowpassthrough,bool allowdtshddecode,CAEStreamInfo::DataType ptStreamType) @BASELINE@
};
int main() {
 auto& settings=*CServiceBroker::component.settings;
 struct Case {bool enabled,sync,realtime,allow;int config;CAEStreamInfo::DataType type;bool ptOpen,pcmOpen,hw;int expected;};
 const Case cases[]={
   {false,false,false,true,0,CAEStreamInfo::STREAM_TYPE_NULL,true,true,false,0},
   {true,true,false,false,0,CAEStreamInfo::STREAM_TYPE_TRUEHD,true,true,false,0},
   {true,false,true,false,0,CAEStreamInfo::STREAM_TYPE_TRUEHD,true,true,false,0},
   {true,false,false,true,2,CAEStreamInfo::STREAM_TYPE_NULL,true,true,false,0},
   {true,false,false,true,0,CAEStreamInfo::STREAM_TYPE_NULL,true,true,false,0},
   {true,false,false,true,0,CAEStreamInfo::STREAM_TYPE_TRUEHD,true,true,false,1},
   {true,false,false,true,0,CAEStreamInfo::STREAM_TYPE_DTSHD_CORE,true,true,false,1},
   {true,false,false,true,0,CAEStreamInfo::STREAM_TYPE_TRUEHD,false,true,false,0},
   {true,false,false,true,0,CAEStreamInfo::STREAM_TYPE_TRUEHD,false,false,false,-1},
   {true,false,false,true,0,CAEStreamInfo::STREAM_TYPE_TRUEHD,true,true,true,0},
 };
 for (const auto& c:cases) {
   settings.flags={{"enabled",c.enabled},{"sync",c.sync},{"ac3",true},{"eac3",false},
                   {"dts",true},{"dtshd",false},{"truehd",true}};
   settings.output=c.config;const auto before=settings.flags;
   CProcessInfo process{c.realtime};CDVDStreamInfo hints;
   ptOpens=c.ptOpen;pcmOpens=c.pcmOpen;
   CDVDFactoryCodec::m_hwAudioCodecs.clear();
   if(c.hw) CDVDFactoryCodec::m_hwAudioCodecs.emplace("native",1);
   CLog::lines.clear();
   auto actual=CDVDFactoryCodec::CreateAudioCodec(hints,process,c.allow,true,c.type);
   assert((actual?actual->NeedPassthrough()?1:0:-1)==c.expected);
   assert(CLog::lines.size()==1); // Removing the diagnostic must fail this test.
   const auto& line=CLog::lines[0];
   for(const auto& field:std::vector<std::string>{
       "codec=86020","profile=60","rate=48000",
       fmt::format("player_allows={}",c.allow),fmt::format("stream_type={}",int(c.type)),
       fmt::format("realtime={}",c.realtime),fmt::format("sync_display={}",c.sync),
       fmt::format("configured={}",c.enabled),fmt::format("output_config={}",c.config),
       "formats=ac3:true,eac3:false,dts:true,dtshd:false,truehd:true",
       "pcm_device=ALSA:default","passthrough_device=ALSA:hdmi:CARD=PCH,DEV=0"})
     assert(line.find(field)!=std::string::npos);
   assert(settings.flags==before && settings.output==c.config);
   auto reference=CDVDFactoryCodec::Baseline(hints,process,c.allow,true,c.type);
   assert((reference?reference->NeedPassthrough()?1:0:-1)==c.expected);
 }
}
'''.replace('@CANDIDATE@', body(candidate, signature)).replace('@BASELINE@', body(native, signature))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'check.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root/'check.cpp'), '-lfmt', '-o', str(root/'check')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root/'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout+run.stderr)
