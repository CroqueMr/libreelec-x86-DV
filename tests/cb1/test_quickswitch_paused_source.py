"""Menu identity belongs to Kodi's selected stream, not an output transaction."""
import os
from pathlib import Path
import resource
import subprocess
import tempfile
import unittest
from test_native_video_source import body


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi tree')
class PausedQuickSwitch(unittest.TestCase):
    def test_native_source_opens_menu_after_output_clear_without_reviving_old_source(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        source = (tree / 'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        gate = body(source, 'bool CDVPlaybackModes::ShowMenu(')
        gate = gate[:gate.index('#ifdef CB1_HAS_HDR10_AI')] + '\nreturn true;\n}'
        signature = 'StreamHdrType CDVPlaybackModes::SourceType()'
        getter = signature + body(source, signature) if signature in source else ''
        code = r'''
#include <cassert>
#include <memory>
#include <string>
enum class StreamHdrType { HDR_TYPE_NONE, HDR_TYPE_HDR10, HDR_TYPE_DOLBYVISION,
 HDR_TYPE_HLG, HDR_TYPE_HDR10PLUS };
struct VideoStreamInfo {bool valid{};StreamHdrType hdrType{};std::string stereoMode;};
constexpr int CURRENT_STREAM=-1, WINDOW_DIALOG_SELECT=12000, LOGINFO=1, LOGDEBUG=0;
struct CApplicationPlayer {
 bool active=true;VideoStreamInfo info;
 bool IsPlayingVideo()const{return active;}
 void GetVideoStreamInfo(int stream,VideoStreamInfo& out)const{assert(stream==CURRENT_STREAM);out=info;}
};
auto player=std::make_shared<CApplicationPlayer>();
struct Components {template<class T>auto GetComponent(){return player;}};
struct CGUIDialogSelect{};
struct Windows {bool present=true;template<class T>T* GetWindow(int){static T dialog;return present?&dialog:nullptr;}};
struct GUI {Windows windows;Windows& GetWindowManager(){return windows;}};
struct Settings {int GetSettings(){return 0;}};
struct Resources {int GetLocalizeStrings(){return 0;}};
struct CServiceBroker {
 static Components& GetAppComponents(){static Components value;return value;}
 static GUI* GetGUI(){static GUI value;return &value;}
 static Settings* GetSettingsComponent(){static Settings value;return &value;}
 static Resources& GetResourcesComponent(){static Resources value;return value;}
};
namespace DVBRIDGE {
struct Capabilities {bool stereoSource{},sourceKnown{},isDV{},isHDR10{};};
struct Snapshot {struct {Capabilities capabilities;}transaction;};
struct StreamTelemetry {static inline Snapshot value;static Snapshot Read(){return value;}};
template<class... T>void DiagnosticLog(T...){}
}
struct Choice {int output,method,label;};
struct CDVPlaybackModes {
 static bool enabled;
 static bool MenuEnabled(){return enabled;}
 static StreamHdrType SourceType();
 static bool ShowMenu(bool settingsMenu=false) GATE
};
bool CDVPlaybackModes::enabled=true;
GETTER
int main(){
 using H=StreamHdrType;
 // Output teardown while paused: no new picture can refill the transaction.
 player->info={true,H::HDR_TYPE_HDR10PLUS,""};
 DVBRIDGE::StreamTelemetry::value={};
 assert(CDVPlaybackModes::ShowMenu());
 assert(!DVBRIDGE::StreamTelemetry::value.transaction.capabilities.sourceKnown);
 for(auto type:{H::HDR_TYPE_HDR10,H::HDR_TYPE_HDR10PLUS,H::HDR_TYPE_DOLBYVISION,H::HDR_TYPE_HLG}){
  player->info={true,type,"mono"};assert(CDVPlaybackModes::ShowMenu());
 }
 // HLG is independently eligible; an SDR source cannot inherit the previous DV/HDR transaction's menu.
 auto& old=DVBRIDGE::StreamTelemetry::value.transaction.capabilities;
 old.sourceKnown=old.isDV=true;
 for(auto type:{H::HDR_TYPE_NONE}){
  player->info={true,type,""};assert(!CDVPlaybackModes::ShowMenu());
 }
 player->info={true,H::HDR_TYPE_DOLBYVISION,"left_right"};assert(!CDVPlaybackModes::ShowMenu());
 player->info={false,H::HDR_TYPE_DOLBYVISION,""};assert(!CDVPlaybackModes::ShowMenu());
 player->info.valid=true;player->active=false;assert(!CDVPlaybackModes::ShowMenu());
 player->active=true;CDVPlaybackModes::enabled=false;assert(!CDVPlaybackModes::ShowMenu());
 // Global DV preferences stay available without a playing DV picture.
 player->active=false;player->info={};assert(CDVPlaybackModes::ShowMenu(true));
}
'''.replace('GATE', gate).replace('GETTER', getter)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'test.cpp').write_text(code)
            built = subprocess.run(['c++', '-std=c++20', str(path / 'test.cpp'), '-o', str(path / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(path / 'test')], capture_output=True, text=True,
                                 preexec_fn=lambda: resource.setrlimit(resource.RLIMIT_CORE, (0, 0)))
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
