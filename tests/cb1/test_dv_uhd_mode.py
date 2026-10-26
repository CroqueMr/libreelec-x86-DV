"""CB1 uses the same Kodi mode selection as ordinary playback."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class DVUHDModeTests(unittest.TestCase):
    def test_real_selector_preserves_whitelist_override_and_adjustment_off(self):
        resolution = (TREE/'xbmc/windowing/Resolution.cpp').read_text()
        resolution = re.sub(r'^#include[^\n]*', '', resolution, flags=re.M)
        manager = body((TREE/'xbmc/cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text(),
                       'RESOLUTION CRenderManager::GetResolution()')
        gbm = (TREE/'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        eligible = body(gbm, 'bool NativeDVEligible(')
        wants = body(gbm, 'bool DVBRIDGE::WantsNativeOutput(const CDVDStreamInfo& stream)')
        program = r'''
#include "windowing/Resolution.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVPlaybackPolicy.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <limits>
#include <mutex>
#include <string>
#include <utility>
#include <vector>
constexpr uint32_t D3DPRESENTFLAG_INTERLACED=1, D3DPRESENTFLAG_MODE3DSBS=2,
 D3DPRESENTFLAG_MODE3DTB=4, D3DPRESENTFLAG_MODEMASK=7;
constexpr int LOGDEBUG=0, LOGINFO=1, STEREOSCOPIC_PLAYBACK_MODE_PREFERRED=1,
 STEREOSCOPIC_PLAYBACK_MODE_MONO=2, ADJUST_REFRESHRATE_OFF=0, STATE_UNCONFIGURED=0;
namespace MathUtils {
 bool FloatEquals(float a,float b,float epsilon){return std::abs(a-b)<epsilon;}
 int round_int(double value){return std::lround(value);}
}
struct CLog {template<class... T> static void Log(T&&...) {}};
struct CVariant {
 std::string value; CVariant(std::string v):value(std::move(v)){}
 std::string asString()const{return value;}
};
struct CSettings {
 static constexpr const char* SETTING_VIDEOSCREEN_WHITELIST="whitelist";
 static constexpr const char* SETTING_VIDEOPLAYER_STEREOSCOPICPLAYBACKMODE="stereo";
 static constexpr const char* SETTING_VIDEOPLAYER_ADJUSTREFRESHRATE="adjust";
 std::vector<CVariant> whitelist; int adjust=1;
 std::vector<CVariant> GetList(const char*)const{return whitelist;}
 bool GetBool(const char*)const{return false;}
 int GetInt(const char*)const{return adjust;}
};
struct RefreshOverride {bool fallback=false;float fpsmin=0,fpsmax=100,refreshmin=0,refreshmax=100;};
struct Advanced {
 bool m_stereoscopicPreferFramePacking=true;
 std::vector<RefreshOverride> m_videoAdjustRefreshOverrides;
};
struct Component {
 CSettings settings; Advanced advanced;
 CSettings* GetSettings(){return &settings;}
 Advanced* GetAdvancedSettings(){return &advanced;}
};
struct CDisplaySettings {
 std::vector<RESOLUTION_INFO> modes=std::vector<RESOLUTION_INFO>(RES_DESKTOP);
 static CDisplaySettings& GetInstance(){static CDisplaySettings d;return d;}
 const RESOLUTION_INFO& GetResolutionInfo(RESOLUTION r)const{return modes.at(r);}
 RESOLUTION GetCurrentResolution()const{return RES_DESKTOP;}
 RESOLUTION GetResFromString(const std::string& s)const{return static_cast<RESOLUTION>(std::stoi(s));}
 std::string GetStringFromRes(RESOLUTION r)const{return std::to_string(r);}
 size_t ResolutionInfoSize()const{return modes.size();}
};
struct CGraphicContext {
 RESOLUTION GetVideoResolution()const{return RES_DESKTOP;}
 const RESOLUTION_INFO& GetResInfo(RESOLUTION r)const{return CDisplaySettings::GetInstance().GetResolutionInfo(r);}
 void GetAllowedResolutions(std::vector<RESOLUTION>& out)const {
  for(size_t i=RES_DESKTOP;i<CDisplaySettings::GetInstance().modes.size();++i)
   out.push_back(static_cast<RESOLUTION>(i));
 }
 RenderStereoMode GetNextStereoMode()const{return RenderStereoMode::OFF;}
 bool IsFullScreenRoot()const{return true;}
};
struct Window {
 CGraphicContext gfx;CGraphicContext& GetGfxContext(){return gfx;}
 bool available=true;bool CanRetainDVSource()const{return available;}
};
using CWinSystemGbmGLESContext=Window;
struct Stereo {bool IsStereoModeSettled()const{return true;}};
struct GUI {Stereo stereo;Stereo& GetStereoscopicsManager(){return stereo;}};
struct CServiceBroker {
 static Window* GetWinSystem(){static Window w;return &w;}
 static Component* GetSettingsComponent(){static Component c;return &c;}
 static GUI* GetGUI(){static GUI g;return &g;}
};
constexpr int CODEC_FORCE_SOFTWARE=1;
class CDVDStreamInfo {
public:
 struct {int dv_profile=0;} dovi;
 int codecOptions=0;bool interlaced=false;std::string stereo_mode;
};
namespace DVBRIDGE {
 enum class OutputMode {Standard,Disabled};
 std::atomic<OutputMode> playbackMode{OutputMode::Standard};
}
bool NativeDVEligible(bool source,bool software,bool interlaced,bool stereo) ELIGIBLE_CODE
bool DVBRIDGE::WantsNativeOutput(const CDVDStreamInfo& stream) WANTS_CODE
RESOLUTION_CODE
struct CRenderManager {
 std::mutex m_statelock;int m_renderState=1;bool m_nativeDVRate=false;float m_fps=24000.f/1001;
 struct {int iWidth=3840,iHeight=2160;std::string stereoMode;} m_picture;
 RESOLUTION GetResolution() MANAGER_CODE
};
int main() {
 auto& modes=CDisplaySettings::GetInstance().modes;
 const float film=24000.f/1001;
 auto add=[&](int width,int height,float rate,uint32_t flags=0) {
  RESOLUTION_INFO info(width,height);info.fRefreshRate=rate;info.dwFlags=flags;
  modes.push_back(info);return static_cast<RESOLUTION>(modes.size()-1);
 };
 add(3840,2160,60);
 const auto dci=add(4096,2160,film);
 add(3840,2160,film,D3DPRESENTFLAG_INTERLACED);
 add(3840,2160,film,D3DPRESENTFLAG_MODE3DSBS);
 add(3840,2160,film,D3DPRESENTFLAG_MODE3DTB);
 add(3840,2160,120);add(3840,2160,144);add(3840,1080,film);
 const auto uhd=add(3840,2160,film);
 const auto fhd=add(1920,1080,film);
 add(3840,2160,24);
 const auto uhd25=add(3840,2160,25);
 const auto uhd30=add(3840,2160,30);
 add(3840,2160,60000.f/1001);add(3840,2160,60);
 auto& component=*CServiceBroker::GetSettingsComponent();
 CRenderManager manager;
 CDVDStreamInfo stream;
 assert(!DVBRIDGE::WantsNativeOutput(stream));
 stream.dovi.dv_profile=7;
 assert(DVBRIDGE::WantsNativeOutput(stream));
 stream.codecOptions=CODEC_FORCE_SOFTWARE;assert(!DVBRIDGE::WantsNativeOutput(stream));
 stream.codecOptions=0;stream.interlaced=true;assert(!DVBRIDGE::WantsNativeOutput(stream));
 stream.interlaced=false;stream.stereo_mode="left_right";assert(!DVBRIDGE::WantsNativeOutput(stream));
 stream.stereo_mode.clear();
 DVBRIDGE::playbackMode=DVBRIDGE::OutputMode::Disabled;
 assert(!DVBRIDGE::WantsNativeOutput(stream));
 DVBRIDGE::playbackMode=DVBRIDGE::OutputMode::Standard;
 for(bool whitelist:{false,true}) {
  component.settings.whitelist.clear();
  if(whitelist)component.settings.whitelist.emplace_back(std::to_string(fhd));
  for(float fps: {film,24.f,25.f,30.f,50.f,60000.f/1001,60.f})
   for(int width: {1280,1920,3840}) {
    manager.m_picture.iWidth=width;manager.m_picture.iHeight=width*9/16;manager.m_fps=fps;
    manager.m_nativeDVRate=false;const auto native=manager.GetResolution();
    manager.m_nativeDVRate=true;assert(manager.GetResolution()==native);
   }
 }
 manager.m_picture.iWidth=1920;manager.m_picture.iHeight=1080;manager.m_fps=film;
 manager.m_nativeDVRate=true;assert(manager.GetResolution()==fhd);
 component.advanced.m_videoAdjustRefreshOverrides.push_back({false,23,24,23,24});
 manager.m_nativeDVRate=false;const auto override=manager.GetResolution();
 manager.m_nativeDVRate=true;assert(manager.GetResolution()==override);
 component.settings.adjust=ADJUST_REFRESHRATE_OFF;
 assert(manager.GetResolution()==RES_DESKTOP && "CB1 must preserve native adjustment Off");
 manager.m_nativeDVRate=false;
 assert(manager.GetResolution()==RES_DESKTOP);
}
'''.replace('RESOLUTION_CODE', resolution).replace('MANAGER_CODE', manager).replace(
            'ELIGIBLE_CODE', eligible).replace('WANTS_CODE', wants)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-I'+str(TREE/'xbmc'),
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__': unittest.main()
