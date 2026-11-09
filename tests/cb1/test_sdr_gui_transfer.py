"""The real GUI LUT selector keeps SDR graphics in their target gamma."""
from pathlib import Path
import subprocess,tempfile,unittest
from test_native_video_source import TREE,body

class SDRGUITransferTests(unittest.TestCase):
    def test_sdr_gamma_never_enables_pq_or_hlg_gui_conversion(self):
        source=(TREE/'xbmc/rendering/gles/GuiCompositeShaderGLES.cpp').read_text()
        code=body(source,'bool CGuiCompositeShaderGLES::CreateLUTs(')
        self.assertTrue('AVCOL_TRC_GAMMA22' in code,'SDR GUI target must be explicitly supported')
        program=r'''
#include <cassert>
#include <cmath>
#include <vector>
constexpr int AVCOL_TRC_GAMMA22=4,AVCOL_TRC_SMPTE2084=16,AVCOL_TRC_ARIB_STD_B67=18;
constexpr int LOGERROR=1,LOGDEBUG=2;
struct CLog{template<typename...Args>static void Log(Args...){}};
unsigned deleted=0;
void glDeleteTextures(int,const unsigned*){++deleted;}
struct CGuiCompositeShaderGLES{
 unsigned m_lutDegammaTexId=0,m_lutTFTexId=0,pqCalls=0;float m_sdrPeak=.0203f,m_ootfGamma=0;
 static constexpr unsigned LUT_SIZE=256;
 unsigned CreateLUTTexture(const std::vector<float>&){return 1;}
 std::vector<float> GenerateDegammaLUT(){return {0,1};}
 std::vector<float> GeneratePQLUT(float){++pqCalls;return {0,1};}
 bool CreateLUTs(int colorTransfer,float sdrGamma=2.4f) BODY
};
int main(){
 CGuiCompositeShaderGLES shader;
 for(float gamma:{2.2f,2.4f,2.6f}){
  assert(shader.CreateLUTs(AVCOL_TRC_GAMMA22,gamma));
  assert(shader.m_ootfGamma==-gamma && !shader.m_lutTFTexId && shader.pqCalls==0);
 }
 assert(!shader.CreateLUTs(AVCOL_TRC_GAMMA22,NAN));
 assert(shader.CreateLUTs(AVCOL_TRC_SMPTE2084));assert(shader.m_ootfGamma==0 && shader.pqCalls==1);
 assert(shader.CreateLUTs(AVCOL_TRC_ARIB_STD_B67));assert(shader.m_ootfGamma==1.2f && !shader.m_lutTFTexId);
 assert(shader.CreateLUTs(AVCOL_TRC_GAMMA22,2.2f));assert(shader.m_ootfGamma==-2.2f && !shader.m_lutTFTexId);
}
'''.replace('BODY',code)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            result=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
