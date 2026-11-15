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
        code=code.replace('const float degamma[]={.5,.5,.5,1}',
                          'const float degamma[]={0,0,0,1, 1,1,1,1}')
        code=code.replace('degammaTexture=texture(1,1,degamma)', 'degammaTexture=texture(2,1,degamma)')
        code=code.replace('for(unsigned bits:{10u,12u})for(bool limited:{false,true})for(bool inputPQ:{false,true})for(bool direct:{false,true}){',
                          'for(unsigned bits:{8u,10u,12u})for(bool limited:{false,true})for(float gamma:{2.2f,2.4f,2.6f})for(bool wide:{false,true}){ const bool inputPQ=false,direct=true;')
        code=code.replace('window.m_dvBridge->m_direct=direct;',
                          'window.m_dvBridge->m_direct=direct;window.m_compositeShader->m_ootfGamma=-gamma;'
                          'window.m_sdrConversion=true;window.m_dvBridge->output.container.primaries='
                          'wide?PL_COLOR_PRIM_BT_2020:PL_COLOR_PRIM_BT_709;')
        code=code.replace('const double source=inputPQ?gui[sourceIndex*4+c]:.8*alpha;',
                          'const double source=expectedSDR(sourceIndex,c,alpha,gamma,wide);')
        code=code.replace('const double source=inputPQ?gui[j*4+c]:.8*alpha;',
                          'const double source=expectedSDR(j,c,alpha,gamma,wide);')
        code=code.replace('  unsigned failures=0;', r"""
  const auto expectedSDR=[&](unsigned pixel,unsigned channel,float alpha,float gamma,bool wide){
    // The 2x1 nearest-sampled degamma LUT maps channels below 0.5 to black.
    constexpr double matrix[3][3]={{.6274,.3293,.0433},{.0691,.9195,.0114},{.0164,.0880,.8956}};
    double light[3];
    for(unsigned c=0;c<3;c++)light[c]=gui[4*pixel+c]>=.5 ? 1 : 0;
    const double linear=wide?matrix[channel][0]*light[0]+matrix[channel][1]*light[1]+matrix[channel][2]*light[2]:light[channel];
    return std::pow(linear,1.0/gamma)*alpha;
  };
  unsigned failures=0;""")
        # The unrelated Player-Led test assumes the original constant LUT.
        code=code.replace('    film.fill(.2f);', '    return failures?1:0;\n    film.fill(.2f);', 1)
        self.assertEqual(code.count('const double source=expectedSDR'),2)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);cpp=root/'test.cpp';cpp.write_text(code)
            built=subprocess.run(['c++','-std=c++20','-I'+str(ROOT/'CB1/src'),str(cpp),'-lEGL','-lGLESv2','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test'),str(TREE/'system/shaders/GLES/2.0/gles_gui_composite.frag')],
                               env=dict(os.environ,EGL_PLATFORM='surfaceless',LIBGL_ALWAYS_SOFTWARE='1'),capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)

if __name__=='__main__':unittest.main()
