"""Progress evidence survives startup chatter without increasing the line budget."""
import test_diagnostics_runtime as diagnostics
from test_native_video_source import body
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class HDR10PlusDiagnostics(unittest.TestCase):
    def test_native_rejection_details_are_bounded_admitted_and_do_not_change_transport(self):
        # Dropping rejection detail, reading beyond the arrays, or staging an
        # unsupported display must fail this real-function/real-serializer check.
        text=(diagnostics.TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        stage=body(text,'void CWinSystemGbmGLESContext::StageNativeHDR10Plus(')
        prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
        repo=Path(__file__).resolve().parents[2]
        program=r'''
#include "cb1_hdr10plus.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <cstring>
#include <iterator>
#include <memory>
#include <optional>
#include <string>
#include <vector>
#include <fmt/format.h>
constexpr int LOGINFO=1;
namespace DVBRIDGE {
inline bool admit=true;
inline std::vector<std::string> lines;
template<class...T>bool DiagnosticLog(int,fmt::format_string<T...> f,T&&...a){
 if(!admit)return false;
 lines.push_back(fmt::format(f,std::forward<T>(a)...));return true;
}
}
namespace KODI::UTILS {enum class Eotf{PQ};}
struct Cache{uint64_t GetVideoProcessingGeneration(){return 7;}};
struct CServiceBroker{static Cache& GetDataCacheCore(){static Cache cache;return cache;}};
struct Connector{bool SupportsProperty(const char*){return true;}};
struct DRMBase{virtual ~DRMBase()=default;};
struct CDRMAtomic:DRMBase{
 Connector connector;
 std::optional<std::array<uint8_t,31>> packet;
 Connector* GetConnector(){return &connector;}
 void StageHDR10Plus(std::optional<std::array<uint8_t,31>> value,uint64_t generation){
  assert(generation==7);packet=std::move(value);
 }
};
struct Source{
 AVDynamicHDRPlus metadata{};
 uint64_t Generation()const{return 7;}
 const AVDynamicHDRPlus* HDR10Plus()const{return &metadata;}
};
struct Display{unsigned version=1;unsigned HDR10PlusVersion()const{return version;}};
struct CWinSystemGbmGLESContext{
 std::shared_ptr<DRMBase> m_DRM=std::make_shared<CDRMAtomic>();
 std::shared_ptr<Source> m_videoSourceSideData=std::make_shared<Source>();
 std::string m_hdr10plusReason;
 Display display;
 const Display* GetDisplayInfo(){return &display;}
 KODI::UTILS::Eotf GetEotf(){return KODI::UTILS::Eotf::PQ;}
 unsigned GetOutputBitDepth(){return 10;}
 void StageNativeHDR10Plus(bool overlay) BODY
 CDRMAtomic& drm(){return *std::dynamic_pointer_cast<CDRMAtomic>(m_DRM);}
};
AVDynamicHDRPlus fixture(){
 AVDynamicHDRPlus m{};m.itu_t_t35_country_code=0xb5;m.application_version=1;m.num_windows=1;
 m.targeted_system_display_maximum_luminance={300,1};
 auto& p=m.params[0];
 p.maxscl[0]={3956,100000};p.maxscl[1]={2063,100000};p.maxscl[2]={2047,100000};
 p.average_maxrgb={93,100000};p.fraction_bright_pixels={0,1000};
 const unsigned percentages[]={1,5,10,25,50,75,90,95,99};
 const int values[]={0,2094,96,3,4,5,88,720,2888};
 const int anchors[]={102,205,307,410,512,614,717,819,0};
 p.num_distribution_maxrgb_percentiles=p.num_bezier_curve_anchors=9;p.tone_mapping_flag=1;
 p.knee_point_x=p.knee_point_y={0,4095};
 for(unsigned i=0;i<9;i++){
  p.distribution_maxrgb[i]={static_cast<uint8_t>(percentages[i]),{values[i],100000}};
  p.bezier_curve_anchors[i]={anchors[i],1023};
 }
 return m;
}
void unchanged(CWinSystemGbmGLESContext& w,const AVDynamicHDRPlus& original){
 assert(!std::memcmp(&w.m_videoSourceSideData->metadata,&original,sizeof(original)));
}
int main(){
 using DVBRIDGE::lines;
 CWinSystemGbmGLESContext rejected;rejected.m_videoSourceSideData->metadata=fixture();
 const auto original=rejected.m_videoSourceSideData->metadata;
 rejected.StageNativeHDR10Plus(false);unchanged(rejected,original);
 assert(!rejected.drm().packet);
 assert(lines.size()==3 && "rejected source needs its summary and two bounded detail lines");
 assert(lines[0].find("HDR10+ output: unrepresentable-metadata")!=std::string::npos);
 assert(lines[1]=="HDR10+ statistics: distribution=[1:0/100000,5:2094/100000,10:96/100000,25:3/100000,50:4/100000,75:5/100000,90:88/100000,95:720/100000,99:2888/100000] maxscl=[3956/100000,2063/100000,2047/100000] average=93/100000 bright=0/1000");
 assert(lines[2]=="HDR10+ curve: knee=0/4095,0/4095 anchors=[102/1023,205/1023,307/1023,410/1023,512/1023,614/1023,717/1023,819/1023,0/1023]");
 rejected.StageNativeHDR10Plus(true);assert(lines.size()==3);unchanged(rejected,original);

 lines.clear();CWinSystemGbmGLESContext invalid;
 invalid.m_videoSourceSideData->metadata=fixture();auto& p=invalid.m_videoSourceSideData->metadata.params[0];
 p.num_distribution_maxrgb_percentiles=p.num_bezier_curve_anchors=255;
 for(unsigned i=0;i<15;i++){
  p.distribution_maxrgb[i]={static_cast<uint8_t>(i+1),{static_cast<int>(100+i),100000}};
  p.bezier_curve_anchors[i]={static_cast<int>(i+1),1023};
 }
 const auto malformed=invalid.m_videoSourceSideData->metadata;
 invalid.StageNativeHDR10Plus(false);assert(!invalid.drm().packet);unchanged(invalid,malformed);
 assert(lines.size()==3 && lines[0].find("invalid-metadata")!=std::string::npos);
 assert(lines[1].find("distribution=[1:100/100000,2:101/100000,3:102/100000,4:103/100000,5:104/100000,6:105/100000,7:106/100000,8:107/100000,9:108/100000,10:109/100000,11:110/100000,12:111/100000,13:112/100000,14:113/100000,15:114/100000]")!=std::string::npos);
 assert(lines[2]=="HDR10+ curve: knee=0/4095,0/4095 anchors=[1/1023,2/1023,3/1023,4/1023,5/1023,6/1023,7/1023,8/1023,9/1023,10/1023,11/1023,12/1023,13/1023,14/1023,15/1023]");
 invalid.StageNativeHDR10Plus(false);assert(lines.size()==3);

 lines.clear();DVBRIDGE::admit=false;CWinSystemGbmGLESContext denied;
 denied.m_videoSourceSideData->metadata=fixture();denied.StageNativeHDR10Plus(false);
 assert(lines.empty() && denied.m_hdr10plusReason.empty() && !denied.drm().packet);
 DVBRIDGE::admit=true;denied.StageNativeHDR10Plus(false);assert(lines.size()==3);

 lines.clear();CWinSystemGbmGLESContext unsupported;
 unsupported.display.version=0;unsupported.m_videoSourceSideData->metadata=fixture();
 unsupported.StageNativeHDR10Plus(false);assert(!unsupported.drm().packet && lines.size()==1);
 assert(lines[0].find("display-unsupported")!=std::string::npos);
 unsupported.m_videoSourceSideData->metadata.params[0].bezier_curve_anchors[8]={922,1023};
 const auto valid=unsupported.m_videoSourceSideData->metadata;
 unsupported.StageNativeHDR10Plus(false);assert(!unsupported.drm().packet && lines.size()==1);
 unsupported.display.version=1;unsupported.StageNativeHDR10Plus(true);unchanged(unsupported,valid);
 assert(unsupported.drm().packet && lines.size()==2 && lines[1].find("output: staged")!=std::string::npos);
 uint8_t expected[31];assert(cb1_hdr10plus_vsif(expected,&valid,true,true)==CB1_HDR10PLUS_OK);
 assert(!std::memcmp(unsupported.drm().packet->data(),expected,sizeof(expected)));
 unsupported.StageNativeHDR10Plus(true);assert(lines.size()==2);
}
'''.replace('BODY',stage)
        with tempfile.TemporaryDirectory(prefix='hdr10plus-diagnostics-') as temporary:
            folder=Path(temporary);source=folder/'check.cpp';obj=folder/'serializer.o';binary=folder/'check'
            source.write_text(program)
            flags=['-fsanitize=address,undefined','-fno-omit-frame-pointer',
                   '-I'+str(prefix/'include'),'-I'+str(repo/'CB1/src')]
            built=subprocess.run(['cc','-std=c11',*flags,'-c',str(repo/'CB1/src/cb1_hdr10plus.c'),
                                  '-o',str(obj)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            built=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-DFMT_HEADER_ONLY',
                *flags,'-idirafter',os.environ.get('CB1_FMT_INCLUDE','/usr/include'),str(source),str(obj),
                '-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_actual_progress_logger_uses_the_reserved_shared_slots(self):
        diagnostics.DiagnosticsRuntime().run_cpp(r'''
#include "utils/DVBridgeDiagnosticLog.h"
#include <cassert>
int main(){
 DVBRIDGE::DiagnosticOpen();DVBRIDGE::DiagnosticReserveProgress();
 for(unsigned i=0;i<18;i++)assert(DVBRIDGE::DiagnosticLog(LOGINFO,"detail {}",i));
 assert(!DVBRIDGE::DiagnosticLog(LOGINFO,"startup overflow"));
 for(unsigned i=0;i<6;i++)assert(DVBRIDGE::DiagnosticProgressLog(LOGINFO,"progress {}",i));
 assert(!DVBRIDGE::DiagnosticProgressLog(LOGINFO,"progress overflow"));
 assert(CLog::count==24);
}
''', {'utils/log.h':r'''
#pragma once
#include <fmt/format.h>
constexpr int LOGDEBUG=0,LOGINFO=1,LOGWARNING=2,LOGERROR=3;
struct CLog {
 inline static unsigned count{};
 template<class...T>static void Log(int,fmt::format_string<T...>,T&&...){++count;}
};
'''})

    def test_failed_emission_keeps_the_progress_deadline_eligible(self):
        diagnostics.DiagnosticsRuntime().run_cpp(r'''
#include "utils/DVBridgeDiagnosticState.h"
#include <cassert>
int main(){
 DVBRIDGE::DiagnosticInterval interval;
 assert(interval.Due(100));assert(interval.Due(100)); // Refused admission is retried.
 interval.Emitted(100);assert(!interval.Due(5099));assert(interval.Due(5100));
 assert(!interval.Due(99));
}
''')

    def test_configuration_log_identifies_expert_without_changing_the_signal(self):
        text=(diagnostics.TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        start=text.index('bool CWinSystemGbmGLESContext::ConfigureHDR10Conversion(')
        start=text.index('    if (m_dvSelection.policy.mode == DVBRIDGE_MODE_HDR10PLUS)',start)
        end=text.index('    if (m_hdrDeepColorPrevious)',start)
        diagnostics.DiagnosticsRuntime().run_cpp(r'''
#include <cassert>
#include <string>
#include <vector>
#include <fmt/format.h>
enum {LOGINFO,DVBRIDGE_MODE_HDR10PLUS=6,DVBRIDGE_MODE_HDR10_EXPERT=3};
namespace DVBRIDGE {
inline std::vector<std::string> lines;
template<class...T>void DiagnosticLog(int,fmt::format_string<T...> f,T&&...a){lines.push_back(fmt::format(f,std::forward<T>(a)...));}
}
struct Window {
 struct{struct{int mode;}policy;}m_dvSelection;
 struct{struct{struct{int max_luma=1000;}hdr;}target;struct{bool level6=true;}output;}session;
 int GetOutputBitDepth(){return 10;}bool UseLimitedColor(){return false;}
 void Report(int mode){m_dvSelection.policy.mode=mode;BLOCK}
};
int main(){Window w;w.Report(3);assert(DVBRIDGE::lines.back().find("policy=Expert")!=std::string::npos);
 assert(w.session.target.hdr.max_luma==1000);
 w.Report(2);assert(DVBRIDGE::lines.back().find("policy=Basic")!=std::string::npos);
 w.Report(6);assert(DVBRIDGE::lines.back().find("HDR10+ configured")!=std::string::npos);}
'''.replace('BLOCK',text[start:end]))

    def test_progress_reservation_preserves_the_shared_budget_and_stream_lifecycle(self):
        diagnostics.DiagnosticsRuntime().run_cpp(r'''
#include "utils/DVBridgeDiagnosticState.h"
#include <cassert>
int main(){
 using namespace DVBRIDGE;
 DiagnosticSession s;s.Observe(100,3,1,1,1,"analysis",true,false);s.ReserveProgress();
 unsigned normal=0;while(s.Admit(100,DiagnosticEvent::Normal))++normal;
 assert(normal==18);
 const auto progress=DiagnosticEvent::Progress;
 for(unsigned n=0;n<6;n++)assert(s.Admit(100+n*5000,progress));
 assert(!s.Admit(29999,progress));
 s.Observe(29999,3,2,2,2,"seek",true,false);
 assert(!s.Admit(29999,DiagnosticEvent::Normal));
 assert(s.Admit(30100,progress));
 assert(s.Admit(30100,DiagnosticEvent::Failure));
 assert(s.Admit(30100,DiagnosticEvent::Final));
 assert(!s.Admit(30101,DiagnosticEvent::Final));
 s.Observe(30200,4,1,1,1,"native",true,false);
 normal=0;while(s.Admit(30200,DiagnosticEvent::Normal))++normal;
 assert(normal==24); // Other streams retain their original capacity.
}
''')

    def test_each_phase_counts_unique_frames_and_separates_quantization_from_acceptance(self):
        diagnostics.DiagnosticsRuntime().run_cpp(r'''
#include "utils/DVBridgeDiagnosticState.h"
#include <cassert>
int main(){
 DVBRIDGE::DiagnosticFrames stats,generated,accepted;
 for(unsigned p=1;p<=3;p++){
  std::array<uint64_t,3> id{3,p,9};
  stats.Observe(id,100+p); // All three analyses differ.
  generated.Observe(id,p==3?200:199);
  generated.Observe(id,p==3?200:199); // Capture retry is not another frame.
  if(p!=3)accepted.Observe(id,199); // Third presentation rejected.
 }
 assert(stats.count==3 && stats.changes==2);
 assert(generated.count==3 && generated.changes==1);
 assert(accepted.count==2 && accepted.changes==0);
 assert((generated.identity==std::array<uint64_t,3>{3,3,9}));
 assert((accepted.identity==std::array<uint64_t,3>{3,2,9}));
 generated.Observe({0,0,0},1);assert(generated.count==3);
}
''')


if __name__=='__main__':
    unittest.main()
