"""Run SDR setup and admission against an SDR-only atomic display."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import body

ROOT=Path(__file__).resolve().parents[2]


class SDRDisplayTransitionTests(unittest.TestCase):
    def test_sdr_admission_uses_connected_progressive_mode_without_hdr_capabilities(self):
        patch=(ROOT/'projects/Generic/patches/kodi/kodi-9992-cb1-display.patch').read_text()
        source='\n'.join(line[1:] if line.startswith('+') else line for line in patch.splitlines())
        code=body(source,'bool CWinSystemGbmGLESContext::SupportsSDRConversion() const')
        program=r'''
#include <cassert>
#include <memory>
constexpr unsigned DRM_MODE_FLAG_INTERLACE=1,DRM_MODE_FLAG_DBLSCAN=2;
struct Mode{unsigned hdisplay=1920,vdisplay=1080,flags=0;};
struct Connector{bool connected=true;bool IsConnected(){return connected;}};
struct DRM{virtual ~DRM()=default;};
struct CDRMAtomic:DRM{Mode mode;Connector connector;bool selected=true;
 Mode* GetSelectedMode(){return selected?&mode:nullptr;}Connector* GetConnector(){return &connector;}};
struct CWinSystemGbmGLESContext{
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();
 bool SupportsSDRConversion() const BODY
};
int main(){
 CWinSystemGbmGLESContext window;auto drm=std::dynamic_pointer_cast<CDRMAtomic>(window.m_DRM);
 assert(window.SupportsSDRConversion());
 drm->mode={3840,2160,0};assert(window.SupportsSDRConversion());
 drm->connector.connected=false;assert(!window.SupportsSDRConversion());drm->connector.connected=true;
 drm->selected=false;assert(!window.SupportsSDRConversion());drm->selected=true;
 drm->mode.hdisplay=4096;assert(!window.SupportsSDRConversion());drm->mode.hdisplay=1920;
 for(unsigned flags:{DRM_MODE_FLAG_INTERLACE,DRM_MODE_FLAG_DBLSCAN}){
  drm->mode.flags=flags;assert(!window.SupportsSDRConversion());}
 window.m_DRM.reset();assert(!window.SupportsSDRConversion());
}
'''.replace('BODY',code)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            compiled=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_sdr_only_sink_clears_hdr_and_uses_existing_transaction_owner(self):
        patch=(ROOT/'projects/Generic/patches/kodi/kodi-9992-cb1-display.patch').read_text()
        source='\n'.join(line[1:] if line.startswith('+') else line for line in patch.splitlines())
        signature='bool CWinSystemGbmGLESContext::ConfigureSDRConversion('
        self.assertTrue(signature in source,'SDR needs its own signal setup without HDR sink admission')
        setup=body(source,signature)
        program=r'''
#include <cassert>
#include <array>
#include <cstdint>
#include <memory>
#include <optional>
#include <string>
constexpr int AVCOL_TRC_BT709=1,AVCOL_PRI_BT709=1,AVCOL_SPC_BT709=1;
struct VideoPicture{int color_transfer{},color_primaries{},color_space{},colorBits{};
 struct {uint64_t informationGeneration=11;} doviSourceInfo;};
struct Connector{bool hdr=false;bool SupportsProperty(const char*){return hdr;}};
struct DRM{virtual ~DRM()=default;};
struct CDRMAtomic:DRM{
 Connector connector;unsigned clears=0,plusClears=0,depthRestores=0;bool propertyOK=true;
 Connector* GetConnector(){return &connector;}
 bool AddProperty(Connector*,const char* name,uint64_t value){
  if(std::string(name)=="HDR_OUTPUT_METADATA"){assert(value==0);++clears;}
  else {assert(std::string(name)=="DVBRIDGE_HDR10_DEEP_COLOR");++depthRestores;}
  return propertyOK;
 }
 void StageHDR10Plus(std::optional<std::array<uint8_t,31>> packet,uint64_t generation){
  assert(!packet && generation==11);++plusClears;
 }
};
struct State{bool captured=false,stageOK=true;unsigned stages=0;
 bool Captured(){return captured;}bool Stage(CDRMAtomic&,bool restore){assert(restore);++stages;return stageOK;}};
struct CWinSystemGbmGLESContext{
 std::shared_ptr<DRM> m_DRM=std::make_shared<CDRMAtomic>();State m_dvState;
 bool pageOK=true,captureOK=true,beginOK=true,m_failedHDR10SetupRestore=false;
 unsigned captured=0,begun=0,sdrSignals=0,hdrClears=0;
 std::optional<uint64_t> m_hdrDeepColorPrevious;
 std::optional<int> m_hdr10Session=1,m_hdr10BasicSignal=1,m_hdr10Signal=1;
 uint64_t m_hdr10SessionStream=1;
 bool CompleteDVBridgePage(){return pageOK;}
 bool CaptureCB1ConnectorPreferences(){++captured;return captureOK;}
 bool BeginDVBridge(){++begun;return beginOK;}
 int GetOutputBitDepth(){return 8;}
 void SetColorimetry(const VideoPicture* value){assert(value && value->color_transfer==AVCOL_TRC_BT709 &&
  value->color_primaries==AVCOL_PRI_BT709 && value->color_space==AVCOL_SPC_BT709 && value->colorBits==8);++sdrSignals;}
 bool SetHDR(const VideoPicture* value){assert(!value);++hdrClears;return false;}
 bool ConfigureSDRConversion(const VideoPicture& picture) BODY
};
int main(){
 VideoPicture picture;CWinSystemGbmGLESContext window;
 auto drm=std::dynamic_pointer_cast<CDRMAtomic>(window.m_DRM);
 assert(window.ConfigureSDRConversion(picture));
 assert(window.captured==1 && window.begun==1 && window.hdrClears==1 && window.sdrSignals==1);
 assert(drm->clears==0 && drm->plusClears==1 && !window.m_failedHDR10SetupRestore);
 assert(!window.m_hdr10Session && !window.m_hdr10BasicSignal && !window.m_hdr10Signal && !window.m_hdr10SessionStream);
 drm->connector.hdr=true;window.m_dvState.captured=true;window.m_hdrDeepColorPrevious=0;
 assert(window.ConfigureSDRConversion(picture));
 assert(drm->clears==1 && drm->depthRestores==1 && window.m_dvState.stages==1);
 window.beginOK=false;assert(!window.ConfigureSDRConversion(picture));
 assert(window.m_failedHDR10SetupRestore); // Pending rollback survives setup rejection.
 window.m_failedHDR10SetupRestore=false;window.pageOK=false;
 auto previous=window.captured;assert(!window.ConfigureSDRConversion(picture));assert(window.captured==previous);
}
'''.replace('BODY',setup)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.cpp').write_text(program)
            compiled=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__':unittest.main()
