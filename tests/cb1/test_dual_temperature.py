"""Native cached temperature formatting; ordinary Kodi labels stay unchanged."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET
from test_native_video_source import TREE,body

class DualTemperature(unittest.TestCase):
    def test_native_formatter_units_unknown_and_cached_polling(self):
        source=(TREE/'xbmc/guilib/guiinfo/SystemGUIInfo.cpp').read_text()
        formatter=body(source,'std::string CSystemGUIInfo::GetSystemHeatInfo(')
        program=r'''
#include <cassert>
#include <memory>
#include <string>
#include <fmt/format.h>
constexpr int SYSTEM_HEAT_UPDATE_INTERVAL=1000;
enum{SYSTEM_CPU_TEMPERATURE,SYSTEM_GPU_TEMPERATURE,SYSTEM_FAN_SPEED,SYSTEM_CPU_USAGE};
struct Temperature {double c{};bool valid=true;
 bool IsValid()const{return valid;}double ToCelsius()const{return c;}
 double ToFahrenheit()const{return c*1.8+32;}} nextTemperature{45};
int frame=1000,cpuPolls{},gpuPolls{};
struct CTimeUtils {static int GetFrameTime(){return frame;}};
struct CPU {bool GetTemperature(Temperature& t){++cpuPolls;t=nextTemperature;return t.valid;}
 bool SupportsCPUUsage(){return true;}std::string GetCoresUsageString(){return "0%";}} cpu;
struct GPU {bool GetTemperature(Temperature& t){++gpuPolls;t=nextTemperature;return t.valid;}};
struct Strings {std::string Get(int){return "Not available";}};
struct Resources {Strings strings;Strings& GetLocalizeStrings(){return strings;}};
struct CServiceBroker {static CPU* GetCPUInfo(){return &cpu;}
 static Resources& GetResourcesComponent(){static Resources r;return r;}};
struct Language {std::string GetTemperatureAsString(Temperature)const{return "REGIONAL";}} g_langInfo;
struct StringUtils {template<class... A>static std::string Format(fmt::format_string<A...> f,A&&... a){
 return fmt::format(f,std::forward<A>(a)...);}};
struct CSystemGUIInfo {
 mutable int m_lastSysHeatInfoTime{};
 mutable Temperature m_cpuTemp,m_gpuTemp;
 std::unique_ptr<GPU> m_gpuInfo=std::make_unique<GPU>();int m_fanSpeed{};
 std::string GetSystemHeatInfo(int info,bool dualUnits=false) const BODY
};
int main(){
 CSystemGUIInfo info;
 assert(info.GetSystemHeatInfo(SYSTEM_CPU_TEMPERATURE)=="REGIONAL");
 assert(info.GetSystemHeatInfo(SYSTEM_CPU_TEMPERATURE,true)=="113\u00b0F / 45\u00b0C");
 assert(info.GetSystemHeatInfo(SYSTEM_GPU_TEMPERATURE,true)=="REGIONAL");
 assert(cpuPolls==1 && gpuPolls==1);
 for(auto [c,expected]:{std::pair{-40.,"-40\u00b0F / -40\u00b0C"},
                       {0.,"32\u00b0F / 0\u00b0C"},{100.,"212\u00b0F / 100\u00b0C"}}){
  frame+=1000;nextTemperature={c};
  assert(info.GetSystemHeatInfo(SYSTEM_CPU_TEMPERATURE,true)==expected);
  assert(info.GetSystemHeatInfo(SYSTEM_CPU_TEMPERATURE)=="REGIONAL");
 }
 frame+=1000;nextTemperature.valid=false;
 assert(info.GetSystemHeatInfo(SYSTEM_CPU_TEMPERATURE,true).empty());
 assert(info.GetSystemHeatInfo(SYSTEM_CPU_TEMPERATURE)=="Not available");
 assert(cpuPolls==5 && gpuPolls==5);
}
'''.replace('BODY',formatter)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-lfmt','-o',str(root/'test')],
                                 capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_panel_requests_dual_units_without_changing_regional_defaults(self):
        manager=(TREE/'xbmc/GUIInfoManager.cpp').read_text()
        system=manager[manager.index('else if (cat.Name() == "system")'):]
        self.assertLess(system.index('prop.param() == "dual"'),system.index('for (const auto& system_label'))
        self.assertIn('AddMultiInfo(CGUIInfo(SYSTEM_CPU_TEMPERATURE, 1))',system)
        panel=ET.parse(Path(__file__).resolve().parents[2]/
            'projects/Generic/filesystem/usr/share/kodi/media/cb1/IncludesDVProcessInfo.xml')
        row=next(row for row in panel.iter('include') if
                 any(p.get('name')=='label' and p.get('value')=='Temperature' for p in row.findall('param')))
        params={p.get('name'):p.get('value') for p in row.findall('param')}
        self.assertEqual(params['value'],'$INFO[System.CPUTemperature(dual)]')
        self.assertIn('!String.IsEmpty(System.CPUTemperature(dual))',params['visible'])

if __name__=='__main__':unittest.main()
