# SPDX-License-Identifier: MIT
"""Execute the actual Expert snapshot/callback code with isolated native settings."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import body

TREE=Path(os.environ.get('KODI_NATIVE_SOURCE_TREE','/unavailable'))
REPO=Path(__file__).resolve().parents[2]

@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'),'Set matched Kodi source tree')
class ExpertSettings(unittest.TestCase):
    def test_legacy_calibration_copies_once_without_overwriting_explicit_values(self):
        code=body((TREE/'xbmc/settings/Settings.cpp').read_text(),
                  'bool CSettings::Load(const TiXmlElement* root, bool& updated)')
        program=r'''
#include <tinyxml.h>
#include <cassert>
#include <map>
#include <memory>
#include <optional>
#include <string>
#include <string_view>
#include <utility>
#define HAVE_DVBRIDGE
struct CSettingsBase {
 inline static std::map<std::string,std::string> values;
 static bool LoadValuesFromXml(const TiXmlElement* root,bool&){
  values.clear();for(auto* e=root->FirstChildElement("setting");e;e=e->NextSiblingElement("setting"))
   values[e->Attribute("id")]=e->GetText();return true;
 }
};
struct Settings:CSettingsBase {
 bool Load(const TiXmlNode*){return true;}
 bool Load(const TiXmlElement* root,bool& updated) BODY
};
int main(){
 for(bool explicitPeak:{false,true})for(bool explicitGamut:{false,true})for(bool defaults:{false,true}){
  std::string xml="<settings><setting id='dvbridge.tvpeak' default='"+std::string(defaults?"true":"false")+
   "'>1234.5</setting><setting id='dvbridge.tvgamut'>3</setting>";
  if(explicitPeak)xml+="<setting id='dvbridge.expertpeak'>900.1</setting>";
  if(explicitGamut)xml+="<setting id='dvbridge.expertgamut'>1</setting>";
  xml+="</settings>";TiXmlDocument doc;doc.Parse(xml.c_str());assert(!doc.Error());
  TiXmlPrinter before;doc.Accept(&before);
  Settings settings;bool updated=false;assert(settings.Load(doc.RootElement(),updated));
  assert(settings.values["dvbridge.tvpeak"]=="1234.5" && settings.values["dvbridge.tvgamut"]=="3");
  assert(updated==(!explicitPeak && !defaults));
  if(explicitPeak)assert(settings.values["dvbridge.expertpeak"]=="900.1");
  else if(!defaults)assert(settings.values["dvbridge.expertpeak"]=="1234.5");
  else assert(!settings.values.contains("dvbridge.expertpeak"));
  if(explicitGamut)assert(settings.values["dvbridge.expertgamut"]=="1");
  TiXmlPrinter after;doc.Accept(&after);assert(std::string(before.CStr())==after.CStr());
 }
}
'''.replace('BODY',code)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            result=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-ltinyxml',
                                   '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_snapshot_admission_and_custom_memory(self):
        header=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        header='\n'.join(v for v in header.splitlines() if not v.startswith('#include'))
        source=(TREE/'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        loaded=body(source,'void CDVPlaybackModes::OnSettingsLoaded()')
        changed=body(source,'void CDVPlaybackModes::OnSettingChanged(')
        program=r'''
#include <atomic>
#include <bit>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#define HAVE_DVBRIDGE
struct Settings {
 std::map<std::string,int> ints;
 std::map<std::string,double> numbers;
 int GetInt(const char* k){return ints[k];}
 double GetNumber(const char* k){return numbers[k];}
 bool GetBool(const char* k){return ints[k];}
 bool SetBool(const char* k,bool v){ints[k]=v;return true;}
 bool SetNumber(const char* k,double v){numbers[k]=v;return true;}
};
auto stored=std::make_shared<Settings>();
struct Component {auto GetSettings(){return stored;}} component;
struct CServiceBroker {static auto GetSettingsComponent(){return &component;}};
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t n=1;return ++n;}}
HEADER
struct CSetting {std::string id;std::string GetId()const{return id;}};
struct Callback {
 int m_expertBlackPreset{};
 void OnSettingsLoaded() LOADED
 void OnSettingChanged(const std::shared_ptr<const CSetting>& setting) CHANGED
};
int main(){
 using namespace DVBRIDGE;
 stored->ints["dvbridge.outputmode"]=1;stored->ints["dvbridge.hdr10method"]=1;
 stored->ints["dvbridge.expertgamut"]=2;stored->numbers["dvbridge.expertpeak"]=1234.5;
 stored->ints["dvbridge.expertblack"]=3;stored->numbers["dvbridge.expertblackcustom"]=.0042;
 auto p=FrameOutputSettings();
 assert(p.ExpertProfileValid() && !p.ProfileValid());
 assert(p.ProfileValid(DVBRIDGE_MODE_HDR10_EXPERT));
 auto policy=p.Policy();assert(policy.tv.peak_nits==1234.5 && policy.tv.gamut==DVBRIDGE_GAMUT_P3_D65);
 assert(policy.expert_black_nits==.0042 && policy.mode==DVBRIDGE_MODE_HDR10_EXPERT);
 for(int mode=0;mode<4;mode++){
  stored->ints["dvbridge.expertblack"]=mode;
  const double expected[]={0,.005,.05,.0042};
  assert(FrameOutputSettings().Policy().expert_black_nits==expected[mode]);
 }
 stored->numbers["dvbridge.expertpeak"]=0;stored->numbers["dvbridge.tvpeak"]=2000;
 stored->ints["dvbridge.tvgamut"]=2;
 p=FrameOutputSettings();assert(!p.ExpertProfileValid() && p.ProfileValid());
 stored->ints["dvbridge.outputmode"]=0;p=FrameOutputSettings();
 stored->numbers["dvbridge.expertpeak"]=1500.1;
 stored->numbers["dvbridge.expertblackcustom"]=.0001;
 assert(FrameOutputSettings().revision==p.revision);
 stored->ints["dvbridge.hdr10source"]=2;
 auto ai=FrameOutputSettings().HDR10Policy();
 assert(ai.mode==DVBRIDGE_MODE_ENHANCED_DV && ai.tv.peak_nits==2000 && ai.expert_black_nits==0);
 Callback callback;
 auto preset=std::make_shared<CSetting>(CSetting{"dvbridge.expertblack"});
 auto custom=std::make_shared<CSetting>(CSetting{"dvbridge.expertblackcustom"});
 for(int initial=0;initial<3;initial++){
  stored->ints["dvbridge.expertblack"]=initial;stored->ints["dvbridge.expertblackcustomset"]=0;
  callback.OnSettingsLoaded();stored->ints["dvbridge.expertblack"]=3;callback.OnSettingChanged(preset);
  const double expected[]={0,.005,.05};
  assert(stored->numbers["dvbridge.expertblackcustom"]==expected[initial]);
  stored->numbers["dvbridge.expertblackcustom"]=.1234;callback.OnSettingChanged(custom);
  stored->ints["dvbridge.expertblack"]=0;callback.OnSettingChanged(preset);
  callback.OnSettingsLoaded();stored->ints["dvbridge.expertblack"]=3;callback.OnSettingChanged(preset);
  assert(stored->numbers["dvbridge.expertblackcustom"]==.1234);
 }
}
'''.replace('HEADER',header).replace('LOADED',loaded).replace('CHANGED',changed)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            result=subprocess.run(['c++','-std=c++20','-I'+str(REPO/'CB1/src'),str(root/'test.cpp'),
                                   '-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_decimal_controls_use_native_text_validation_and_are_expert_only(self):
        settings=ET.parse(TREE/'system/settings/settings.xml')
        for key,step in [('dvbridge.expertpeak','0.1'),('dvbridge.expertblackcustom','0.0001')]:
            node=settings.find(f".//setting[@id='{key}']")
            self.assertEqual(node.find('control').get('format'),'string')
            self.assertEqual(node.findtext('constraints/step'),step)
            text=ET.tostring(node,encoding='unicode')
            self.assertIn('dvbridge.hdr10method',text)
        source=(TREE/'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        self.assertIn('expert ? !CGUIKeyboardFactory::ShowAndGetInput',source)
        conditions=(TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        self.assertIn('dvbridge_tv_profile{preferences.expertPeak',conditions)

if __name__=='__main__':unittest.main()
