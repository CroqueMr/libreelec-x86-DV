"""Execute shipped output-state code with a NVIDIA DRM property boundary."""
from pathlib import Path
import subprocess
import os
import re
import tempfile
import unittest
from test_drm_state_capture import DRM_BOUNDARY, source


class NvidiaOutput(unittest.TestCase):
    def test_transport_capture_and_exact_restore(self):
        program = r'''
#include <cassert>
#include "DVBridgeState.h"
#include "DRMAtomic.h"
using namespace KODI::WINDOWING::GBM;
struct DisplayInfo {
  bool dv=true, qs=true;
  bool SupportsStandardDolbyVision() const {return dv;}
  bool SupportsRGBQuantizationSelection() const {return qs;}
};
struct CWinSystemGbm {
  std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
  std::shared_ptr<DisplayInfo> m_info=std::make_shared<DisplayInfo>();
  bool SupportsDVOutputMode(bool) const {return true;}
  bool SupportsNativeDVOutput(bool requireCurrentMode) const;
};
@ADMISSION@
struct CWinSystemGbmGLESContext : CWinSystemGbm {
  bool IsHDRDisplay() const {return true;}
  struct Cap {bool SupportsHDR10() const {return true;}};
  Cap GetDisplayHDRCapabilities() const {return {};}
  bool FloatOutputUsable() const {return floatUsable;}
  bool floatUsable=false;
  bool SupportsHDR10Conversion(bool);
};
@HDR_ADMISSION@
int main() {
  CDRMAtomic drm;
  drm.connector.props={{"NV_HDMI_VSIF_METADATA",0},{"max bpc",12},
      {"dithering mode",1},{"Colorspace",0},{"HDR_OUTPUT_METADATA",33},
      {"DVBRIDGE_HDR10_DEEP_COLOR",1}};
  drm.crtc.props={{"NV_CRTC_REGAMMA_DIVISOR",17}};
  drm.plane.props={{"NV_PLANE_DEGAMMA_MULTIPLIER",19}};
  CDVBridgeState state;
  assert(state.Capture(drm));
  assert(state.Stage(drm,false));
  assert(drm.staged.at("max bpc")==8);
  assert(drm.staged.at("DVBRIDGE_HDR10_DEEP_COLOR")==0);
  assert(drm.staged.at("NV_HDMI_VSIF_METADATA")==778);
  assert(transportBytes.size()==27 && transportBytes[0]==0x46 &&
      transportBytes[1]==0xd0 && transportBytes[2]==0 && transportBytes[3]==2);
  for(unsigned i=4;i<27;++i) assert(transportBytes[i]==0);
  assert(drm.staged.at("NV_CRTC_REGAMMA_DIVISOR")==4294967296ULL);
  assert(state.Stage(drm,true));
  assert(drm.staged.at("max bpc")==12);
  assert(drm.staged.at("DVBRIDGE_HDR10_DEEP_COLOR")==1);
  assert(drm.staged.at("NV_HDMI_VSIF_METADATA")==0);
  assert(drm.staged.at("HDR_OUTPUT_METADATA")==777);
  assert(drm.staged.at("NV_CRTC_REGAMMA_DIVISOR")==17);
  assert(drm.staged.at("NV_PLANE_DEGAMMA_MULTIPLIER")==19);
  state.Restored(); assert(clones==0);
  assert(state.Capture(drm,0,true));
  assert(transportBytes.size()==24 && transportBytes[0]==3 &&
      transportBytes[1]==12 && transportBytes[2]==0);
  for(unsigned i=3;i<24;++i) assert(transportBytes[i]==0);
  assert(state.Stage(drm,false) && state.Stage(drm,true));
  state.Restored(); assert(clones==0);
  assert(state.Capture(drm));
  assert(transportBytes.size()==27 && transportBytes[0]==0x46 &&
      transportBytes[1]==0xd0 && transportBytes[3]==2);
  state.Restored(); assert(clones==0);
  drm.connector.props["NV_HDMI_VSIF_METADATA"]=123;
  assert(!state.Capture(drm) && clones==0);
  drm.connector.props["NV_HDMI_VSIF_METADATA"]=0;
  for (auto name : {"dithering mode","max bpc","HDR_OUTPUT_METADATA","Colorspace"}) {
    auto entry=drm.connector.props.extract(name);
    assert(!state.Capture(drm) && !state.Captured() && clones==0);
    drm.connector.props.insert(std::move(entry));
  }
  drm.connector.connectorType="DP";
  assert(!state.Capture(drm));
  drm.connector.connectorType="HDMI-A";
  badClone=true; assert(!state.Capture(drm) && clones==0); badClone=false;
  drm.connector.badEnum="dithering mode";
  assert(!state.Capture(drm) && clones==0); drm.connector.badEnum.clear();
  for (unsigned i=0;i<50;++i) {
    assert(state.Capture(drm));
    CDRMAtomic foreign; assert(!state.Stage(foreign,true));
    assert(state.Stage(drm,false) && state.Stage(drm,true));
    state.Restored(); assert(clones==0);
    assert(state.CapturedBackend()==CDVBridgeState::Backend::NONE);
  }
  CWinSystemGbm window;
  window.m_DRM->connector.props={{"NV_HDMI_VSIF_METADATA",0},{"max bpc",12},
      {"dithering mode",1},{"Colorspace",0},{"HDR_OUTPUT_METADATA",0}};
  assert(window.SupportsNativeDVOutput(false));
  window.m_info->qs=false;
  assert(!window.SupportsNativeDVOutput(false));
  window.m_DRM->connector.props["DVBRIDGE_DV_STANDARD_LAB"]=0;
  assert(window.SupportsNativeDVOutput(false));
  window.m_info->dv=false;
  assert(!window.SupportsNativeDVOutput(false));
  CWinSystemGbmGLESContext hdr;
  hdr.m_DRM->connector.props={{"NV_HDMI_VSIF_METADATA",0},{"max bpc",12},
      {"dithering mode",1},{"Colorspace",0},{"HDR_OUTPUT_METADATA",0}};
  assert(!hdr.SupportsHDR10Conversion(false));
  hdr.floatUsable=true;
  assert(hdr.SupportsHDR10Conversion(false));
  hdr.m_DRM->connector.connectorType="DP";
  hdr.m_DRM->connector.props.erase("NV_HDMI_VSIF_METADATA");
  assert(hdr.SupportsHDR10Conversion(false));
  hdr.m_DRM->connector.props.erase("HDR_OUTPUT_METADATA");
  assert(!hdr.SupportsHDR10Conversion(false));
}
'''
        from shipped_kodi import shipped_code
        override = os.environ.get('CB1_DRM_STATE_SOURCE')
        win = ((Path(override) / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
               if override else shipped_code('xbmc/windowing/gbm/WinSystemGbm.cpp'))
        admission = re.search(r'bool CWinSystemGbm::SupportsNativeDVOutput.*?^}',win,re.S|re.M).group()
        program = '#include <memory>\n' + program.replace('@ADMISSION@',admission)
        path='xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp'
        win=(Path(override)/path).read_text() if override else shipped_code(path)
        hdr=re.search(r'bool CWinSystemGbmGLESContext::SupportsHDR10Conversion.*?^}',win,re.S|re.M).group()
        program=program.replace('@HDR_ADMISSION@',hdr)
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            files = {'DRMObject.h': DRM_BOUNDARY,
                     'DRMConnector.h': '#include "DRMObject.h"\n',
                     'DRMAtomic.h': '#include "DRMObject.h"\n',
                     'DVBridgeState.cpp': source('xbmc/windowing/gbm/drm/DVBridgeState.cpp'),
                     'DVBridgeState.h': source('xbmc/windowing/gbm/drm/DVBridgeState.h'),
                     'check.cpp': program}
            for name, content in files.items():
                (folder / name).write_text(content)
            result = subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-I',directory,str(folder/'DVBridgeState.cpp'),str(folder/'check.cpp'),
                '-o',str(folder/'check')], capture_output=True, text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result = subprocess.run([str(folder/'check')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
