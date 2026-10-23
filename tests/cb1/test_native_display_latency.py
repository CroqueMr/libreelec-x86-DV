"""A synchronous native policy commit must not change the scheduler queue depth."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class NativeDisplayLatencyTests(unittest.TestCase):
    def test_native_policy_transition_keeps_configured_async_latency(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        function = body(source, 'float CWinSystemGbmGLESContext::GetDisplayLatency()')
        program = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <memory>
constexpr int DVBRIDGE_MODE_STANDARD=0,DVBRIDGE_MODE_MASTER_REFERENCE=4;
struct Cache {float GetVideoFps(){return 30;}};
struct CServiceBroker {static Cache& GetDataCacheCore(){static Cache c;return c;}};
struct DRM {struct Mode{float fRefreshRate=60;}mode;Mode GetCurrentMode(){return mode;}};
struct Context {bool enabled=true;uint64_t stream=1;
 bool AsyncPreparationConfigured() const {return enabled && stream;}};
struct Bridge {
 bool advanced=false;std::shared_ptr<Context> context=std::make_shared<Context>();
 bool Advanced(){return advanced;}
 auto GetContext(){return context;}
};
struct CWinSystemGbmEGLContext {float GetDisplayLatency(){return -1;}};
struct CWinSystemGbmGLESContext:CWinSystemGbmEGLContext {
 DRM drm;DRM* m_DRM=&drm;
 std::shared_ptr<Bridge> m_dvBridge=std::make_shared<Bridge>();
 bool active=true,available=true,m_hdrConversion=false;
 struct Selection {struct Policy{int mode=0;}policy;}m_dvSelection;
 bool CB1AsyncPlayback(){return active;}
 bool CB1AsyncAvailable(){return available;}
 float GetDisplayLatency() FUNCTION
};
int main(){
 CWinSystemGbmGLESContext active;assert(active.GetDisplayLatency()==50);
 for(int mode:{0,4}){
   CWinSystemGbmGLESContext transition;transition.active=false;
   transition.m_dvSelection.policy.mode=mode;
   assert(transition.GetDisplayLatency()==50);
 }
 // Stopped, disabled, advanced/conversion and unavailable paths keep native fallback.
 for(int scenario=0;scenario<8;++scenario){
   CWinSystemGbmGLESContext other;other.active=false;
   if(scenario==0)other.available=false;
   if(scenario==1)other.m_dvBridge->context->enabled=false;
   if(scenario==2)other.m_dvBridge->context->stream=0;
   if(scenario==3)other.m_dvBridge->advanced=true;
   if(scenario==4)other.m_hdrConversion=true;
   if(scenario==5)other.m_dvSelection.policy.mode=3;
   if(scenario==6)other.m_dvBridge->context.reset();
   if(scenario==7){other.available=false;other.m_dvBridge.reset();}
   assert(other.GetDisplayLatency()==-1);
 }
}
'''.replace('FUNCTION', function)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            build = subprocess.run(['c++', '-std=c++20', str(root/'test.cpp'), '-o', str(root/'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
