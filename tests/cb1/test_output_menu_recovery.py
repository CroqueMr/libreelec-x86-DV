"""A disabled or failed frame must not permanently disable output preferences."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class OutputMenuRecoveryTests(unittest.TestCase):
    def test_mode_choices_recover_without_restarting_kodi(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree / 'xbmc/settings/SettingConditions.cpp').read_text()
        start = source.index('{', source.index('void CSettingConditions::DVOutputOptions('))
        depth, end = 1, start + 1
        while depth:
            depth += (source[end] == '{') - (source[end] == '}')
            end += 1
        program = r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
#include <cassert>
#include <algorithm>
#include <cmath>
#include <memory>
#include <vector>
using dvbridge_mode=int;
constexpr int DVBRIDGE_MODE_DISABLED=0, DVBRIDGE_MODE_STANDARD=1, DVBRIDGE_MODE_SDR=7;
enum class StreamHdrType {HDR_TYPE_NONE,HDR_TYPE_HDR10,HDR_TYPE_DOLBYVISION,HDR_TYPE_HLG,HDR_TYPE_HDR10PLUS};
struct CDVPlaybackModes {
 static inline StreamHdrType nativeSource=StreamHdrType::HDR_TYPE_NONE;
 static StreamHdrType SourceType(){return nativeSource;}
};
namespace DVBRIDGE {
enum class OutputMode {Standard, HDR10, Disabled};
enum class HDR10SourceMode {Native, ReferenceDV, EnhancedDV, HDR10PlusDV};
struct Preferences { OutputMode output{}; HDR10SourceMode hdr10Source{};
 double peak=1000,expertPeak=1000; int gamut=2,expertGamut=2;
 bool ProfileValid(int=0) const { return peak>0 && gamut>0; } } preferences;
Preferences FrameOutputSettings() {return preferences;}
struct Identity { bool valid{}; bool Valid() const {return valid;} };
struct Snapshot {struct {OutputCapabilities capabilities; Identity identity;} transaction;};
struct StreamTelemetry { static inline Snapshot value; static Snapshot Read() {return value;} };
}
struct Window {virtual ~Window()=default;};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext : Window {
 DVBRIDGE::OutputCapabilities available;
 DVBRIDGE::OutputCapabilities GetDVOutputCapabilities(std::nullptr_t,bool) {return available;}
};
}
KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct Localizer {std::string Get(int id) const {return std::to_string(id);}};
struct Resources { Localizer localizer; const Localizer& GetLocalizeStrings() {return localizer;} };
struct CServiceBroker {static Window* GetWinSystem() {return &window;}
 static Resources& GetResourcesComponent() {static Resources value;return value;} };
struct CSetting {std::string id="dvbridge.outputmode"; const std::string& GetId() const {return id;}};
struct IntegerSettingOption {std::string label="Standard",label2;int value{};
 std::vector<std::pair<std::string,bool>> properties;};
struct CSettingConditions {static void DVOutputOptions(const std::shared_ptr<const CSetting>& setting,
 std::vector<IntegerSettingOption>& list) BODY };
bool disabled(int value=0, const char* settingId="dvbridge.playbackchoice") {
 std::vector<IntegerSettingOption> list(1);list[0].value=value;
 auto setting=std::make_shared<CSetting>();setting->id=settingId;
 CSettingConditions::DVOutputOptions(setting,list);
 return list[0].properties.back().second;
}
int main() {
 using namespace DVBRIDGE;
 window.available.processingKnown=true;window.available.nativeDV=true;window.available.hdr10=true;
 window.available.hdr10plus=true;
 for(auto& mode:window.available.processing) mode={true,OutputReason::None};
 auto& frame=StreamTelemetry::value.transaction;
 frame.identity.valid=true;frame.capabilities=window.available;
 frame.capabilities.sourceKnown=true;frame.capabilities.isDV=true;
 std::vector<IntegerSettingOption> choices;
 for(int value:{0,4,5,2,1}) {IntegerSettingOption option;option.value=value;choices.push_back(option);}
 CSettingConditions::DVOutputOptions(std::make_shared<CSetting>(),choices);
 assert(choices.size()==5 && std::none_of(choices.begin(),choices.end(),[](auto& x){return x.value==6;}));
 // The flat settings view reuses the seven Quick Switch modes, but uses hardware
 // capabilities and permits selecting Expert before configuring its profile.
 for(int i=0;i<7;++i)assert(!disabled(i,"dvbridge.playback"));
 window.available.hdr10plus=false;
 assert(disabled(6,"dvbridge.playback"));
 assert(!disabled(4,"dvbridge.playback") && !disabled(5,"dvbridge.playback"));
 window.available.hdr10plus=true;
 preferences.peak=preferences.expertPeak=0;
 assert(!disabled(2,"dvbridge.playback") && !disabled(5,"dvbridge.playback"));
 preferences.peak=preferences.expertPeak=1000;
 assert(!disabled());
 // The current HDMI ceiling takes precedence over an earlier presented frame.
 window.available.hdr10MaxBpc=8;
 assert(disabled(4) && disabled(5) && !disabled());
 window.available.hdr10MaxBpc=10;
 assert(!disabled(4) && !disabled(5));
 // A prior failed atomic commit does not remove physically available transports.
 frame.capabilities.nativeDV=false;frame.capabilities.hdr10=false;
 assert(!disabled());
 // Disabled intentionally retains no imported DV picture. Enabling must still be possible.
 preferences.output=OutputMode::Disabled;frame.capabilities.processingKnown=false;
 assert(!disabled());
 // Real unsupported hardware and mismatched source formats stay disabled.
 window.available.nativeDV=false;assert(disabled());window.available.nativeDV=true;
 frame.capabilities.isDV=false;frame.capabilities.isHDR10=true;assert(disabled());
 frame.capabilities.isDV=true;frame.capabilities.isHDR10=false;
 window.available.processing[1]={false,OutputReason::NoGPUProcessing};assert(disabled());
 window.available.processing[1]={true,OutputReason::None};
 preferences.output=OutputMode::Standard;frame.capabilities=window.available;
 frame.capabilities.sourceKnown=true;frame.capabilities.isDV=true;
 frame.capabilities.processing[1]={false,OutputReason::SourceIneligible};
 assert(disabled());
 // HLG SDR is available on an SDR sink and uses per-picture import admission.
 window.available.nativeDV=window.available.hdr10=false;
 window.available.hdr10Processing[DVBRIDGE_MODE_SDR]={true,OutputReason::None};
 assert(!disabled(2,"dvbridge.hlgsource") && disabled(1,"dvbridge.hlgsource"));
 frame.capabilities=window.available;
 frame.capabilities.sourceKnown=frame.capabilities.isHLG=true;
 frame.capabilities.processing=window.available.hdr10Processing;
 assert(!disabled(2,"dvbridge.hlgplaybackchoice") && disabled(0,"dvbridge.hlgplaybackchoice"));
 frame.capabilities.processing[DVBRIDGE_MODE_SDR]={false,OutputReason::ActivationFailed};
 assert(disabled(2,"dvbridge.hlgplaybackchoice") && !disabled(1,"dvbridge.hlgplaybackchoice"));
 window.available.nativeDV=window.available.hdr10=true;
#ifdef CB1_HAS_HDR10_AI
 // Native HDR10 must expose AI choices before AI output has ever activated.
 preferences={};
 for(auto& mode:window.available.hdr10Processing) mode={true,OutputReason::None};
 frame.capabilities=window.available;
 frame.capabilities.sourceKnown=true;frame.capabilities.isDV=false;frame.capabilities.isHDR10=true;
 frame.capabilities.processing=window.available.hdr10Processing;
 assert(preferences.hdr10Source==HDR10SourceMode::Native);
 for(const auto& choice : {std::pair{"dvbridge.hdr10playbackchoice",0},
                           std::pair{"dvbridge.hdr10playbackchoice",1}})
   assert(!disabled(choice.second,choice.first));
 // Unknown source uses reusable HDR10-AI hardware facts, not authored-DV processing.
 window.available.processing[1]={false,OutputReason::NoGPUProcessing};
 frame={};
 assert(!disabled(1,"dvbridge.hdr10source"));
 frame.identity.valid=true;frame.capabilities=window.available;
 frame.capabilities.sourceKnown=true;frame.capabilities.isHDR10=true;
 frame.capabilities.processing=window.available.hdr10Processing;
 // Actual per-picture import failure must not be masked by reusable hardware facts.
 frame.capabilities.processing[1]={false,OutputReason::SourceIneligible};
 assert(disabled(0,"dvbridge.hdr10playbackchoice"));
 frame.capabilities.processing[1]={true,OutputReason::None};
 frame.capabilities.processingKnown=false;
 assert(disabled(0,"dvbridge.hdr10playbackchoice"));
 frame.capabilities.processingKnown=true;
 // Unsupported hardware and transport remain unavailable.
 frame.capabilities.processing[1]={false,OutputReason::NoGPUProcessing};
 assert(disabled(0,"dvbridge.hdr10playbackchoice"));
 frame.capabilities.processing[1]={true,OutputReason::None};
 window.available.nativeDV=false;
 assert(disabled(1,"dvbridge.hdr10source"));
 assert(disabled(0,"dvbridge.hdr10playbackchoice"));
 window.available.nativeDV=true;
 // HDR10+ is eligible only for metadata-guided conversion, with valid source metadata.
 frame.capabilities.hdr10PlusSource=true;
 assert(disabled(0,"dvbridge.hdr10playbackchoice"));
 assert(disabled(0,"dvbridge.hdr10plusplaybackchoice"));
 frame.capabilities.isHDR10Plus=true;
 assert(!disabled(3,"dvbridge.hdr10plussource"));
 assert(!disabled(0,"dvbridge.hdr10plusplaybackchoice"));
 // Native HDR10+ classification survives output teardown while paused.
 // Selection is deferred; this does not assert or manufacture per-picture admission.
 CDVPlaybackModes::nativeSource=StreamHdrType::HDR_TYPE_HDR10PLUS;
 frame={};
 assert(!disabled(1,"dvbridge.hdr10plusplaybackchoice"));
 assert(!disabled(0,"dvbridge.hdr10plusplaybackchoice"));
 // Explicit per-picture failures must not be replaced by the stream's HDR label.
 frame.identity.valid=true;
 assert(disabled(0,"dvbridge.hdr10plusplaybackchoice"));
 frame.capabilities=window.available;frame.capabilities.sourceKnown=true;
 frame.capabilities.isHDR10=true;frame.capabilities.hdr10PlusSource=true;
 frame.capabilities.isHDR10Plus=false;
 assert(disabled(0,"dvbridge.hdr10plusplaybackchoice"));
#endif
 // Global preferences use hardware capabilities, never the last frame's admission.
 // This covers a stopped HDR10 film, SDR/unknown input and stale import failures.
 preferences={};
 window.available.processingKnown=true;
 for(auto& mode:window.available.processing) mode={true,OutputReason::None};
 for(auto& mode:window.available.hdr10Processing) mode={true,OutputReason::None};
 for(int source=0;source<4;++source) {
   frame={};frame.identity.valid=true;frame.capabilities.sourceKnown=true;
   frame.capabilities.isDV=source==0;
   frame.capabilities.isHDR10=source==1 || source==2;
   frame.capabilities.hdr10PlusSource=source==2;
   CDVPlaybackModes::nativeSource=source==2 ? StreamHdrType::HDR_TYPE_HDR10PLUS : StreamHdrType::HDR_TYPE_NONE;
   for(int output:{0,1,3,4}) assert(!disabled(output,"dvbridge.outputmode"));
   for(int method:{0,1,2}) assert(!disabled(method,"dvbridge.hdr10method"));
#ifdef CB1_HAS_HDR10_AI
   for(int output:{0,1,2}) assert(!disabled(output,"dvbridge.hdr10source"));
   for(int output:{0,3}) assert(!disabled(output,"dvbridge.hdr10plussource"));
#endif
   // A quick switch still rejects the last frame's failed/unavailable processing.
   assert(disabled(0,"dvbridge.playbackchoice"));
 }
 // Real hardware limits still apply to global preferences.
 window.available.nativeDV=false;
 assert(disabled(0,"dvbridge.outputmode"));
 assert(!disabled(1,"dvbridge.outputmode"));
 window.available.nativeDV=true;window.available.hdr10=false;
 assert(disabled(1,"dvbridge.outputmode"));
 window.available.hdr10=true;window.available.hdr10plus=false;
 assert(disabled(2,"dvbridge.hdr10method"));
 window.available.processing[5]={false,OutputReason::NoGPUProcessing};
 assert(disabled(4,"dvbridge.outputmode"));
#ifdef CB1_HAS_HDR10_AI
 window.available.hdr10Processing[1]={false,OutputReason::NoGPUProcessing};
 assert(disabled(1,"dvbridge.hdr10source"));
 assert(disabled(3,"dvbridge.hdr10source"));
#endif
}
'''.replace('BODY', source[start:end])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(program)
            for flags in ([], ['-DCB1_HAS_HDR10_AI']):
                with self.subTest(flags=flags):
                    built = subprocess.run(['c++', '-std=c++20', *flags, '-I' + str(tree / 'xbmc'),
                                        str(root / 'test.cpp'), '-o', str(root / 'test')],
                                       capture_output=True, text=True)
                    self.assertEqual(built.returncode, 0, built.stderr)
                    ran = subprocess.run([str(root / 'test')], capture_output=True, text=True)
                    self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
