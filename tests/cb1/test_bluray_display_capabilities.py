"""Native GBM capabilities come from a full enumeration, before disc playback."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_native_video_source import TREE, body


class BlurayDisplayCapabilities(unittest.TestCase):
    def compile_run(self, code):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(code)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            checked = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(checked.returncode, 0, checked.stderr)

    def test_complete_gbm_mode_list_is_published_without_partial_catalogue(self):
        gbm = (TREE / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
        signature = 'uint32_t Bluray3DDisplayCapabilities('
        # Existing libbluray automatic 3D initialization advertises all four
        # capability bits. The missing GBM authority previously left that intact.
        caps = body(gbm, signature) if signature in gbm else '{return 0x0f;}'
        update = body(gbm, 'void CWinSystemGbm::UpdateResolutions()')
        self.compile_run(r'''
#include <atomic>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <functional>
#include <string>
#include <vector>
constexpr uint32_t D3DPRESENTFLAG_MODE3DSBS=1, D3DPRESENTFLAG_MODE3DTB=2, D3DPRESENTFLAG_INTERLACED=4;
constexpr int RES_DESKTOP=16, LOGINFO=0;
struct RESOLUTION_INFO {
 int iScreenWidth=1920,iScreenHeight=1080,iBlanking=0;
 float fRefreshRate=24000.f/1001;uint32_t dwFlags=0;int iWidth=1920,iHeight=1080;
 std::string StereoLayoutTag()const{return {};}
};
uint32_t Bluray3DDisplayCapabilities(const std::vector<RESOLUTION_INFO>& modes) CAPS
struct CLog {template<class... T>static void Log(T&&...){} };
struct CDisplaySettings {
 static inline std::function<void()> observer;
 static CDisplaySettings& GetInstance(){static CDisplaySettings s;return s;}
 void ClearCustomResolutions(){if(observer)observer();}
 void AddResolutionInfo(const RESOLUTION_INFO&){if(observer)observer();}
 RESOLUTION_INFO& GetResolutionInfo(int){static RESOLUTION_INFO r;return r;}
 void ApplyCalibrations(){}void UpdateCalibrations(){}
};
struct Window {Window& GetGfxContext(){return *this;}void ResetOverscan(RESOLUTION_INFO&){} };
struct CServiceBroker {static Window* GetWinSystem(){static Window w;return &w;} };
struct DRM {
 std::vector<RESOLUTION_INFO> modes;RESOLUTION_INFO current;
 auto GetCurrentMode(){return current;}auto GetModes(){return modes;}
};
struct CWinSystemGbm {
 DRM drm;DRM* m_DRM=&drm;std::atomic<uint32_t> m_bluray3DDisplayCapabilities{0};
 void UpdateResolutions() UPDATE
};
int main(){
 const RESOLUTION_INFO mono{1920,1080,0,24000.f/1001,0};
 const RESOLUTION_INFO fp{1920,2205,45,24000.f/1001,D3DPRESENTFLAG_MODE3DTB};
 const RESOLUTION_INFO ntsc720{1280,720,0,60000.f/1001,D3DPRESENTFLAG_MODE3DSBS};
 const RESOLUTION_INFO pal720{1280,1470,30,50,D3DPRESENTFLAG_MODE3DTB};
 assert(Bluray3DDisplayCapabilities({mono})==0 && "A mono GBM display must not inherit the automatic 0x0f");
 assert(Bluray3DDisplayCapabilities({})==0);
 assert(Bluray3DDisplayCapabilities({fp})==0);
 assert(Bluray3DDisplayCapabilities({ntsc720})==0);
 assert(Bluray3DDisplayCapabilities({fp,ntsc720})==1);
 assert(Bluray3DDisplayCapabilities({pal720})==2);
 assert(Bluray3DDisplayCapabilities({mono,fp,ntsc720,pal720})==3);
 auto integer24=fp;integer24.fRefreshRate=24;
 auto integer60=ntsc720;integer60.fRefreshRate=60;
 assert(Bluray3DDisplayCapabilities({integer24,ntsc720})==0);
 assert(Bluray3DDisplayCapabilities({fp,integer60})==0);
 auto interlaced=fp;interlaced.dwFlags|=D3DPRESENTFLAG_INTERLACED;
 assert(Bluray3DDisplayCapabilities({interlaced,ntsc720})==0);
 auto halfTB=fp;halfTB.iScreenHeight=1080;halfTB.iBlanking=0;
 assert(Bluray3DDisplayCapabilities({halfTB,ntsc720})==1);
 CWinSystemGbm output;output.drm.modes={mono,fp,ntsc720,pal720};
 unsigned duringPublication=0;
 CDisplaySettings::observer=[&]{++duringPublication;assert(output.m_bluray3DDisplayCapabilities.load()==3);};
 output.UpdateResolutions();assert(duringPublication>=5);
 CDisplaySettings::observer={};output.drm.modes={mono};output.UpdateResolutions();
 assert(output.m_bluray3DDisplayCapabilities.load()==0);
 // An empty enumeration must not reinterpret the current arrangement as a capability.
 output.drm.modes={fp,ntsc720,pal720};output.UpdateResolutions();
 assert(output.m_bluray3DDisplayCapabilities.load()==3);
 output.drm.modes={};output.drm.current=fp;output.UpdateResolutions();
 assert(output.m_bluray3DDisplayCapabilities.load()==0);
}
'''.replace('CAPS', caps).replace('UPDATE', update))

    def test_disc_overrides_only_authoritative_backend_after_auto_initialization(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp').read_text()
        opening = body(source, 'bool CDVDInputStreamBluray::Open()')
        signature = 'if (const auto* windowSystem = CServiceBroker::GetWinSystem())'
        apply = body(opening, signature) if signature in opening else '{}'
        base = (TREE / 'xbmc/windowing/WinSystem.h').read_text()
        gbm = (TREE / 'xbmc/windowing/gbm/WinSystemGbm.h').read_text()
        base_getter = body(base, 'virtual std::optional<uint32_t> GetBluray3DDisplayCapabilities() const')
        gbm_getter = body(gbm, 'std::optional<uint32_t> GetBluray3DDisplayCapabilities() const override')
        self.compile_run(r'''
#include <atomic>
#include <cassert>
#include <cstdint>
#include <optional>
constexpr uint32_t BLURAY_PLAYER_SETTING_DISPLAY_CAP=23;
constexpr int LOGERROR=0;
struct CLog{template<class... T>static void Log(T&&...){} };
struct Player {uint32_t display=15,player=0xffffffff,profile=0x130240;bool accept=true;};
bool bd_set_player_setting(Player* p,uint32_t index,uint32_t value){
 assert(index==23);if(!p->accept)return false;p->display=value;return true;
}
struct Window {virtual ~Window()=default;virtual std::optional<uint32_t> GetBluray3DDisplayCapabilities()const BASEGETTER};
struct GBMWindow:Window {
 std::atomic<uint32_t> m_bluray3DDisplayCapabilities{0};
 std::optional<uint32_t> GetBluray3DDisplayCapabilities()const override GBMGETTER
};
struct CServiceBroker {static inline Window* current=nullptr;static auto* GetWinSystem(){return current;}};
bool apply(Player* m_bd){if(const auto* windowSystem=CServiceBroker::GetWinSystem()) APPLY return true;}
int main(){
 Player absent;assert(apply(&absent) && absent.display==15);
 Window other;CServiceBroker::current=&other;Player p;
 assert(apply(&p) && p.display==15);
 for(uint32_t caps:{0u,1u,2u,3u}){
  GBMWindow gbm;gbm.m_bluray3DDisplayCapabilities.store(caps);CServiceBroker::current=&gbm;Player p;
  assert(apply(&p) && p.display==caps && p.player==0xffffffff && p.profile==0x130240);
  p.accept=false;assert(!apply(&p));
 }
}
'''.replace('APPLY', apply).replace('BASEGETTER', base_getter).replace('GBMGETTER', gbm_getter))
        self.assertLess(opening.index('bd_get_disc_info'), opening.index(signature))
        self.assertLess(opening.index(signature), opening.index('bd_play('))


if __name__ == '__main__':
    unittest.main()
