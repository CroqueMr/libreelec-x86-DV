"""Load shipped bitmap defaults through the native control format boundary."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_native_video_source import TREE, body


class BitmapSettingsLoading(unittest.TestCase):
    def test_controls_load_neutral_defaults_and_missing_values_stay_neutral(self):
        controls = (TREE/'xbmc/settings/SettingControl.cpp').read_text()
        source = (TREE/'xbmc/settings/SubtitlesSettings.cpp').read_text()
        settings = ET.parse(TREE/'system/settings/settings.xml')
        calls = []
        for node in settings.findall('.//setting'):
            name = node.get('id', '')
            if not name.startswith('subtitles.bitmap'):
                continue
            control = node.find('control')
            self.assertEqual(control.get('type'), 'spinner' if node.find('constraints/minimum') is not None else 'list')
            if control.get('type') == 'spinner':
                calls.append('load('+json.dumps(name)+','+json.dumps(control.get('format'))+','+node.findtext('default')+');')
        self.assertEqual(len(calls), 6)
        program = r'''
#include <algorithm>
#include <cassert>
#include <cctype>
#include <map>
#include <memory>
#include <string>
#include "cores/VideoPlayer/DVDSubtitles/BitmapSubtitles.h"
struct StringUtils {
 static void ToLower(std::string& s){std::transform(s.begin(),s.end(),s.begin(),[](unsigned char c){return std::tolower(c);});}
 static bool EqualsNoCase(std::string a,std::string b){ToLower(a);ToLower(b);return a==b;}
};
struct CSettingControlSpinner {std::string m_format;bool SetFormat(const std::string& format) SET_FORMAT};
struct Settings {
 std::map<std::string,int> values;
 bool GetSetting(const std::string& id) const {return values.contains(id);}
 int GetInt(const std::string& id) const {auto it=values.find(id);return it==values.end()?0:it->second;}
};
using namespace KODI::SUBTITLES;
struct CSubtitlesSettings {
 std::shared_ptr<Settings> m_settings=std::make_shared<Settings>();
 BitmapOptions GetBitmapOptions() const GET_OPTIONS
};
int main(){
 CSubtitlesSettings subtitles;
 auto load=[&](const char* id,const char* format,int value){
  CSettingControlSpinner control;
  assert(control.SetFormat(format) && "shipped bitmap control must be accepted by Kodi");
  subtitles.m_settings->values[id]=value;
 };
 LOAD
 auto neutral=[&]{
  const auto options=subtitles.GetBitmapOptions();
  assert(!options.HasGeometry());
  assert(options.zoom==100 && options.sdrBrightness==100 && options.hdrBrightness==100);
  assert(options.sdrSaturation==100 && options.hdrSaturation==100);
  std::vector<uint32_t> palette{0xffffffff};
  AdjustBitmapPalette(palette,false,options,DVDOverlaySource::SUBTITLE);
  assert(palette[0]==0xffffffff);
 };
 neutral();
 subtitles.m_settings->values.clear();neutral();
 subtitles.m_settings->values["subtitles.bitmapsdrbrightness"]=0;
 subtitles.m_settings->values["subtitles.bitmaphdrbrightness"]=0;
 auto zero=subtitles.GetBitmapOptions();
 assert(zero.sdrBrightness==0 && zero.hdrBrightness==0 && zero.zoom==100);
}
'''.replace('SET_FORMAT', body(controls, 'bool CSettingControlSpinner::SetFormat('))
        program = program.replace('GET_OPTIONS', body(source, 'BitmapOptions CSubtitlesSettings::GetBitmapOptions() const'))
        program = program.replace('LOAD', '\n'.join(calls))
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code, executable = root/'probe.cpp', root/'probe'
            code.write_text(program)
            built = subprocess.run(['c++','-std=c++20','-DHAVE_DVBRIDGE','-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'),str(code),'-o',str(executable)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran = subprocess.run([str(executable)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__ == '__main__':
    unittest.main()
