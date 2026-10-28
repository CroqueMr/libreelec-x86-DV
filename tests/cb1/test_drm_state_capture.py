"""Run shipped TV-Led capture and HDR10 admission against DRM boundary doubles."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

ROOT = Path(__file__).resolve().parents[2]


def source(relative):
    override = os.environ.get('CB1_DRM_STATE_SOURCE')
    if override:
        return (Path(override) / relative).read_text()
    patch = (ROOT / 'projects/Generic/patches/kodi/kodi-9990-native-dv.patch').read_text()
    section = patch.split('+++ b/' + relative + '\n', 1)[1]
    section = re.split(r'\n(?:diff --git |--- )', section, maxsplit=1)[0]
    return '\n'.join(line[1:] for line in section.splitlines() if line.startswith('+')) + '\n'


DRM_BOUNDARY = r'''
#pragma once
#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>
#include <utility>
#define CDRMConnector CDRMObject
constexpr unsigned DRM_MODE_ROTATE_0=1;
inline bool badBlob=false, badClone=false, badPlane=false, badResources=false;
inline unsigned clones=0;
inline std::vector<unsigned char> transportBytes;
struct Blob {unsigned length; void* data;};
inline unsigned char hdrBytes[]={1,2,3,4};
inline Blob original{4,hdrBytes};
inline Blob* drmModeGetPropertyBlob(int,unsigned) {return badBlob ? nullptr : &original;}
inline void drmModeFreePropertyBlob(Blob*) {}
struct Planes {unsigned count_planes=1; unsigned ids[1]={30}; unsigned* planes=ids;};
struct Plane {unsigned plane_id=30,crtc_id=59;};
inline Planes planes;
inline Plane plane;
inline Planes* drmModeGetPlaneResources(int) {return badResources ? nullptr : &planes;}
inline Plane* drmModeGetPlane(int,unsigned) {return badPlane ? nullptr : &plane;}
inline void drmModeFreePlane(Plane*) {}
inline void drmModeFreePlaneResources(Planes*) {}
namespace KODI::WINDOWING::GBM {
struct CDRMPropertyBlob {
  unsigned value=0;
  CDRMPropertyBlob()=default;
  CDRMPropertyBlob(int,const void* data,unsigned length) {
    if (!badClone && length==4 && data==hdrBytes) {value=777; ++clones;}
    if (!badClone && (length==27 || length==24)) {
      value=778; ++clones;
      auto* bytes=static_cast<const unsigned char*>(data);
      transportBytes.assign(bytes,bytes+length);
    }
  }
  CDRMPropertyBlob(const CDRMPropertyBlob&)=delete;
  CDRMPropertyBlob(CDRMPropertyBlob&& other) noexcept : value(std::exchange(other.value,0)) {}
  CDRMPropertyBlob& operator=(CDRMPropertyBlob&& other) noexcept {
    if(value) --clones;
    value=std::exchange(other.value,0); return *this;
  }
  ~CDRMPropertyBlob() {if(value) --clones;}
  bool IsValid() const {return value!=0;}
  unsigned Get() const {return value;}
};
struct CDRMObject {
  std::map<std::string,uint64_t> props;
  std::string badEnum;
  std::string connectorType="HDMI-A";
  std::optional<uint64_t> GetPropertyValue(const char* name) const {
    auto it=props.find(name); return it==props.end() ? std::nullopt : std::optional<uint64_t>(it->second);
  }
  bool SupportsProperty(const char* name) const {return props.contains(name);}
  bool IsConnected() const {return true;}
  std::optional<uint64_t> GetPropertyEnumValue(const char* name,const char*) const {
    return badEnum==name ? std::nullopt : GetPropertyValue(name);
  }
  unsigned GetId() const {return 30;}
  unsigned GetCrtcId() const {return 59;}
  std::string GetType() const {return connectorType;}
};
struct CDRMAtomic {
  CDRMObject connector{{{"DVBRIDGE_DV_STANDARD_LAB",0},{"max bpc",12},
                       {"Broadcast RGB",0},{"Colorspace",0},{"DVBRIDGE_HDR10_DEEP_COLOR",0}}, {}};
  CDRMObject crtc,plane;
  std::map<std::string,uint64_t> staged;
  CDRMObject* GetConnector() {return &connector;}
  CDRMObject* GetCrtc() {return &crtc;}
  CDRMObject* GetGuiPlane() {return &plane;}
  CDRMObject* GetVideoPlane() {return nullptr;}
  int GetFileDescriptor() const {return 4;}
  bool AddProperty(CDRMObject* object,const char* name,uint64_t value) {
    if(!object->props.contains(name)) return false;
    staged[name]=value; return true;
  }
};
}
'''


class DRMStateCaptureTests(unittest.TestCase):
    def test_missing_hdr10_property_allows_tv_led_but_not_hdr10_conversion(self):
        cpp = source('xbmc/windowing/gbm/drm/DVBridgeState.cpp')
        header = source('xbmc/windowing/gbm/drm/DVBridgeState.h')
        win_source = os.environ.get('CB1_DRM_STATE_SOURCE')
        if win_source:
            win = (Path(win_source) / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        else:
            win = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        admission = re.search(r'bool CWinSystemGbmGLESContext::SupportsHDR10Conversion.*?^}', win, re.S | re.M).group()
        program = r'''
#include <cassert>
#include "DVBridgeState.h"
#include "DRMAtomic.h"
using namespace KODI::WINDOWING::GBM;
struct CWinSystemGbmGLESContext {
  CDRMAtomic* m_DRM;
  bool hdr=true;
  bool IsHDRDisplay() const {return hdr;}
  bool FloatOutputUsable() const {return false;}
  struct Cap {bool SupportsHDR10() const {return true;}};
  Cap GetDisplayHDRCapabilities() const {return {};}
  bool SupportsDVOutputMode(bool) const {return true;}
  bool SupportsHDR10Conversion(bool requireCurrentMode);
};
''' + admission + r'''
int main() {
  CDRMAtomic drm;
  drm.connector.props["DVBRIDGE_HDR10_DEEP_COLOR"]=1;
  CDVBridgeState state;
  assert(state.Capture(drm));
  assert(std::string(state.CaptureFailure())=="none");
  assert(state.Stage(drm,false));
  assert(drm.staged.at("DVBRIDGE_DV_STANDARD_LAB")==1);
  assert(drm.staged.at("max bpc")==8);
  assert(drm.staged.at("DVBRIDGE_HDR10_DEEP_COLOR")==0);
  assert(!drm.staged.contains("HDR_OUTPUT_METADATA"));
  assert(state.Stage(drm,true));
  assert(drm.staged.at("DVBRIDGE_DV_STANDARD_LAB")==0);
  assert(drm.staged.at("max bpc")==12);
  assert(drm.staged.at("DVBRIDGE_HDR10_DEEP_COLOR")==1);
  CDRMAtomic other;
  assert(!state.Stage(other,false));
  CWinSystemGbmGLESContext window{&drm};
  assert(!window.SupportsHDR10Conversion(false));
  state.Restored();
  drm.connector.props["HDR_OUTPUT_METADATA"]=33;
  assert(window.SupportsHDR10Conversion(false));
  assert(state.Capture(drm) && clones==1);
  assert(state.Stage(drm,false) && drm.staged.at("HDR_OUTPUT_METADATA")==0);
  assert(state.Stage(drm,true) && drm.staged.at("HDR_OUTPUT_METADATA")==777);
  state.Restored(); assert(clones==0);
  drm.connector.props["HDR_OUTPUT_METADATA"]=0;
  assert(state.Capture(drm) && clones==0);
  assert(state.Stage(drm,false) && drm.staged.at("HDR_OUTPUT_METADATA")==0);
  assert(state.Stage(drm,true) && drm.staged.at("HDR_OUTPUT_METADATA")==0);
  state.Restored();
  drm.connector.props["HDR_OUTPUT_METADATA"]=33;
  badBlob=true;
  assert(!state.Capture(drm) && !state.Captured());
  assert(std::string(state.CaptureFailure())=="HDR_OUTPUT_METADATA");
  badBlob=false; badClone=true;
  assert(!state.Capture(drm) && !state.Captured());
  assert(std::string(state.CaptureFailure())=="HDR_OUTPUT_METADATA");
  badClone=false;
  drm.connector.props.erase("HDR_OUTPUT_METADATA");
  for (auto name : {"DVBRIDGE_DV_STANDARD_LAB", "max bpc", "Broadcast RGB", "Colorspace"}) {
    auto entry=drm.connector.props.extract(name);
    assert(!state.Capture(drm) && !state.Captured());
    assert(std::string(state.CaptureFailure())==name);
    drm.connector.props.insert(std::move(entry));
  }
  drm.connector.badEnum="Broadcast RGB";
  assert(!state.Capture(drm));
  assert(std::string(state.CaptureFailure())=="Broadcast RGB");
  drm.connector.badEnum.clear(); badPlane=true;
  assert(!state.Capture(drm));
  assert(std::string(state.CaptureFailure())=="plane-query");
  badPlane=false; badResources=true;
  assert(!state.Capture(drm));
  assert(std::string(state.CaptureFailure())=="plane-resources");
  badResources=false; plane.plane_id=31;
  assert(!state.Capture(drm));
  assert(std::string(state.CaptureFailure())=="active-plane");
  plane.plane_id=30;
  assert(state.Capture(drm));
  assert(std::string(state.CaptureFailure())=="none");
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name, content in {'DRMObject.h': DRM_BOUNDARY, 'DRMConnector.h': '#include "DRMObject.h"\n', 'DRMAtomic.h': '#include "DRMObject.h"\n',
                                  'DVBridgeState.h': header, 'DVBridgeState.cpp': cpp, 'check.cpp': program}.items():
                (folder / name).write_text(content)
            command = ['c++','-std=c++20','-Wall','-Wextra','-Werror','-I',temporary,
                       str(folder/'DVBridgeState.cpp'),str(folder/'check.cpp'),'-o',str(folder/'check')]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result = subprocess.run([str(folder/'check')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
