"""Compile the real replayed kernel selectors, not a parallel policy model.

CB1_KERNEL_SOURCE must name Linux 7.2.6 with the shipped kernel patches applied.
No kernel build or GPU access is needed. The native DC global validation and
physical wire precision still require hardware qualification.
"""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


def function(source, name):
    match = re.search(r'^(?:static )?(?:inline )?(?:[\w]+\s+)+\*?' + name +
                      r'\([^;{]+\)\s*\{', source, re.M)
    if not match:
        raise AssertionError('Missing native function: ' + name)
    start, position, depth = match.start(), match.end(), 1
    while depth:
        depth += (source[position] == '{') - (source[position] == '}')
        position += 1
    return source[start:position]


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'),
                     'set CB1_KERNEL_SOURCE to the privately replayed pinned kernel')
class HDR10Transport(unittest.TestCase):
    def compile_run(self, code):
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'check.c', Path(directory)/'check'
            source.write_text(code)
            built = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_amd_rgb_first_then_deep_transport_without_changing_timing(self):
        root = Path(os.environ['CB1_KERNEL_SOURCE'])/'drivers/gpu/drm/amd/display/amdgpu_dm'
        dm = (root/'amdgpu_dm.c').read_text()
        dv = (root/'amdgpu_dm_dv.c').read_text()
        fill = function(dm, 'fill_stream_properties_from_drm_display_mode')
        # Execute the actual format/depth pipeline, stopping before color signalling.
        pipeline = fill.split('stream->out_transfer_func.tf = TRANSFER_FUNCTION_SRGB;', 1)[1]
        pipeline = pipeline.split('stream->output_color_space =', 1)[0]
        helper = (function(dm, 'amdgpu_dm_hdr10_select_format')
                  if 'static void amdgpu_dm_hdr10_select_format(' in dm else '')
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define EINVAL 22
#define BIT(n) (1U << (n))
#define min_t(t,a,b) ((t)((a)<(b)?(a):(b)))
typedef uint8_t u8;
enum { DRM_MODE_CONNECTOR_HDMIA=1, DRM_MODE_CONNECTOR_DisplayPort=2 };
enum { DRM_MODE_COLORIMETRY_BT2020_RGB=1, DRM_MODE_COLORIMETRY_BT2020_YCC=2 };
enum { HDMI_EOTF_SMPTE_ST2084=2, DRM_OUTPUT_COLOR_FORMAT_YCBCR422=3 };
enum { DRM_EDID_YCBCR420_DC_30=1, DRM_EDID_YCBCR420_DC_36=2, DRM_EDID_YCBCR420_DC_48=4 };
enum signal_type { SIGNAL_TYPE_HDMI_TYPE_A, SIGNAL_TYPE_DISPLAY_PORT };
enum dc_color_depth { COLOR_DEPTH_UNDEFINED, COLOR_DEPTH_666, COLOR_DEPTH_888,
 COLOR_DEPTH_101010, COLOR_DEPTH_121212, COLOR_DEPTH_141414, COLOR_DEPTH_161616,
 COLOR_DEPTH_999, COLOR_DEPTH_111111 };
enum { PIXEL_ENCODING_RGB, PIXEL_ENCODING_YCBCR422, PIXEL_ENCODING_YCBCR444, PIXEL_ENCODING_YCBCR420 };
struct hdr_output_metadata { int metadata_type; struct {int metadata_type,eotf;} hdmi_metadata_type1; };
struct drm_property_blob { size_t length; void *data; };
struct drm_display_info { unsigned color_formats; int max_tmds_clock,bpc; struct {unsigned y420_dc_modes;} hdmi;
 bool mode420,only420; };
struct drm_connector { int connector_type; struct drm_display_info display_info; };
struct amdgpu_dm_connector { struct drm_connector base; void *hdr10_deep_color_property; };
struct drm_connector_state { struct drm_connector *connector; void *crtc; unsigned max_requested_bpc;
 int colorspace; struct drm_property_blob *hdr_output_metadata; };
struct dm_connector_state { struct drm_connector_state base; bool hdr10_deep_color,dv_standard; };
struct dc_link { enum signal_type connector_signal; };
struct dc_crtc_timing { int pixel_encoding; enum dc_color_depth display_color_depth; unsigned pix_clk_100hz; };
struct dc_stream_state { enum signal_type signal; struct dc_link *link; struct dc_crtc_timing timing; bool dv_standard; };
struct drm_display_mode { int unused; };
struct drm_crtc_state {bool active;struct dc_stream_state *stream;};
struct drm_atomic_commit {struct drm_connector_state *con;struct drm_crtc_state *cs;};
#define to_dm_crtc_state(p) (p)
#define for_each_new_connector_in_state(s,c,con,i) \
 for((i)=0;(i)<1 && (((con)=(s)->con),((c)=(con)->connector),true);++(i))
static struct drm_crtc_state *drm_atomic_get_new_crtc_state(struct drm_atomic_commit *s,void *crtc)
{(void)crtc;return s->cs;}
#define to_amdgpu_dm_connector(p) ((struct amdgpu_dm_connector *)(p))
#define to_dm_connector_state(p) ((struct dm_connector_state *)(p))
static bool drm_mode_is_420_also(const struct drm_display_info *i,const struct drm_display_mode *m)
{(void)m;return i->mode420;}
static bool drm_mode_is_420_only(const struct drm_display_info *i,const struct drm_display_mode *m)
{(void)m;return i->only420;}
static bool drm_mode_is_420(const struct drm_display_info *i,const struct drm_display_mode *m)
{return drm_mode_is_420_also(i,m)||drm_mode_is_420_only(i,m);}
@@FUNCTIONS@@
static void native_format(struct dc_stream_state *stream,const struct drm_connector_state *connector_state,
 const struct drm_display_mode *mode_in,int requested_bpc) {
 struct dc_crtc_timing *timing_out=&stream->timing;
 const struct drm_display_info *info=&connector_state->connector->display_info;
 (void)requested_bpc;
 @@PIPELINE@@
}
int main(void) {
 struct amdgpu_dm_connector connector = {
  .base={.connector_type=DRM_MODE_CONNECTOR_HDMIA,
   .display_info={.color_formats=BIT(DRM_OUTPUT_COLOR_FORMAT_YCBCR422),.max_tmds_clock=600000,.bpc=10,
                  .hdmi={DRM_EDID_YCBCR420_DC_30},.mode420=true}},
  .hdr10_deep_color_property=&connector};
 struct hdr_output_metadata hdr={.metadata_type=0,.hdmi_metadata_type1={0,HDMI_EOTF_SMPTE_ST2084}};
 struct drm_property_blob blob={sizeof(hdr),&hdr};
 struct dm_connector_state state={.hdr10_deep_color=true,
  .base={.connector=&connector.base,.crtc=&state,.max_requested_bpc=10,
         .colorspace=DRM_MODE_COLORIMETRY_BT2020_RGB,.hdr_output_metadata=&blob}};
 struct dc_link link={SIGNAL_TYPE_HDMI_TYPE_A}; struct drm_display_mode mode={0};
 for (int scenario=0;scenario<29;++scenario) {
  struct amdgpu_dm_connector saved_connector=connector;
  struct dm_connector_state saved_state=state;
  struct dc_stream_state stream={.signal=SIGNAL_TYPE_HDMI_TYPE_A,.link=&link,
    .timing={PIXEL_ENCODING_RGB,COLOR_DEPTH_101010,5940000}};
  int requested=10,want_format=PIXEL_ENCODING_YCBCR422;
  enum dc_color_depth want_depth=COLOR_DEPTH_101010;
  if(scenario==1) {stream.timing.pix_clk_100hz=2970000;want_format=PIXEL_ENCODING_RGB;}
  if(scenario==2) {state.hdr10_deep_color=false;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==3) {state.dv_standard=true;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==4) {connector.base.display_info.color_formats=0;want_format=PIXEL_ENCODING_YCBCR420;}
  if(scenario==5) {connector.base.display_info.max_tmds_clock=340000;want_format=PIXEL_ENCODING_YCBCR420;want_depth=COLOR_DEPTH_888;}
  if(scenario==6) {connector.base.connector_type=DRM_MODE_CONNECTOR_DisplayPort;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==7) {link.connector_signal=SIGNAL_TYPE_DISPLAY_PORT;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==8) {state.base.hdr_output_metadata=NULL;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==9) {state.base.max_requested_bpc=8;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==10) {requested=8;stream.timing.display_color_depth=COLOR_DEPTH_888;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==11) {connector.base.display_info.color_formats=0;connector.base.display_info.hdmi.y420_dc_modes=0;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==12) {connector.base.display_info.color_formats=0;connector.base.display_info.mode420=false;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==13) {stream.signal=SIGNAL_TYPE_DISPLAY_PORT;want_format=PIXEL_ENCODING_RGB;}
  if(scenario==14) {connector.base.display_info.max_tmds_clock=0;connector.base.display_info.mode420=false;want_format=PIXEL_ENCODING_RGB;}
  if(scenario==15) {stream.timing.pixel_encoding=PIXEL_ENCODING_YCBCR444;want_format=PIXEL_ENCODING_YCBCR444;want_depth=COLOR_DEPTH_888;}
  if(scenario==16) {connector.hdr10_deep_color_property=NULL;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==17) {hdr.hdmi_metadata_type1.eotf=1;want_format=PIXEL_ENCODING_RGB;want_depth=COLOR_DEPTH_888;}
  if(scenario==18) {connector.base.display_info.mode420=false;connector.base.display_info.only420=true;want_format=PIXEL_ENCODING_YCBCR420;}
  if(scenario==19) {connector.base.display_info.mode420=false;connector.base.display_info.only420=true;stream.timing.pix_clk_100hz=2970000;want_format=PIXEL_ENCODING_YCBCR420;}
  if(scenario==20) {connector.base.display_info.mode420=false;connector.base.display_info.only420=true;connector.base.display_info.hdmi.y420_dc_modes=0;stream.timing.pix_clk_100hz=2970000;want_format=PIXEL_ENCODING_YCBCR420;want_depth=COLOR_DEPTH_888;}
  if(scenario==21) {connector.base.display_info.mode420=false;connector.base.display_info.only420=true;connector.base.display_info.max_tmds_clock=100000;stream.timing.pix_clk_100hz=2970000;want_format=PIXEL_ENCODING_YCBCR420;want_depth=COLOR_DEPTH_888;}
  if(scenario==22) {connector.base.display_info.mode420=false;connector.base.display_info.only420=true;connector.base.display_info.max_tmds_clock=0;stream.timing.pix_clk_100hz=2970000;want_format=PIXEL_ENCODING_YCBCR420;want_depth=COLOR_DEPTH_888;}
  if(scenario==23) {connector.base.display_info.max_tmds_clock=400000;connector.base.display_info.hdmi.y420_dc_modes=0;want_format=PIXEL_ENCODING_YCBCR420;want_depth=COLOR_DEPTH_888;}
  if(scenario==24) {state.hdr10_deep_color=false;connector.base.display_info.max_tmds_clock=400000;connector.base.display_info.hdmi.y420_dc_modes=0;want_format=PIXEL_ENCODING_YCBCR420;}
  if(scenario==25) {state.dv_standard=true;connector.base.display_info.max_tmds_clock=400000;connector.base.display_info.hdmi.y420_dc_modes=0;want_format=PIXEL_ENCODING_YCBCR420;}
  if(scenario==26) {stream.timing.pixel_encoding=PIXEL_ENCODING_YCBCR420;stream.timing.display_color_depth=COLOR_DEPTH_888;connector.base.display_info.max_tmds_clock=400000;want_format=PIXEL_ENCODING_YCBCR420;}
  if(scenario==27) {stream.timing.pixel_encoding=PIXEL_ENCODING_YCBCR420;connector.base.display_info.mode420=false;connector.base.display_info.max_tmds_clock=400000;want_format=PIXEL_ENCODING_YCBCR420;want_depth=COLOR_DEPTH_888;}
  if(scenario==28) {connector.base.display_info.max_tmds_clock=0;want_format=PIXEL_ENCODING_YCBCR420;want_depth=COLOR_DEPTH_888;}
  unsigned clock=stream.timing.pix_clk_100hz;
  native_format(&stream,&state.base,&mode,requested);
  if(stream.timing.pixel_encoding!=want_format || stream.timing.display_color_depth!=want_depth)
   return 10+scenario;
  assert(stream.timing.pix_clk_100hz==clock);
  if((scenario>=20 && scenario<=23) || scenario==27 || scenario==28) {
   struct drm_crtc_state cs={true,&stream};
   struct drm_atomic_commit commit={&state.base,&cs};
   assert(amdgpu_dm_hdr10_atomic_check(&commit)==-EINVAL);
  }
  connector=saved_connector;state=saved_state;link.connector_signal=SIGNAL_TYPE_HDMI_TYPE_A;
  hdr.hdmi_metadata_type1.eotf=HDMI_EOTF_SMPTE_ST2084;
 }
 /* The final atomic gate must inspect the post-DC actual depth, not max_bpc
  * or framebuffer format, including the out-of-order DC 9-bit enum. */
 struct dc_stream_state final={.signal=SIGNAL_TYPE_HDMI_TYPE_A,.link=&link,
   .timing={PIXEL_ENCODING_YCBCR422,COLOR_DEPTH_101010,5940000}};
 struct drm_crtc_state cs={true,&final};
 struct drm_atomic_commit commit={&state.base,&cs};
 assert(amdgpu_dm_hdr10_atomic_check(&commit)==0);
 final.timing.display_color_depth=COLOR_DEPTH_888;
 assert(amdgpu_dm_hdr10_atomic_check(&commit)==-EINVAL);
 final.timing.display_color_depth=COLOR_DEPTH_999;
 assert(amdgpu_dm_hdr10_atomic_check(&commit)==-EINVAL);
 final.timing.display_color_depth=COLOR_DEPTH_101010;
 final.dv_standard=true;
 assert(amdgpu_dm_hdr10_atomic_check(&commit)==-EINVAL);
 final.dv_standard=false;cs.active=false;
 assert(amdgpu_dm_hdr10_atomic_check(&commit)==-EINVAL);
 cs.active=true;final.link=NULL;
 assert(amdgpu_dm_hdr10_atomic_check(&commit)==-EINVAL);
 final.link=&link;state.hdr10_deep_color=false;
 final.timing.display_color_depth=COLOR_DEPTH_888;
 assert(amdgpu_dm_hdr10_atomic_check(&commit)==0);
}
'''
        functions = [function(dm, 'convert_color_depth_from_display_info'),
                     function(dm, 'adjust_colour_depth_from_display_info'),
                     function(dv, 'amdgpu_dm_hdr10_validate'),
                     function(dv, 'hdr10_depth'), function(dv, 'amdgpu_dm_hdr10_atomic_check')]
        code = code.replace('(void)requested_bpc;', '(void)requested_bpc; (void)drm_mode_is_420;')
        if helper:
            functions.append(helper)
        else:
            # The baseline pipeline has no retry; keep native conversion compiled
            # and used so a red result diagnoses RGB8 behavior, not missing symbols.
            code = code.replace('(void)requested_bpc;',
                                '(void)requested_bpc; (void)convert_color_depth_from_display_info;')
        self.compile_run(code.replace('@@FUNCTIONS@@', '\n'.join(functions))
                         .replace('@@PIPELINE@@', pipeline))

    def test_intel_native_rgb_then_420_obeys_edid_depth_and_link_limits(self):
        root = Path(os.environ['CB1_KERNEL_SOURCE'])/'drivers/gpu/drm/i915/display'
        source = (root/'intel_hdmi.c').read_text()
        policy = (root/'intel_dvbridge_hdr_policy.h').read_text()
        names = ('intel_hdmi_tmds_clock', 'intel_hdmi_source_bpc_possible',
                 'intel_hdmi_sink_bpc_possible', 'intel_hdmi_sink_format_valid',
                 'intel_hdmi_compute_bpc', 'intel_hdmi_compute_clock',
                 'intel_hdmi_output_format', 'intel_hdmi_compute_output_format',
                 'intel_dvbridge_hdr_deep_requested', 'intel_hdmi_compute_formats')
        config = function(source, 'intel_hdmi_compute_config')
        admission = config.split('/* This opt-in', 1)[1].split('pipe_config->has_audio', 1)[0]
        admission = '/* This opt-in' + admission
        final_guard = config.split('\tret = intel_hdmi_compute_formats(', 1)[1]
        final_guard = '\tret = intel_hdmi_compute_formats(' + final_guard.split('\n\tif (ret) {', 1)[0]
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#define EINVAL 22
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
#define DIV_ROUND_CLOSEST(a,b) (((a)+(b)/2)/(b))
#define DISPLAY_VER(d) ((d)->version)
#define HAS_GMCH(d) (false)
#define MISSING_CASE(x) ((void)(x))
#define drm_dbg_kms(d,...) ((void)(d))
#define drm_info(...) ((void)0)
#define __ratelimit(p) ((void)(p),false)
enum intel_output_format { INTEL_OUTPUT_FORMAT_RGB, INTEL_OUTPUT_FORMAT_YCBCR420 };
enum drm_mode_status { MODE_OK, MODE_NO_420, MODE_BAD };
enum { DRM_MODE_FLAG_DBLCLK=1, DRM_MODE_COLORIMETRY_BT2020_RGB=1, DRM_MODE_COLORIMETRY_BT2020_YCC=2,
 HDMI_EOTF_SMPTE_ST2084=2, DRM_EDID_YCBCR420_DC_30=1, DRM_EDID_YCBCR420_DC_36=2,
 DRM_EDID_HDMI_DC_30=1, DRM_EDID_HDMI_DC_36=2 };
struct hdr_output_metadata { int metadata_type; struct {int metadata_type,eotf;} hdmi_metadata_type1; };
struct drm_property_blob { size_t length; void *data; };
struct drm_hdmi_info {unsigned y420_dc_modes;};
struct drm_display_info {struct drm_hdmi_info hdmi;unsigned edid_hdmi_rgb444_dc_modes;
 int max_tmds_clock;bool also420,only420;};
struct drm_connector {struct drm_display_info display_info;bool ycbcr_420_allowed;};
struct intel_connector {struct drm_connector base;int dv_log_limit;};
struct drm_connector_state {struct drm_connector *connector;unsigned max_requested_bpc;int colorspace;
 struct drm_property_blob *hdr_output_metadata;};
struct intel_digital_connector_state {struct drm_connector_state base;bool dv_hdr10_deep_color,dv_lab_standard;};
struct drm_display_mode {int crtc_clock,flags;};
struct intel_display {int version;void *drm;};
struct intel_encoder {int limit;struct intel_connector *connector;};
struct intel_crtc_state {struct {struct drm_display_mode adjusted_mode;} hw;
 int pipe_bpp,port_clock;enum intel_output_format sink_format,output_format;bool has_hdmi_sink;
 struct intel_connector *connector;};
static struct intel_display display_state={.version=12};
#define to_intel_display(p) ((void)(p),&display_state)
#define to_intel_connector(p) ((struct intel_connector *)(p))
#define to_intel_digital_connector_state(p) ((struct intel_digital_connector_state *)(p))
#define enc_to_intel_hdmi(p) (p)
static bool drm_mode_is_420_also(const struct drm_display_info *i,const struct drm_display_mode *m)
{(void)m;return i->also420;}
static bool drm_mode_is_420_only(const struct drm_display_info *i,const struct drm_display_mode *m)
{(void)m;return i->only420;}
static bool drm_mode_is_420(const struct drm_display_info *i,const struct drm_display_mode *m)
{return drm_mode_is_420_also(i,m)||drm_mode_is_420_only(i,m);}
static enum drm_mode_status hdmi_port_clock_valid(struct intel_encoder *e,int clock,bool strict,bool hdmi)
{(void)hdmi;return clock<=e->limit && (!strict || clock<=e->connector->base.display_info.max_tmds_clock)?MODE_OK:MODE_BAD;}
static bool hdmi_bpc_possible(const struct intel_crtc_state *s,int bpc);
@@FUNCTIONS@@
static bool hdmi_bpc_possible(const struct intel_crtc_state *s,int bpc)
{return intel_hdmi_source_bpc_possible(&display_state,bpc) &&
 intel_hdmi_sink_bpc_possible(&s->connector->base,bpc,s->has_hdmi_sink,s->sink_format);}
static int native_config(struct intel_encoder *encoder,struct intel_crtc_state *pipe_config,
 const struct drm_connector_state *conn_state) {
 struct intel_display *display=&display_state;
 struct intel_connector *connector=encoder->connector;
 int ret;
 @@ADMISSION@@
 @@FINAL_GUARD@@
 return ret;
}
int main(void) {
 struct intel_connector connector={.base={.display_info={.hdmi={1},.edid_hdmi_rgb444_dc_modes=1,
   .max_tmds_clock=600000,.also420=true},.ycbcr_420_allowed=true}};
 struct hdr_output_metadata hdr={0,{0,HDMI_EOTF_SMPTE_ST2084}};
 struct drm_property_blob blob={sizeof(hdr),&hdr};
 struct intel_digital_connector_state state={.base={&connector.base,10,DRM_MODE_COLORIMETRY_BT2020_RGB,&blob},
   .dv_hdr10_deep_color=true};
 struct intel_encoder encoder={600000,&connector};
 for(int scenario=0;scenario<17;++scenario) {
  struct intel_connector saved_connector=connector;
  struct intel_digital_connector_state saved_state=state;
  struct intel_crtc_state stream={.hw={.adjusted_mode={594000,0}},.pipe_bpp=30,
    .has_hdmi_sink=true,.connector=&connector};
  int want_result=0;enum intel_output_format want_format=INTEL_OUTPUT_FORMAT_YCBCR420;
  int want_bpp=30;
  if(scenario==1) {stream.hw.adjusted_mode.crtc_clock=297000;want_format=INTEL_OUTPUT_FORMAT_RGB;}
  if(scenario==2) {state.dv_hdr10_deep_color=false;want_format=INTEL_OUTPUT_FORMAT_RGB;want_bpp=24;}
  if(scenario==3) {state.dv_lab_standard=true;want_result=-EINVAL;}
  if(scenario==4) {connector.base.display_info.hdmi.y420_dc_modes=0;want_result=-EINVAL;}
  if(scenario==5) {connector.base.display_info.also420=false;want_result=-EINVAL;}
  if(scenario==6) {connector.base.ycbcr_420_allowed=false;want_result=-EINVAL;}
  if(scenario==7) {connector.base.display_info.max_tmds_clock=340000;want_result=-EINVAL;}
  if(scenario==8) {encoder.limit=340000;want_result=-EINVAL;}
  if(scenario==9) {connector.base.display_info.only420=true;connector.base.display_info.also420=false;}
  if(scenario==10) {connector.base.display_info.only420=true;connector.base.display_info.hdmi.y420_dc_modes=0;want_result=-EINVAL;}
  if(scenario==11) {state.base.hdr_output_metadata=NULL;want_result=-EINVAL;}
  if(scenario==12) {state.base.max_requested_bpc=8;want_result=-EINVAL;}
  if(scenario==13) {stream.pipe_bpp=24;want_result=-EINVAL;}
  if(scenario==14) {display_state.version=11;want_result=-EINVAL;}
  if(scenario==15) {state.dv_hdr10_deep_color=false;state.dv_lab_standard=true;want_format=INTEL_OUTPUT_FORMAT_RGB;want_bpp=24;}
  if(scenario==16) {hdr.hdmi_metadata_type1.eotf=1;want_result=-EINVAL;}
  int clock=stream.hw.adjusted_mode.crtc_clock;
  int result=native_config(&encoder,&stream,&state.base);
  if(result!=want_result) return 20+scenario;
  if(!result && (stream.sink_format!=want_format || stream.pipe_bpp!=want_bpp)) return 50+scenario;
  assert(stream.hw.adjusted_mode.crtc_clock==clock);
  connector=saved_connector;state=saved_state;encoder.limit=600000;display_state.version=12;
  hdr.hdmi_metadata_type1.eotf=HDMI_EOTF_SMPTE_ST2084;
 }
}
'''
        functions = [function(policy, 'intel_dvbridge_hdr_retry_420')]
        functions.extend(function(source, name) for name in names)
        code = code.replace('struct intel_hdmi *intel_hdmi =', 'struct intel_encoder *intel_hdmi =')
        functions = [f.replace('struct intel_hdmi *intel_hdmi =',
                               'struct intel_encoder *intel_hdmi =') for f in functions]
        self.compile_run(code.replace('@@FUNCTIONS@@', '\n'.join(functions))
                         .replace('@@ADMISSION@@', admission)
                         .replace('@@FINAL_GUARD@@', final_guard))


if __name__ == '__main__':
    unittest.main()
