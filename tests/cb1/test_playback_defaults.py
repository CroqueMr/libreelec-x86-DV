"""Run the shipped default/session, complete dialog and native action-label owners."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE, body

ROOT = Path(__file__).resolve().parents[2]


class PlaybackDefaultsTests(unittest.TestCase):
    def test_hdr10plus_settings_keep_exactly_four_choices_and_kodi_default(self):
        settings = ET.parse(TREE/'system/settings/settings.xml')
        selector = settings.find(".//setting[@id='dvbridge.hdr10plussource']")
        self.assertIsNotNone(selector)
        self.assertEqual(selector.findtext('default'), '0')
        self.assertEqual([choice.text for choice in selector.findall('constraints/options/option')],
                         ['3', '5', '0', '4'])

    def test_file_capture_live_dialog_and_stored_action_value(self):
        header = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSettings.h').read_text()
        header = '\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
        source = (TREE/'xbmc/dialogs/DVPlaybackModes.cpp').read_text()
        choices = re.search(r'struct Choice.*?dvChoices\[\].*?;', source, re.S).group()
        menu = body(source, 'bool CDVPlaybackModes::ShowMenu(')
        label = ''
        if 'CDVPlaybackModes::DefaultPlaybackLabel(' in source:
            label = 'std::string CDVPlaybackModes::DefaultPlaybackLabel() ' + body(source, 'CDVPlaybackModes::DefaultPlaybackLabel(')
        control = (TREE/'xbmc/settings/windows/GUIControlSettings.cpp').read_text()
        action = body(control[control.index('void CGUIControlButtonSetting::Update('):], 'case SettingType::Action:')
        selector = body((TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVOutputSelection.h').read_text(), 'inline OutputSelection SelectOutput(')
        program = r'''
#include <algorithm>
#include <atomic>
#include <bit>
#include <cmath>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <map>
#include <string>
#include <vector>
#include <iterator>
#include <cassert>
#define HAVE_DVBRIDGE
#ifndef CB1_TEST_NO_AI
#define CB1_HAS_HDR10_AI
#endif
#include "dvbridge_policy.h"
#include "cb1_cmv40.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h"
struct Settings {
 std::map<std::string,int> ints;std::map<std::string,double> numbers;
 unsigned writes=0,saves=0;std::string fail;
 int GetInt(const char* key){return ints[key];}
 double GetNumber(const char* key){return numbers[key];}
 bool GetBool(const char* key){return ints[key];}
 bool SetInt(const char* key,int value){++writes;if(fail==key)return false;ints[key]=value;return true;}
 void Save(){++saves;}
};
auto stored=std::make_shared<Settings>();
struct Component {auto GetSettings(){return stored;}} component;
struct CVariant {bool value=false;CVariant()=default;CVariant(bool b):value(b){}
 CVariant(const std::string&){}bool asBoolean()const{return value;}};
struct IntegerSettingOption {std::string label,label2;int value;std::vector<std::pair<std::string,CVariant>> properties;
 IntegerSettingOption(std::string l,int v):label(l),value(v){}};
struct CSetting {std::string id;const auto& GetId()const{return id;}};
struct CSettingInt:CSetting {CSettingInt(std::string value){id=value;}};
struct Strings {std::string Get(int id)const{return std::to_string(id);}};
struct Resources {const Strings& GetLocalizeStrings(){static Strings s;return s;}} resources;
struct CFileItem {CFileItem(std::string){}void SetLabel2(std::string){}void SetProperty(std::string,CVariant){}
 void SetProperty(std::string,const char*){}CVariant GetProperty(std::string){return {};}};
struct CGUIDialogSelect {
 int selected=0,current=-1;bool confirmed=true;std::vector<CFileItem> items;
 void Reset(){items.clear();}template<class T>void SetHeading(T){}void SetUseDetails(bool){}
 void Add(const CFileItem& item){items.push_back(item);}void SetSelected(int i){current=i;}
 void SetProperty(const char*,CVariant){}void Open(){}bool IsConfirmed(){return confirmed;}int GetSelectedItem(){return selected;}
} dialog;
constexpr int WINDOW_DIALOG_SELECT=1,LOGINFO=1;
struct Manager {template<class T>T* GetWindow(int){return &dialog;}} manager;
struct GUI {Manager& GetWindowManager(){return manager;}} gui;
constexpr int TMSG_MEDIA_SEEK_TIME=1;
struct CApplicationPlayer {bool CanSeek(){return false;}bool IsInMenu(){return false;}
 float GetPlaySpeed(){return 1.0f;}int GetTime(){return 0;}} player;
struct AppComponents {template<class T>T* GetComponent(){return &player;}} appComponents;
struct AppMessenger {void PostMsg(int,int){assert(false);}} appMessenger;
enum class VideoOutputType {DolbyVision,HDR10,HDR10Plus,HLG,SDR};
struct DataCacheCore {
 struct VideoInfo {std::optional<VideoOutputType> outputType;struct {unsigned flags;bool lldv;} output;};
 static inline VideoInfo recording{};
 VideoInfo GetVideoProcessingInfo(){return recording;}
};
struct CServiceBroker {static auto& GetAppComponents(){return appComponents;}
 static DataCacheCore& GetDataCacheCore(){static DataCacheCore core;return core;}
 static auto GetAppMessenger(){return &appMessenger;}
 static auto GetSettingsComponent(){return &component;}
 static auto& GetResourcesComponent(){return resources;}static auto GetGUI(){return &gui;}};
namespace DVBRIDGE {uint64_t NextRevision(){static uint64_t revision=1;return ++revision;}
 template<class... T>void DiagnosticLog(T...){}
 struct StreamTelemetry {struct Snapshot {struct {OutputCapabilities capabilities;} transaction;};static Snapshot Read(){return {};}};}
HEADER
namespace DVBRIDGE {enum class OutputRoute{Vanilla,NativeDV,HDR10,SDR,PlayerLed};
struct OutputSelection {OutputRoute route{};dvbridge_policy policy{};OutputReason reason{};int lldvFormat{};uint64_t lldvEdidGeneration{};unsigned lldvRgbScanoutBits{8};};
OutputSelection SelectOutput(const OutputPreferences& preferences,const OutputCapabilities& caps) SELECTOR
}
enum class StreamHdrType{HDR_TYPE_NONE,HDR_TYPE_DOLBYVISION,HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS,HDR_TYPE_HLG};
struct CSettingConditions {
 static inline bool hdr10PlusSink=true;
#ifdef CB1_HAS_HDR10_AI
 static constexpr int nativeHDR10PlusIndex=1;
#else
 static constexpr int nativeHDR10PlusIndex=0;
#endif
 static void DVOutputOptions(const std::shared_ptr<CSettingInt>& setting,std::vector<IntegerSettingOption>& options,bool) {
  if (!hdr10PlusSink && setting->GetId()=="dvbridge.hdr10plusplaybackchoice")
    options.at(nativeHDR10PlusIndex).properties.emplace_back("disabled",true);
 }
};
struct StringUtils {template<class... T>static std::string Format(std::string text,T...){return text;}};
CHOICES
bool ShowLldvFormatMenu(bool,bool){return false;}
struct CDVPlaybackModes {
 static inline StreamHdrType source=StreamHdrType::HDR_TYPE_DOLBYVISION;
 static bool MenuEnabled(){return true;}static StreamHdrType SourceType(){return source;}
 static bool ShowMenu(bool settingsMenu=false) MENU
 static std::string DefaultPlaybackLabel();
 static std::string LldvPreferenceLabel(){return "LLDV format";}
 static std::string SDRGamutLabel(){return "BT.709";}
};
LABEL
struct Button {std::string label;std::string GetLabel2(){return label;}} button;
enum class SettingType{Action};
std::string actionValue(const char* setting="dvbridge.playback"){std::string strText;auto m_pButton=&button;
 auto m_pSetting=std::make_shared<CSetting>();m_pSetting->id=setting;
 switch(SettingType::Action){case SettingType::Action: ACTION}return strText;}
bool choose(StreamHdrType type,int index,bool settings=false){CDVPlaybackModes::source=type;dialog.selected=index;return CDVPlaybackModes::ShowMenu(settings);}
int main(int argc,char** argv){assert(argc==2);using namespace DVBRIDGE;std::string scenario=argv[1];
 stored->ints={{"dvbridge.outputmode",1},{"dvbridge.hdr10method",1},{"dvbridge.hdr10source",1},
 {"dvbridge.hdr10plussource",3},{"dvbridge.hlgsource",1},{"dvbridge.tvgamut",2},{"dvbridge.expertgamut",2}};
 stored->numbers={{"dvbridge.tvpeak",1000},{"dvbridge.expertpeak",1000}};
 SelectOutputSettings();auto initial=FrameOutputSettings();auto saved=stored->ints;
 if(scenario=="default-edits"){
  stored->ints["dvbridge.outputmode"]=4;stored->ints["dvbridge.hdr10method"]=2;
  stored->ints["dvbridge.hdr10source"]=2;stored->ints["dvbridge.hdr10plussource"]=0;stored->ints["dvbridge.hlgsource"]=0;
  auto current=FrameOutputSettings();assert(current.SameValues(initial)&&current.revision==initial.revision);
  stored->numbers["dvbridge.tvpeak"]=2000;current=FrameOutputSettings();assert(current.peak==2000&&current.revision!=initial.revision);
  assert(current.output==initial.output&&current.method==initial.method&&current.hdr10Source==initial.hdr10Source);
  SelectOutputSettings();current=FrameOutputSettings();assert(current.output==OutputMode::MasterReference&&current.method==2);
  assert(current.hdr10Source==HDR10SourceMode::EnhancedDV&&current.hdr10PlusSource==HDR10SourceMode::Native&&current.hlgSource==HLGSourceMode::Native);
 }
 if(scenario=="fallback-menu"){
  stored->ints["dvbridge.outputmode"]=int(OutputMode::PlayerLed);
  SelectOutputSettings(false,false);
  assert(FrameOutputSettings().hdr10TransportFallback);
  dialog.confirmed=false;
  choose(StreamHdrType::HDR_TYPE_DOLBYVISION,0);
  assert(dialog.current==8); // Before a frame is committed, the requested row remains selected.
  DataCacheCore::recording={VideoOutputType::HDR10,{1,false}};
  choose(StreamHdrType::HDR_TYPE_DOLBYVISION,0);
  assert(dialog.current==4); // Active circuit is HDR10 Rendering.
  choose(StreamHdrType::HDR_TYPE_DOLBYVISION,0,true);
  assert(dialog.current==8);
  assert(FrameOutputSettings().output==OutputMode::PlayerLed && stored->writes==0);
 }
 if(scenario=="live"){
  for(int method=0;method<3;++method){assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,4+method));
   auto p=FrameOutputSettings();assert(p.output==OutputMode::HDR10&&p.method==method);assert(stored->ints==saved);}
#ifdef CB1_HAS_HDR10_AI
  assert(choose(StreamHdrType::HDR_TYPE_HDR10,1));assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::EnhancedDV);
  assert(choose(StreamHdrType::HDR_TYPE_HDR10PLUS,2));assert(FrameOutputSettings().hdr10PlusSource==HDR10SourceMode::Native);
#else
  assert(choose(StreamHdrType::HDR_TYPE_HDR10,0));assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::Native);
  assert(choose(StreamHdrType::HDR_TYPE_HDR10PLUS,1));assert(FrameOutputSettings().hdr10PlusSource==HDR10SourceMode::Native);
#endif
  assert(choose(StreamHdrType::HDR_TYPE_HLG,1));assert(FrameOutputSettings().hlgSource==HLGSourceMode::Native);
  auto active=FrameOutputSettings();for(int i=0;i<20;++i){auto p=FrameOutputSettings(i%2,i%3==0);assert(p.revision==active.revision);}
  assert(playbackMode==active.output&&hdr10PlaybackMode==active.hdr10Source&&hdr10PlusPlaybackMode==active.hdr10PlusSource);
  assert(stored->ints==saved&&stored->writes==0&&stored->saves==0);
  SelectOutputSettings();auto next=FrameOutputSettings();assert(next.output==initial.output&&next.method==initial.method);
  assert(next.hdr10Source==initial.hdr10Source&&next.hdr10PlusSource==initial.hdr10PlusSource&&next.hlgSource==initial.hlgSource);
 }
 if(scenario=="hdr10plus"){
  static_assert(int(HDR10SourceMode::HDR10PlusPassthrough)==5);
  stored->ints["dvbridge.hdr10plussource"]=0;
  SelectOutputSettings();
  constexpr auto hdr10Plus=StreamHdrType::HDR_TYPE_HDR10PLUS;
  constexpr int nativeChoice=CSettingConditions::nativeHDR10PlusIndex;
  constexpr int defaultChoice=nativeChoice+1;
#ifdef CB1_HAS_HDR10_AI
  constexpr int count=4;
#else
  constexpr int count=2;
#endif
  CSettingConditions::hdr10PlusSink=false;
  assert(choose(hdr10Plus,nativeChoice));
  assert(dialog.current==defaultChoice && dialog.items.size()==count);
  assert(FrameOutputSettings(true).hdr10PlusSource==HDR10SourceMode::Native);
  assert(hdr10PlusPlaybackMode==HDR10SourceMode::Native);
  CSettingConditions::hdr10PlusSink=true;
  assert(choose(hdr10Plus,nativeChoice));
  const auto native=FrameOutputSettings(true);
  assert(native.hdr10PlusSource==HDR10SourceMode::HDR10PlusPassthrough);
  assert(hdr10PlusPlaybackMode==HDR10SourceMode::HDR10PlusPassthrough);
  assert(native.hdr10Source==HDR10SourceMode::Native &&
         native.HDR10Mode(true)==HDR10SourceMode::Native);
  assert(FrameOutputSettings().hdr10Source==HDR10SourceMode::ReferenceDV);
  assert(choose(hdr10Plus,defaultChoice));
  assert(dialog.current==nativeChoice && dialog.items.size()==count);
  assert(FrameOutputSettings(true).hdr10PlusSource==HDR10SourceMode::Native);
  assert(hdr10PlusPlaybackMode==HDR10SourceMode::Native);
#ifdef CB1_HAS_HDR10_AI
  assert(choose(hdr10Plus,0));
  assert(FrameOutputSettings(true).hdr10PlusSource==HDR10SourceMode::HDR10PlusDV);
  assert(choose(hdr10Plus,3));
  assert(FrameOutputSettings(true).hdr10PlusSource==HDR10SourceMode::SDR);
#endif
  assert(stored->ints["dvbridge.hdr10plussource"]==0 && stored->writes==0 && stored->saves==0);
  stored->ints["dvbridge.hdr10plussource"]=5;
  SelectOutputSettings();
  const auto persisted=FrameOutputSettings(true);
  assert(persisted.hdr10PlusSource==HDR10SourceMode::HDR10PlusPassthrough);
  assert(persisted.HDR10Mode(true)==HDR10SourceMode::Native);
 }
 if(scenario=="settings"){
  assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,0));assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,6,true));
  assert(dialog.current==5);assert(stored->ints["dvbridge.outputmode"]==1&&stored->ints["dvbridge.hdr10method"]==2);
  assert(stored->saves==1);assert(FrameOutputSettings().output==OutputMode::MasterReference);
  SelectOutputSettings();assert(FrameOutputSettings().output==OutputMode::HDR10&&FrameOutputSettings().method==2);
 }
 if(scenario=="label"){
  assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,0));assert(actionValue()=="40823");
  for(int method=0;method<3;++method){stored->ints["dvbridge.hdr10method"]=method;
   assert(actionValue()==std::to_string(method==0?40822:method==1?40823:40922));}
  stored->ints["dvbridge.outputmode"]=2;assert(actionValue()=="40814");
  assert(actionValue("dvbridge.lldvformat")=="LLDV format");
  assert(actionValue("dvbridge.sdrgamut")=="BT.709");
 }
 if(scenario=="legacy-toggles"){
  auto before=FrameOutputSettings();stored->ints["dvbridge.encodedactivearea"]=1;stored->ints["dvbridge.masterfallback"]=1;
  stored->ints["dvbridge.optimizedgui"]=0;auto after=FrameOutputSettings();assert(before.SameValues(after)&&before.revision==after.revision);
 }
 if(scenario=="master-first"){
  const auto dv=StreamHdrType::HDR_TYPE_DOLBYVISION;
  stored->ints["dvbridge.outputmode"]=0;
  SelectOutputSettings();
  assert(choose(dv,0));
  assert(dialog.current==1 && FrameOutputSettings().output==OutputMode::MasterReference);
  assert(stored->ints["dvbridge.outputmode"]==0);
  assert(choose(StreamHdrType::HDR_TYPE_HDR10,0,true));
  assert(dialog.current==1 && stored->ints["dvbridge.outputmode"]==4);
  assert(actionValue()=="40913");
  assert(choose(dv,1,true));
  assert(dialog.current==0 && stored->ints["dvbridge.outputmode"]==0);
 }
 if(scenario=="player-led"){
  assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,8,true));
  assert(stored->ints["dvbridge.outputmode"]==7);
  assert(actionValue()=="41221");
  SelectOutputSettings();
  stored->ints["dvbridge.cmv40"]=1;
  auto preferences=FrameOutputSettings();
  auto policy=preferences.Policy();
  assert(PolicyCode(policy)==9 && policy.tv.peak_nits==0);
  assert(preferences.CMv40Options(policy.mode).mode==1);
  OutputCapabilities caps;
  caps.sourceKnown=caps.isDV=caps.processingKnown=caps.nativeDV=caps.hdr10=true;
  for(auto& mode:caps.processing)mode={true,OutputReason::None};
  assert(SelectOutput(preferences,caps).route==OutputRoute::Vanilla);
  caps.playerLed=true;
  assert(SelectOutput(preferences,caps).route==OutputRoute::PlayerLed);
  UsePlayerLedStartupFallback();
  assert(FrameOutputSettings().hdr10TransportFallback);
  assert(SelectOutput(FrameOutputSettings(),caps).route==OutputRoute::HDR10);
  SelectOutputSettings();
  assert(choose(StreamHdrType::HDR_TYPE_DOLBYVISION,8,false));
  UsePlayerLedStartupFallback();
  assert(!FrameOutputSettings().hdr10TransportFallback);
  caps.isDV=false;
  assert(SelectOutput(preferences,caps).route==OutputRoute::Vanilla);
 }
 if(scenario=="strict"){
  OutputCapabilities caps;caps.sourceKnown=caps.isDV=caps.processingKnown=caps.hdr10=true;
  auto lldv = initial;
  lldv.output=OutputMode::PlayerLed;
  lldv.expertPeak=0;
  assert(SelectOutput(lldv,caps).reason==OutputReason::NoPlayerLedTransport);
  caps.playerLed=true;
  caps.lldvEdidGeneration=4;
  caps.lldvDisplay.sink.version=2;
  caps.lldvDisplay.peak=2484;
  caps.lldvDisplay.primaries={.68,.31,.246,.703,.15,.052};
  caps.processing[DVBRIDGE_MODE_PLAYER_LED]={true,OutputReason::None};
  const auto selectedLldv=SelectOutput(lldv,caps);
  assert(selectedLldv.route==OutputRoute::PlayerLed && selectedLldv.lldvEdidGeneration==4);
  assert(selectedLldv.policy.tv.peak_nits==2484 && selectedLldv.policy.lldv_edid_version==2);
  lldv.expertPeak=800;
  assert(SelectOutput(lldv,caps).policy.tv.peak_nits==2484);
  for(auto& mode:caps.processing)mode={true,OutputReason::None};
  for(auto output:{OutputMode::Standard,OutputMode::MasterReference,OutputMode::AdaptiveB}){
   auto p=initial;p.output=output;auto selected=SelectOutput(p,caps);
   assert(selected.route==OutputRoute::Vanilla&&selected.reason==OutputReason::NoDVTransport);
   assert(selected.policy.mode==p.Policy().mode);
  }
  auto p=initial;p.method=2;auto selected=SelectOutput(p,caps);
  assert(selected.route==OutputRoute::Vanilla&&selected.reason==OutputReason::NoHDR10PlusTransport);
  p.output=OutputMode::Disabled;assert(SelectOutput(p,caps).reason==OutputReason::None);
 }
}
'''.replace('HEADER',header).replace('SELECTOR',selector).replace('MENU',menu).replace('CHOICES',choices).replace('LABEL',label).replace('ACTION',action)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);code=root/'check.cpp';binary=root/'check';code.write_text(program)
            for flags in ([],['-DCB1_TEST_NO_AI']):
                built=subprocess.run(['c++','-std=c++20',*flags,'-I'+str(ROOT/'CB1/src'),'-I'+str(TREE/'xbmc'),str(code),'-o',str(binary)],capture_output=True,text=True)
                self.assertEqual(built.returncode,0,built.stderr)
                for scenario in ('fallback-menu', 'default-edits','live','hdr10plus','settings','label','legacy-toggles','strict','master-first','player-led'):
                    with self.subTest(flags=flags,scenario=scenario):
                        ran=subprocess.run([str(binary),scenario],capture_output=True,text=True)
                        self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)

    def test_native_selector_capture_is_limited_to_file_startup(self):
        video=(TREE/'xbmc/cores/VideoPlayer/VideoPlayer.cpp').read_text()
        capture = body(video, 'static void SelectDVStartupOutput(')
        self.assertIn('DVBRIDGE::SelectOutputSettings(', capture)
        self.assertIn('caps.hdr10 && !caps.HDR10DepthLimited()', capture)

        prepare = body(video, 'void CVideoPlayer::Prepare()')
        self.assertLess(prepare.index('SelectDVStartupOutput('), prepare.index('OpenInputStream()'))

        opening = body(video, 'bool CVideoPlayer::OpenVideoStream(')
        capture_at_open = opening.index('SelectDVStartupOutput(window)')
        self.assertLess(opening.index('window->PendingDVStartupEdid()'), capture_at_open)
        self.assertLess(capture_at_open, opening.index('ChoosePlaybackResolution('))
        self.assertLess(capture_at_open, opening.index('player->OpenStream(hint)'))
        self.assertEqual(video.count('SelectDVStartupOutput('), 3)
        hits=[]
        for source in (TREE/'xbmc').rglob('*.cpp'):
            if 'SelectOutputSettings(' in source.read_text(errors='replace'): hits.append(source.relative_to(TREE).as_posix())
        self.assertEqual(hits,['xbmc/cores/VideoPlayer/VideoPlayer.cpp'])

if __name__=='__main__':unittest.main()
