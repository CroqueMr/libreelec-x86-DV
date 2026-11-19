"""Strict DP HDR preserves native limits and matches NCL CSC to actual YUV."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelDpHdr(unittest.TestCase):
    def test_real_dp_link_selection_rejects_shallow_or_unsafe_retry(self):
        source=(Path(os.environ['CB1_KERNEL_SOURCE'])/
                'drivers/gpu/drm/i915/display/intel_dp.c').read_text()
        body=function(source,'intel_dp_compute_config')
        start=body.index('\t/*\n\t * Try to respect downstream TMDS clock limits')
        pipeline=body[start:body.index('\n\tret = intel_pfit_compute_config',start)]
        helper=(function(source,'intel_dp_hdr10_deep_requested')
                if 'intel_dp_hdr10_deep_requested(' in source else '')
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define EINVAL 22
#define DISPLAY_VER(d) ((d)->version)
enum port{PORT_A,PORT_B};
enum{HDMI_EOTF_SMPTE_ST2084=2,
 DRM_MODE_COLORIMETRY_BT2020_RGB,DRM_MODE_COLORIMETRY_BT2020_YCC};
struct hdr_output_metadata{unsigned metadata_type;struct{unsigned metadata_type,eotf;}hdmi_metadata_type1;};
struct drm_property_blob{size_t length;void*data;};
struct drm_connector_state{unsigned max_requested_bpc,colorspace;struct drm_property_blob*hdr_output_metadata;};
struct intel_digital_connector_state{struct drm_connector_state base;bool dv_hdr10_deep_color,dv_lab_standard;};
#define to_intel_digital_connector_state(p) ((const struct intel_digital_connector_state*)(p))
struct intel_display{int version;struct{bool haswell,broadwell;}platform;};
static struct intel_display display_fixture={.version=9};
#define to_intel_display(p) ((void)(p),&display_fixture)
struct intel_dp{bool edp,colorimetry_support;};
struct intel_encoder{int port;bool lspcon;void*devdata;struct intel_dp dp;};
#define enc_to_intel_dp(p) (&(p)->dp)
static bool intel_dp_is_edp(struct intel_dp*d){return d->edp;}
static bool intel_bios_encoder_is_lspcon(void*p){return *(bool*)p;}
struct intel_crtc_state{int pipe_bpp;};
@@HELPERS@@
static int calls,first_error,selected_bpp;
static int intel_dp_compute_formats(struct intel_encoder*e,struct intel_crtc_state*s,
 struct drm_connector_state*c,bool strict){(void)e;(void)c;calls++;s->pipe_bpp=selected_bpp;return strict?first_error:0;}
static int select_link(struct intel_encoder*encoder,struct intel_crtc_state*pipe_config,
 struct drm_connector_state*conn_state){int ret;
@@PIPELINE@@
 return 0;
}
int main(void){
 struct intel_encoder e={.port=PORT_B,.dp={false,true}};e.devdata=&e.lspcon;
 struct hdr_output_metadata hdr={0,{0,HDMI_EOTF_SMPTE_ST2084}};
 struct drm_property_blob blob={sizeof(hdr),&hdr};
 struct intel_digital_connector_state c={.base={10,DRM_MODE_COLORIMETRY_BT2020_RGB,&blob},.dv_hdr10_deep_color=true};
 struct intel_crtc_state s={0};
 for(int scenario=0;scenario<12;scenario++){
  struct intel_digital_connector_state saved=c;struct intel_encoder saved_e=e;
  calls=first_error=0;selected_bpp=30;int want=0;
  if(scenario==0){selected_bpp=24;want=-EINVAL;}
  if(scenario==1){first_error=-EINVAL;want=-EINVAL;}
  if(scenario==2){c.dv_hdr10_deep_color=false;selected_bpp=24;first_error=-EINVAL;}
  if(scenario==3){e.lspcon=true;want=-EINVAL;}
  if(scenario==4){e.dp.edp=true;want=-EINVAL;}
  if(scenario==5){e.dp.colorimetry_support=false;want=-EINVAL;}
  if(scenario==6){c.base.max_requested_bpc=8;want=-EINVAL;}
  if(scenario==7){hdr.hdmi_metadata_type1.eotf=0;want=-EINVAL;}
  if(scenario==8){c.base.hdr_output_metadata=NULL;want=-EINVAL;}
  if(scenario==9){c.base.colorspace=0;want=-EINVAL;}
  if(scenario==10){e.port=PORT_A;want=-EINVAL;}
  if(scenario==11){c.dv_lab_standard=true;want=-EINVAL;}
  assert(select_link(&e,&s,&c.base)==want);
  assert(calls==(scenario==2?2:1));
  c=saved;e=saved_e;e.devdata=&e.lspcon;hdr.hdmi_metadata_type1.eotf=HDMI_EOTF_SMPTE_ST2084;
 }
}
'''
        code=code.replace('@@HELPERS@@',function(source,'intel_dp_has_gamut_metadata_dip')+'\n'+helper)
        code=code.replace('@@PIPELINE@@',pipeline)
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.c';binary=Path(tmp)/'test';path.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror','-Wno-unused-function',
                str(path),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_native_vsc_bt2020_rgb_request_with_actual_yuv(self):
        source=(Path(os.environ['CB1_KERNEL_SOURCE'])/
                'drivers/gpu/drm/i915/display/intel_dp.c').read_text()
        code=r'''
#include <assert.h>
#include <stdbool.h>
enum{INTEL_OUTPUT_FORMAT_RGB,INTEL_OUTPUT_FORMAT_YCBCR444,INTEL_OUTPUT_FORMAT_YCBCR420};
enum{DRM_MODE_COLORIMETRY_BT709_YCC=1,DRM_MODE_COLORIMETRY_XVYCC_601,
 DRM_MODE_COLORIMETRY_XVYCC_709,DRM_MODE_COLORIMETRY_SYCC_601,DRM_MODE_COLORIMETRY_OPYCC_601,
 DRM_MODE_COLORIMETRY_BT2020_CYCC,DRM_MODE_COLORIMETRY_BT2020_RGB,DRM_MODE_COLORIMETRY_BT2020_YCC,
 DRM_MODE_COLORIMETRY_DCI_P3_RGB_D65,DRM_MODE_COLORIMETRY_DCI_P3_RGB_THEATER};
enum{DP_PIXELFORMAT_RGB,DP_PIXELFORMAT_YUV444,DP_PIXELFORMAT_YUV422,DP_PIXELFORMAT_YUV420};
enum{DP_COLORIMETRY_DEFAULT,DP_COLORIMETRY_BT709_YCC,DP_COLORIMETRY_XVYCC_601,
 DP_COLORIMETRY_XVYCC_709,DP_COLORIMETRY_SYCC_601,DP_COLORIMETRY_OPYCC_601,
 DP_COLORIMETRY_BT2020_RGB=6,DP_COLORIMETRY_BT2020_CYCC=6,DP_COLORIMETRY_BT2020_YCC=7,
 DP_COLORIMETRY_DCI_P3_RGB=8};
enum{DP_DYNAMIC_RANGE_CTA,DP_DYNAMIC_RANGE_VESA,DP_CONTENT_TYPE_NOT_DEFINED};
struct intel_display{void*drm;};static struct intel_display display_fixture;
#define to_intel_display(p) ((void)(p),&display_fixture)
static bool warning(void*d,bool b){(void)d;return b;}
#define drm_WARN_ON(d,b) warning(d,b)
struct intel_crtc_state{bool has_panel_replay,limited_color_range;int output_format,pipe_bpp;};
struct drm_connector_state{int colorspace;};
struct drm_dp_vsc_sdp{unsigned revision,length,pixelformat,colorimetry,bpc,dynamic_range,content_type;};
@@OWNER@@
int main(void){
 struct intel_crtc_state s={.pipe_bpp=30};
 struct drm_connector_state c={.colorspace=DRM_MODE_COLORIMETRY_BT2020_RGB};
 for(int fmt=0;fmt<3;fmt++){
  s.output_format=fmt;struct drm_dp_vsc_sdp v={0};intel_dp_compute_vsc_colorimetry(&s,&c,&v);
  assert(v.bpc==10 && v.colorimetry==(unsigned)(fmt==0?DP_COLORIMETRY_BT2020_RGB:DP_COLORIMETRY_BT2020_YCC));
 }
 c.colorspace=DRM_MODE_COLORIMETRY_BT2020_CYCC;
 struct drm_dp_vsc_sdp v={0};intel_dp_compute_vsc_colorimetry(&s,&c,&v);
 assert(v.colorimetry==DP_COLORIMETRY_BT2020_CYCC);
}
'''.replace('@@OWNER@@',function(source,'intel_dp_compute_vsc_colorimetry'))
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'test.c';binary=Path(tmp)/'test';path.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',str(path),
                '-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
