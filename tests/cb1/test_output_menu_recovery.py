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
namespace DVBRIDGE {
enum class OutputMode {Standard, HDR10, Disabled};
struct Preferences { OutputMode output{}; double peak=1000; int gamut=2;
 bool ProfileValid() const { return peak>0 && gamut>0; } } preferences;
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
bool disabled(int value=0) {
 std::vector<IntegerSettingOption> list(1);list[0].value=value;
 CSettingConditions::DVOutputOptions(std::make_shared<CSetting>(),list);
 return list[0].properties.back().second;
}
int main() {
 using namespace DVBRIDGE;
 window.available.processingKnown=true;window.available.nativeDV=true;window.available.hdr10=true;
 for(auto& mode:window.available.processing) mode={true,OutputReason::None};
 auto& frame=StreamTelemetry::value.transaction;
 frame.identity.valid=true;frame.capabilities=window.available;
 frame.capabilities.sourceKnown=true;frame.capabilities.isDV=true;
 std::vector<IntegerSettingOption> choices;
 for(int value:{0,4,5,6,2,1}) {IntegerSettingOption option;option.value=value;choices.push_back(option);}
 CSettingConditions::DVOutputOptions(std::make_shared<CSetting>(),choices);
 assert(choices.size()==6 && !choices[3].properties.back().second);
 frame.capabilities.processing[4]={false,OutputReason::SourceIneligible};
 assert(disabled(5) && disabled(6));
 frame.capabilities.processing[4]={true,OutputReason::None};
 assert(!disabled(5) && !disabled(6));
 assert(!disabled());
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
}
'''.replace('BODY', source[start:end])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'test.cpp').write_text(program)
            for flags in ([],):
                built = subprocess.run(['c++', '-std=c++20', *flags, '-I' + str(tree / 'xbmc'),
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stderr)
                ran = subprocess.run([str(root / 'test')], capture_output=True, text=True)
                self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
