"""Exercise actual SDR GUI blending over the final target, including legal range."""
import os
from pathlib import Path
import subprocess,tempfile,unittest
from shipped_kodi import shipped_code
from test_native_video_source import TREE,body

ROOT=Path(__file__).resolve().parents[2]

class SDRFinalGUI(unittest.TestCase):
    def test_target_gamma_range_orientation_and_repeated_overlay(self):
        code=(ROOT/'CB1/tests/gui_final_hdr10.cpp').read_text()
        code=code.replace('GUI_COMPOSITE_BODY',body(shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp'),
                           'void CWinSystemGbmGLESContext::CompositeGui()'))
        code=code.replace('GUI_SHADER_ENABLE_BODY',body(shipped_code('xbmc/rendering/gles/GuiCompositeShaderGLES.cpp'),
                           'bool CGuiCompositeShaderGLES::OnEnabled()'))
        code=code.replace('GUI_HDR_TARGET_BODY',body(shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h'),
                           'bool GetHDR10OutputTarget('))
        code=code.replace('for(unsigned bits:{10u,12u})for(bool limited:{false,true})for(bool inputPQ:{false,true})for(bool direct:{false,true}){',
                          'for(unsigned bits:{8u,10u,12u})for(bool limited:{false,true})for(float gamma:{2.2f,2.4f,2.6f}){ const bool inputPQ=false,direct=true;')
        code=code.replace('window.m_dvBridge->m_direct=direct;',
                          'window.m_dvBridge->m_direct=direct;window.m_compositeShader->m_ootfGamma=-gamma;')
        code=code.replace(':.8*alpha;',':std::pow(.5,1.0/gamma)*alpha;')
        self.assertEqual(code.count('std::pow(.5,1.0/gamma)*alpha'),2)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cpp=root/'test.cpp';cpp.write_text(code)
            built=subprocess.run(['c++','-std=c++20','-I'+str(ROOT/'CB1/src'),str(cpp),'-lEGL','-lGLESv2','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test'),str(TREE/'system/shaders/GLES/2.0/gles_gui_composite.frag')],
                               env=dict(os.environ,EGL_PLATFORM='surfaceless',LIBGL_ALWAYS_SOFTWARE='1'),capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)

if __name__=='__main__':unittest.main()
