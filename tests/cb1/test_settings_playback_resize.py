"""Exercise the native resize handler without a running window system."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'),'Set patched Kodi source tree')
class SettingsPlaybackResizeTests(unittest.TestCase):
    def test_playback_resize_never_prompts_or_saves_the_desktop_mode(self):
        from test_native_video_source import body
        source=(Path(os.environ['KODI_NATIVE_SOURCE_TREE'])/
                'xbmc/settings/windows/GUIWindowSettingsCategory.cpp').read_text()
        handler=body(source,'case GUI_MSG_NOTIFY_ALL:')
        program=r'''
#include <cassert>
#include <memory>
constexpr int GUI_MSG_WINDOW_RESIZE=1;
struct Message {int event=GUI_MSG_WINDOW_RESIZE; int GetParam1() const {return event;}};
struct Display {
  int current=60,desktop=60,saves=0;
  int GetCurrentResolution() const {return current;}
  void SetCurrentResolution(int value,bool save=false) {
    if(save) {++saves;desktop=value;} else current=value;
  }
} display;
struct CDisplaySettings {static Display& GetInstance() {return display;}};
struct CApplicationPlayer {
  bool playing=false,video=false;
  bool IsPlaying() const {return playing;}
  bool IsPlayingVideo() const {return playing && video;}
};
struct Components {
  std::shared_ptr<CApplicationPlayer> player=std::make_shared<CApplicationPlayer>();
  template<class T> std::shared_ptr<T> GetComponent() {return player;}
} components;
struct Graphics {int resolution=24; int GetVideoResolution() const {return resolution;}};
struct Window {Graphics graphics;Graphics& GetGfxContext() {return graphics;}} window;
struct CServiceBroker {
  static Window* GetWinSystem() {return &window;}
  static Components& GetAppComponents() {return components;}
};
struct Category {
  bool active=true;int created=0;
  bool IsActive() const {return active;}
  void CreateSettings() {++created;}
  void Resize(Message& message) {switch(0) {case 0: HANDLER}}
};
int main() {
  Message message;
  // OpenVideoStream switches timing before HasVideo becomes true.
  components.player->playing=true;Category startup;startup.Resize(message);
  assert(display.saves==0 && display.desktop==60 && display.current==60 && startup.created==0);
  components.player->video=true;Category video;video.Resize(message);
  assert(display.saves==0 && display.current==60 && video.created==0);
  // The native stop path restores GetCurrentResolution, not the saved string.
  components.player->playing=false;window.graphics.resolution=display.GetCurrentResolution();
  video.Resize(message);
  assert(window.graphics.resolution==60 && display.desktop==60 && display.saves==0);
  window.graphics.resolution=24;display={};components.player->video=false;Category manual;manual.Resize(message);
  assert(display.saves==1 && display.desktop==24 && manual.created==1);
  // An explicit display-setting edit updates runtime state before its resize event.
  display.current=24;components.player->playing=true;Category explicitEdit;explicitEdit.Resize(message);
  assert(display.saves==1 && display.desktop==24 && explicitEdit.created==0);
  display={};components.player->video=true;Category inactive;inactive.active=false;inactive.Resize(message);
  assert(display.saves==0 && display.current==60 && inactive.created==0);
  message.event=99;Category unrelated;unrelated.Resize(message);
  assert(display.saves==0 && unrelated.created==0);
}
'''.replace('HANDLER',handler)
        with tempfile.TemporaryDirectory(prefix='cb1-settings-resize-') as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],
                                 capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)
