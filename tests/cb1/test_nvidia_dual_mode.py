"""Keep native DP distinct from a connected NVIDIA TMDS encoder."""
import subprocess
import tempfile
import unittest
from pathlib import Path
from test_native_video_source import TREE
from test_hdr10_transport import function
import test_nvidia_native_hdr as native_hdr


class NvidiaDualMode(unittest.TestCase):
    sources = native_hdr.NvidiaNativeHdr.sources

    def test_kodi_requires_the_live_native_tmds_proof(self):
        source=(TREE/'xbmc/windowing/gbm/drm/DVBridgeState.cpp').read_text()
        start=source.index('CDVBridgeState::Backend CDVBridgeState::GetBackend(')
        native=source[start:source.index('\nbool CDVBridgeState::Read(',start)]
        program=r'''
#include <cassert>
#include <string>
#include <optional>
struct CDRMConnector {
 std::string type="DP";bool kernel=false,vsif=true,bpc=true,dither=true,proof=true;
 unsigned value=1,cached=0;
 std::string GetType(){return type;}
 bool SupportsProperty(const std::string&name){
  if(name=="DVBRIDGE_DV_STANDARD_LAB")return kernel;
  if(name=="NV_HDMI_VSIF_METADATA")return vsif;
  if(name=="max bpc")return bpc;
  if(name=="dithering mode")return dither;
  if(name=="CB1_NATIVE_TMDS")return proof;
  return false;
 }
 std::optional<unsigned> GetPropertyValue(const std::string&name){
  if(name=="CB1_NATIVE_TMDS" && proof)return cached;
  return {};
 }
 std::optional<unsigned> ReadPropertyValue(const std::string&name){
  if(name=="CB1_NATIVE_TMDS" && proof)return value;
  return {};
 }
};
struct CDVBridgeState {enum class Backend{NONE,NVIDIA,KERNEL};static Backend GetBackend(CDRMConnector&);};
@@NATIVE@@
int main(){
 CDRMConnector c;using B=CDVBridgeState::Backend;
 assert(CDVBridgeState::GetBackend(c)==B::NVIDIA);
 c.value=0;c.cached=1;assert(CDVBridgeState::GetBackend(c)==B::NONE);
 c.value=1;c.proof=false;assert(CDVBridgeState::GetBackend(c)==B::NONE);
 c.proof=true;c.type="eDP";assert(CDVBridgeState::GetBackend(c)==B::NONE);
 c.type="HDMI-A";c.proof=false;assert(CDVBridgeState::GetBackend(c)==B::NVIDIA);
 c.vsif=false;assert(CDVBridgeState::GetBackend(c)==B::NONE);
 c.kernel=true;assert(CDVBridgeState::GetBackend(c)==B::KERNEL);
}
'''.replace('@@NATIVE@@',native)
        self.compile_run(program,cpp=True)

    def compile_run(self,program,cpp=False):
        with tempfile.TemporaryDirectory() as tmp:
            src,exe=Path(tmp)/('check.cpp' if cpp else 'check.c'),Path(tmp)/'check'
            src.write_text(program)
            build=subprocess.run(['c++' if cpp else 'cc','-std=c++17' if cpp else '-std=gnu11',
                '-Wall','-Wextra','-Werror',str(src),'-o',str(exe)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(exe)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_native_proof_tracks_the_connected_selected_encoder(self):
        for root in self.sources():
            source=(root/'kernel-open/nvidia-drm/nvidia-drm-connector.c').read_text()
            native='\n'.join(function(source,name) for name in
                            ('nv_drm_connector_hdmi_properties','nv_drm_connector_dual_tmds'))
            self.compile_run(r'''
#include <assert.h>
#include <stdbool.h>
enum {connector_status_connected=1,NVKMS_CONNECTOR_TYPE_HDMI=2,
 NVKMS_CONNECTOR_TYPE_DP=3,NVKMS_CONNECTOR_SIGNAL_FORMAT_TMDS=2,
 NVKMS_CONNECTOR_SIGNAL_FORMAT_DP=3};
struct drm_connector {int status;};
struct nv_drm_encoder {int signal_format;};
struct nv_drm_connector {struct drm_connector base;int type;bool internal;
 char dpAddress[8];struct nv_drm_encoder*nv_detected_encoder;};
#define to_nv_connector(c) ((struct nv_drm_connector*)(c))
@@NATIVE@@
int main(void){
 struct nv_drm_encoder tmds={2},dp={3},other={2};
 struct nv_drm_connector c={.base={1},.type=3,.nv_detected_encoder=&tmds};
 assert(nv_drm_connector_dual_tmds(&c.base,&tmds));
 assert(!nv_drm_connector_dual_tmds(&c.base,&other));
 c.base.status=0;assert(!nv_drm_connector_dual_tmds(&c.base,&tmds));
 c.base.status=1;c.nv_detected_encoder=&dp;
 assert(!nv_drm_connector_dual_tmds(&c.base,&dp));
 c.nv_detected_encoder=&tmds;c.internal=true;
 assert(!nv_drm_connector_dual_tmds(&c.base,&tmds));c.internal=false;
 c.dpAddress[0]='1';assert(!nv_drm_connector_dual_tmds(&c.base,&tmds));c.dpAddress[0]=0;
 c.type=2;assert(!nv_drm_connector_dual_tmds(&c.base,&tmds));
 c.type=3;assert(!nv_drm_connector_dual_tmds(&c.base,0));
}
'''.replace('@@NATIVE@@',native))

    def test_r615_flip_uses_raw_tmds_and_keeps_hdr_layer_conflicts(self):
        root=self.sources()[0]
        native=function((root/'src/nvidia-modeset/src/nvkms-hw-flip.c').read_text(),
                        'ValidateHdmiVsif')
        self.compile_run(r'''
#include <assert.h>
#include <stddef.h>
typedef int NvBool;typedef unsigned NvU32;
#define TRUE 1
#define FALSE 0
enum {NVKMS_CONNECTOR_TYPE_HDMI=2,NVKMS_CONNECTOR_TYPE_DP=3,
 NVKMS_CONNECTOR_SIGNAL_FORMAT_TMDS=2};
typedef struct {int type,signalFormat,dp;}NVConnectorEvoRec;
typedef struct {struct {int supportsGenericSharedInfoFrames;}caps;
 struct {unsigned numLayers;}head[1];}NVDevEvoRec;
typedef struct {struct {unsigned payloadSize;}hdmiVsifMetadata;
 struct {int enabled;}hdrInfoFrame;struct {struct {int enabled;}hdrStaticMetadata;}layer[1];}NVFlipEvoHwState;
static int nvConnectorUsesDPLib(const NVConnectorEvoRec*c){return c->dp;}
@@NATIVE@@
int main(void){
 NVDevEvoRec dev={.head={{1}}};NVConnectorEvoRec c={3,2,0};
 NVFlipEvoHwState frame={.hdmiVsifMetadata={27}};
 assert(ValidateHdmiVsif(&dev,0,&frame,&c));
 c.dp=1;assert(!ValidateHdmiVsif(&dev,0,&frame,&c));c.dp=0;
 c.signalFormat=3;assert(!ValidateHdmiVsif(&dev,0,&frame,&c));c.signalFormat=2;
 frame.hdrInfoFrame.enabled=1;assert(!ValidateHdmiVsif(&dev,0,&frame,&c));
 frame.hdrInfoFrame.enabled=0;frame.layer[0].hdrStaticMetadata.enabled=1;
 assert(!ValidateHdmiVsif(&dev,0,&frame,&c));
 frame.hdmiVsifMetadata.payloadSize=0;assert(ValidateHdmiVsif(&dev,0,&frame,&c));
}
'''.replace('@@NATIVE@@',native))


if __name__=='__main__': unittest.main()
