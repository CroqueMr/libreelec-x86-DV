"""A refused boot-profile selection must not leave a checked Kodi setting."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class DriverProfileSetting(unittest.TestCase):
    def test_selection_failure_keeps_the_previous_setting(self):
        source = (Path(os.environ['KODI_NATIVE_SOURCE_TREE']) /
                  'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        signature = 'bool CDVPlaybackModes::OnSettingChanging('
        # Before the override, Kodi's native ISettingCallback accepts the change.
        body = '{ return true; }'
        if signature in source:
            start = source.index('{', source.index(signature))
            depth, end = 1, start + 1
            while depth:
                depth += (source[end] == '{') - (source[end] == '}')
                end += 1
            body = source[start:end]
        program = r'''
#include <cassert>
#include <memory>
#include <map>
#include <string>
#define CB1_DEBUG_BUILD 1
constexpr int LOGERROR=0,LOGINFO=1;
struct CSetting {std::string id="debug.cb1standarddrivers";const std::string& GetId()const{return id;}};
struct CSettingBool:CSetting {bool value=true;bool GetValue()const{return value;}};
struct Value {std::string text;bool boolean=true;std::string asString()const{return text;}bool asBoolean()const{return boolean;}};
struct CVariant {std::map<std::string,Value> fields;Value& operator[](const char* key){return fields[key];}};
bool commandOK=false;std::string command;int calls=0;
bool SelectDriverProfile(bool value,CVariant& status){
 command=value ? "select standard" : "select modified";++calls;
 status["pending"].text=value ? "standard" : "modified";return commandOK;
}
struct CLog {template<class...T>static void Log(T...) {}};
struct Localizer {std::string Get(int)const{return "message";}};
struct Resources {Localizer strings;Localizer& GetLocalizeStrings(){return strings;}};
struct CServiceBroker {static Resources& GetResourcesComponent(){static Resources r;return r;}};
struct CGUIDialogKaiToast {enum {Info};template<class...T>static void QueueNotification(T...){}};
struct CDVPlaybackModes {
 bool m_syncingProfile=false,m_driverProfilesAvailable=false,m_standardProfile=false;
 bool OnSettingChanging(const std::shared_ptr<const CSetting>& setting) BODY
};
int main(){
 CDVPlaybackModes modes;auto setting=std::make_shared<CSettingBool>();
 assert(!modes.OnSettingChanging(setting));
 assert(command=="select standard");
 // Native CSettingBool::SetValue repeats the callback with the old value on refusal.
 setting->value=false;assert(modes.OnSettingChanging(setting));assert(calls==1);
 setting->value=true;
 commandOK=true;assert(modes.OnSettingChanging(setting));
 assert(modes.m_standardProfile);
 setting->value=false;assert(modes.OnSettingChanging(setting));
 assert(!modes.m_standardProfile && command=="select modified");
 modes.m_syncingProfile=true;command.clear();assert(modes.OnSettingChanging(setting));assert(command.empty());
}
'''.replace('BODY', body)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root/'test.cpp'), '-o', str(root/'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)
