"""Exercise Vega M admission and native DCE colour programming without a GPU."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_VEGAM_SOURCE') or os.environ.get('CB1_KERNEL_SOURCE'),
                     'needs the patched Linux source')
class VegaMTransport(unittest.TestCase):
    def source(self, name):
        return (Path(os.environ.get('CB1_VEGAM_SOURCE') or os.environ['CB1_KERNEL_SOURCE']) /
                'drivers/gpu/drm/amd/display' / name).read_text()

    def run_c(self, code):
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp)/'test.c', Path(tmp)/'test'
            source.write_text(code)
            built = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_vegam_admitted_without_opening_other_dce_families(self):
        source = self.source('amdgpu_dm/amdgpu_dm_dv.c')
        name = 'dv_display_supported' if 'dv_display_supported(' in source else 'dv_dcn_supported'
        policy = function(source, name)
        symbols = sorted(set(re.findall(r'\b(?:DCN|DCE)_VERSION_\w+', policy)) |
                         {'DCE_VERSION_11_22', 'DCE_VERSION_11_2', 'DCE_VERSION_11_0',
                          'DCE_VERSION_12_0', 'DCE_VERSION_8_0'})
        code = '#include <assert.h>\n#include <stdbool.h>\nenum dce_version {' + ','.join(symbols) + '};\n'
        code += policy + '\nint main(void) {\n'
        for family, expected in [('DCE_VERSION_11_22', 'true'), ('DCE_VERSION_11_2', 'false'),
                                 ('DCE_VERSION_11_0', 'false'), ('DCE_VERSION_12_0', 'false'),
                                 ('DCE_VERSION_8_0', 'false'), ('DCN_VERSION_1_0', 'true'),
                                 ('DCN_VERSION_3_6', 'true')]:
            code += f'assert({name}({family}) == {expected});\n'
        self.run_c(code + 'return 0;}\n')

    def test_dv_bypasses_prescale_and_stale_lut_but_keeps_ordinary_programming(self):
        hwseq = self.source('dc/hwss/dce110/dce110_hwseq.c')
        ipp = self.source('dc/dce/dce_ipp.c')
        enum = re.search(r'enum ipp_prescale_mode\s*\{[^}]+};',
                         self.source('dc/inc/hw/ipp.h')).group()
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
@@ENUM@@
enum { SURFACE_PIXEL_FORMAT_GRPH_RGB565, SURFACE_PIXEL_FORMAT_GRPH_ARGB8888,
 SURFACE_PIXEL_FORMAT_GRPH_ABGR8888, SURFACE_PIXEL_FORMAT_GRPH_ARGB2101010,
 SURFACE_PIXEL_FORMAT_GRPH_ABGR2101010, SURFACE_PIXEL_FORMAT_GRPH_ARGB16161616,
 SURFACE_PIXEL_FORMAT_GRPH_ABGR16161616, SURFACE_PIXEL_FORMAT_GRPH_ABGR16161616F };
enum { TF_TYPE_PREDEFINED, TF_TYPE_BYPASS, TF_TYPE_DISTRIBUTED_POINTS };
enum { TRANSFER_FUNCTION_SRGB, TRANSFER_FUNCTION_BT709, TRANSFER_FUNCTION_LINEAR,
 TRANSFER_FUNCTION_PQ };
enum ipp_degamma_mode { IPP_DEGAMMA_MODE_HW_sRGB, IPP_DEGAMMA_MODE_HW_xvYCC,
 IPP_DEGAMMA_MODE_BYPASS };
struct ipp_prescale_params { enum ipp_prescale_mode mode; uint16_t bias, scale; };
struct dc_transfer_func { int type,tf; };
struct gamma { bool is_identity; };
struct dc_plane_state { int format; struct gamma gamma_correction;
 struct dc_transfer_func in_transfer_func; };
struct input_pixel_processor;
struct ipp_funcs {
 void (*ipp_program_prescale)(struct input_pixel_processor *,struct ipp_prescale_params *);
 void (*ipp_program_input_lut)(struct input_pixel_processor *,const struct gamma *);
 void (*ipp_set_degamma)(struct input_pixel_processor *,enum ipp_degamma_mode);
};
struct input_pixel_processor { const struct ipp_funcs *funcs; };
struct dce_ipp { int unused; };
struct dc_stream_state { bool dv_standard; };
struct pipe_ctx { struct { struct input_pixel_processor *ipp; } plane_res;
 struct dc_stream_state *stream; };
struct dc { int unused; };
static struct dce_ipp fake;
static int prescale_bypass,lut_bypass,lut_writes,degamma;
static void update(const char *field,int value) {
 if (!strcmp(field,"GRPH_PRESCALE_BYPASS")) prescale_bypass=value;
 if (!strcmp(field,"GRPH_INPUT_GAMMA_MODE")) lut_bypass=value;
}
#define ASSERT(x) assert(x)
#define TO_DCE_IPP(p) ((void)(p),&fake)
#define REG_UPDATE(reg,field,value) ((void)ipp_dce,update(#field,value))
#define REG_SET_2(reg,initial,f1,v1,f2,v2) ((void)ipp_dce,(void)(v1),(void)(v2))
static bool dce_use_lut(int format) { (void)format; return true; }
static void input_lut(struct input_pixel_processor *p,const struct gamma *g)
{ (void)p;(void)g; ++lut_writes; }
static void set_degamma(struct input_pixel_processor *p,enum ipp_degamma_mode mode)
{ (void)p; degamma=mode; }
@@FUNCTIONS@@
int main(void) {
 const struct ipp_funcs funcs={ dce_ipp_program_prescale,input_lut,set_degamma };
 struct input_pixel_processor ipp={&funcs};
 struct dc_stream_state stream={0};
 struct pipe_ctx pipe={.plane_res={&ipp},.stream=&stream};
 struct dc_plane_state plane={.format=SURFACE_PIXEL_FORMAT_GRPH_ARGB8888,
  .gamma_correction={true},.in_transfer_func={TF_TYPE_BYPASS,TRANSFER_FUNCTION_LINEAR}};
 assert(dce110_set_input_transfer_func(0,&pipe,&plane));
 assert(prescale_bypass==0 && lut_bypass==1 && lut_writes==0);
 stream.dv_standard=true;
 lut_bypass=0; prescale_bypass=0;
 assert(dce110_set_input_transfer_func(0,&pipe,&plane));
 assert(prescale_bypass==1 && lut_bypass==1 && lut_writes==0);
 assert(degamma==IPP_DEGAMMA_MODE_BYPASS);
 stream.dv_standard=false;
 assert(dce110_set_input_transfer_func(0,&pipe,&plane));
 assert(prescale_bypass==0 && lut_bypass==1);
 return 0;
}
'''
        funcs = '\n'.join([function(ipp, 'dce_ipp_program_prescale'),
                            function(hwseq, 'dce110_prescale_params'),
                            function(hwseq, 'dce110_set_input_transfer_func')])
        self.run_c(code.replace('@@ENUM@@', enum).replace('@@FUNCTIONS@@', funcs))

    def test_deep_output_is_independent_of_dv_on_vegam(self):
        source = self.source('amdgpu_dm/amdgpu_dm_dv.c')
        name = 'dv_display_supported' if 'dv_display_supported(' in source else 'dv_dcn_supported'
        policy = function(source, name)
        symbols = sorted(set(re.findall(r'\b(?:DCN|DCE)_VERSION_\w+', policy)))
        code = '#include <assert.h>\n#include <stdbool.h>\n#include <string.h>\n'
        code += 'enum dce_version {' + ','.join(symbols) + '};\n'
        code += r'''
enum { DRM_MODE_CONNECTOR_HDMIA=1, SIGNAL_TYPE_HDMI_TYPE_A=2, DRM_MODE_PROP_ATOMIC=4 };
struct dc_context { enum dce_version dce_version; };
struct dc { struct dc_context *ctx; };
struct amdgpu_device { struct { struct dc *dc; } dm; };
struct link { int connector_signal; };
struct amdgpu_dm_connector {
 struct { void *dev; int connector_type,base; } base;
 struct link *dc_link; void *dv_standard_property,*hdr10_deep_color_property;
};
static bool dv_standard;
static int dv_properties,hdr_properties;
#define drm_to_adev(p) ((struct amdgpu_device *)(p))
static void *drm_property_create_bool(void *dev,int flags,const char *name)
{ (void)dev;(void)flags; if (!strcmp(name,"DVBRIDGE_DV_STANDARD_LAB")) ++dv_properties;
 else if (!strcmp(name,"DVBRIDGE_HDR10_DEEP_COLOR")) ++hdr_properties;
 return &dv_properties; }
static void drm_object_attach_property(void *base,void *property,int value)
{ (void)base;(void)property;(void)value; }
'''
        code += policy + '\n' + function(source, 'amdgpu_dm_dv_attach')
        code += r'''
int main(void) {
 struct dc_context ctx={DCE_VERSION_11_22}; struct dc dc={&ctx};
 struct amdgpu_device dev={.dm={&dc}};
 struct link link={SIGNAL_TYPE_HDMI_TYPE_A};
 struct amdgpu_dm_connector con={.base={&dev,DRM_MODE_CONNECTOR_HDMIA,0},.dc_link=&link};
 dv_standard=true; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==1 && hdr_properties==1);
 dv_properties=hdr_properties=0; dv_standard=false; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==0 && hdr_properties==1);
 dv_properties=hdr_properties=0;
 ctx.dce_version=DCN_VERSION_1_0; dv_standard=true; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==1 && hdr_properties==1);
 dv_properties=hdr_properties=0; link.connector_signal=0; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==0 && hdr_properties==0);
 return 0;
}
'''
        self.run_c(code)

    def test_only_vegam_dv_uses_byte_depth_linebuffer(self):
        helper = function(self.source('dc/core/dc_resource.c'), 'resource_get_lb_depth')
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
enum { DCE_VERSION_11_2=112, DCE_VERSION_11_22=113, DCE_VERSION_MAX=200,
 DCN_VERSION_1_0=201 };
enum lb_pixel_depth { LB_PIXEL_DEPTH_24BPP=24, LB_PIXEL_DEPTH_30BPP=30,
 LB_PIXEL_DEPTH_36BPP=36 };
struct dc_context { int dce_version; };
struct dc_plane_state { struct dc_context *ctx; };
struct dc_stream_state { bool dv_standard; };
''' + helper + r'''
int main(void) {
 struct dc_context ctx={DCE_VERSION_11_22};
 struct dc_plane_state plane={&ctx}; struct dc_stream_state stream={false};
 assert(resource_get_lb_depth(&plane,&stream)==30);
 stream.dv_standard=true;
 assert(resource_get_lb_depth(&plane,&stream)==24);
 ctx.dce_version=DCE_VERSION_11_2;
 assert(resource_get_lb_depth(&plane,&stream)==30);
 ctx.dce_version=DCN_VERSION_1_0;
 assert(resource_get_lb_depth(&plane,&stream)==36);
 stream.dv_standard=false;
 assert(resource_get_lb_depth(&plane,&stream)==36);
 return 0;
}
''')


if __name__ == '__main__':
    unittest.main()
