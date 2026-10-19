"""New modes must be selected before restoring the NVIDIA transport."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code


class NvidiaModeRestore(unittest.TestCase):
    def test_restore_joins_selected_mode_and_rolls_back_on_refusal(self):
        path='xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp'
        root=os.environ.get('CB1_DRM_STATE_SOURCE')
        source=(Path(root)/path).read_text() if root else shipped_code(path)
        found=re.search(r'bool CWinSystemGbmGLESContext::PrepareNvidiaModeRestore.*?^}',source,re.S|re.M)
        self.assertIsNotNone(found,'joined NVIDIA mode restoration is missing')
        program=r'''
#include <cassert>
struct RESOLUTION_INFO {int id=1;};
struct CDVBridgeState {enum class Backend {KERNEL,NVIDIA}; Backend backend=Backend::NVIDIA;
 Backend CapturedBackend() const {return backend;}};
struct DRM {RESOLUTION_INFO mode; bool accepts=true; int staged=1;
 RESOLUTION_INFO GetCurrentMode() const {return mode;}
 bool SetMode(const RESOLUTION_INFO& value) {if(!accepts && value.id==2)return false;mode=value;return true;}
 bool SetVideoMode(const RESOLUTION_INFO& value,void*) {staged=value.id;return true;}};
struct CWinSystemGbmGLESContext {
 CDVBridgeState m_dvState; DRM drm; DRM* m_DRM=&drm; bool restore=true; int observed=0;
 bool EndDVBridge(){observed=drm.staged;return restore;}
 bool PrepareNvidiaModeRestore(const RESOLUTION_INFO&);
};
METHOD
int main(){
 CWinSystemGbmGLESContext w;RESOLUTION_INFO next{2};
 assert(w.PrepareNvidiaModeRestore(next) && w.observed==2);
 w.drm.mode={1};w.drm.staged=1;w.restore=false;
 assert(!w.PrepareNvidiaModeRestore(next) && w.drm.mode.id==1 && w.drm.staged==1);
 w.restore=true;w.drm.accepts=false;
 assert(!w.PrepareNvidiaModeRestore(next) && w.drm.mode.id==1);
 w.m_dvState.backend=CDVBridgeState::Backend::KERNEL;
 assert(w.PrepareNvidiaModeRestore(next) && w.drm.mode.id==1);
}
'''.replace('METHOD',found.group())
        with tempfile.TemporaryDirectory() as directory:
            code=Path(directory)/'check.cpp';code.write_text(program)
            binary=Path(directory)/'check'
            built=subprocess.run(['c++','-std=c++20',str(code),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
