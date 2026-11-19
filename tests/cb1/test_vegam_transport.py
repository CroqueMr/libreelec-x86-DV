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
enum {DCE_VERSION_11_22=1122};
struct dc_context {int dce_version;};
struct input_pixel_processor { const struct ipp_funcs *funcs; struct dc_context *ctx; };
struct dce_ipp { bool dv_csc_saved; uint32_t dv_csc_mode; };
struct dc_stream_state { bool dv_standard,dv_native_lldv; };
struct pipe_ctx { struct { struct input_pixel_processor *ipp; } plane_res;
 struct dc_stream_state *stream; };
struct dc { int unused; };
static struct dce_ipp fake;
static int prescale_bypass,lut_bypass,lut_writes,degamma,prescale_scale;
static void update(const char *field,int value) {
 if (!strcmp(field,"GRPH_PRESCALE_BYPASS")) prescale_bypass=value;
 if (!strcmp(field,"GRPH_INPUT_GAMMA_MODE")) lut_bypass=value;
}
#define ASSERT(x) assert(x)
#define TO_DCE_IPP(p) ((void)(p),&fake)
#define REG(r) 0
#define REG_GET(r,f,p) ((void)(p))
#define REG_UPDATE(reg,field,value) ((void)ipp_dce,update(#field,value))
#define REG_SET_2(reg,initial,f1,v1,f2,v2) ((void)ipp_dce,prescale_scale=(v1),(void)(v2))
static bool dce_use_lut(int format) { (void)format; return true; }
static void input_lut(struct input_pixel_processor *p,const struct gamma *g)
{ (void)p;(void)g; ++lut_writes; }
static void set_degamma(struct input_pixel_processor *p,enum ipp_degamma_mode mode)
{ (void)p; degamma=mode; }
@@FUNCTIONS@@
int main(void) {
 const struct ipp_funcs funcs={ dce_ipp_program_prescale,input_lut,set_degamma };
 struct dc_context context={0};
 struct input_pixel_processor ipp={&funcs,&context};
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
 stream.dv_native_lldv=true;
 plane.format=SURFACE_PIXEL_FORMAT_GRPH_ARGB2101010;
 assert(dce110_set_input_transfer_func(0,&pipe,&plane));
 assert(prescale_bypass==0 && prescale_scale==0x2008 && lut_bypass==1);
 assert(degamma==IPP_DEGAMMA_MODE_BYPASS);
 stream.dv_native_lldv=false;
 plane.format=SURFACE_PIXEL_FORMAT_GRPH_ARGB8888;
 assert(dce110_set_input_transfer_func(0,&pipe,&plane));
 assert(prescale_bypass==1 && lut_bypass==1);
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
        policy = '\n'.join(function(source, helper) for helper in (
            'dv_rx550', name, 'dv_lldv_native_supported'))
        symbols = sorted(set(re.findall(r'\b(?:DCN|DCE)_VERSION_\w+', policy)))
        code = '#include <assert.h>\n#include <stdbool.h>\n#include <string.h>\n'
        code += 'enum dce_version {' + ','.join(symbols) + '};\n'
        code += r'''
enum { DRM_MODE_CONNECTOR_HDMIA=1, SIGNAL_TYPE_HDMI_TYPE_A=2, DRM_MODE_PROP_ATOMIC=4 };
enum { AMDGPU_LLDV_RGB10_LAB=3,AMDGPU_LLDV_444_10=4 };
#define BIT(n) (1U<<(n))
struct dc_context { enum dce_version dce_version; struct {unsigned chip_id;}asic_id; };
struct dc { struct dc_context *ctx; };
struct amdgpu_device { struct { struct dc *dc; } dm; };
struct link { int connector_signal; };
struct amdgpu_dm_connector {
 struct { void *dev; int connector_type;struct {unsigned id;}base; } base;
 struct link *dc_link; void *dv_standard_property,*hdr10_deep_color_property,*lldv_format_property,*lldv_native_formats_property;
};
#define DRM_MODE_PROP_IMMUTABLE 4
struct drm_prop_enum_list { unsigned value; const char *name; };
#define ARRAY_SIZE(a) (sizeof(a)/sizeof((a)[0]))
static bool dv_standard;
static int dv_properties,hdr_properties,lldv_properties;
#define drm_info(...) ((void)0)
#define drm_to_adev(p) ((struct amdgpu_device *)(p))
static void *drm_property_create_bool(void *dev,int flags,const char *name)
{ (void)dev;(void)flags; if (!strcmp(name,"DVBRIDGE_DV_STANDARD_LAB")) ++dv_properties;
 else if (!strcmp(name,"DVBRIDGE_HDR10_DEEP_COLOR")) ++hdr_properties;
 return &dv_properties; }
static void *drm_property_create_range(void *dev,int flags,const char *name,unsigned min,unsigned max)
{ (void)dev;assert(!flags && !min && max==24 && !strcmp(name,"CB1_NATIVE_LLDV_FORMATS"));
 return &lldv_properties; }
static void *drm_property_create_enum(void *dev,int flags,const char *name,
 const struct drm_prop_enum_list *formats,size_t count)
{
 (void)dev;(void)flags;
 assert(!strcmp(name,"CB1_LLDV_FORMAT"));
 assert(count==4 && formats[0].value==0 && formats[1].value==1 &&
        formats[2].value==AMDGPU_LLDV_RGB10_LAB);
 ++lldv_properties;
 return &lldv_properties;
}
static void drm_object_attach_property(void *base,void *property,int value)
{ (void)base;(void)property;assert(value==0); }
'''
        code += policy + '\n' + function(source, 'amdgpu_dm_dv_attach')
        code += r'''
int main(void) {
 struct dc_context ctx={.dce_version=DCE_VERSION_11_22}; struct dc dc={&ctx};
 struct amdgpu_device dev={.dm={&dc}};
 struct link link={SIGNAL_TYPE_HDMI_TYPE_A};
 struct amdgpu_dm_connector con={.base={&dev,DRM_MODE_CONNECTOR_HDMIA,{0}},.dc_link=&link};
 dv_standard=true; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==1 && hdr_properties==1 && lldv_properties==1);
 dv_properties=hdr_properties=lldv_properties=0;
 dv_standard=false; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==0 && hdr_properties==1 && lldv_properties==1);
 dv_properties=hdr_properties=lldv_properties=0;
 ctx.dce_version=DCN_VERSION_1_0; dv_standard=true; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==1 && hdr_properties==1 && lldv_properties==1);
 dv_properties=hdr_properties=lldv_properties=0;
 link.connector_signal=0; amdgpu_dm_dv_attach(&con);
 assert(dv_properties==0 && hdr_properties==0 && lldv_properties==0);
 return 0;
}
'''
        self.run_c(code)

    def test_dce112_keeps_tunnel_bytes_and_native_ten_bit_linebuffer(self):
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
struct dc_stream_state { bool dv_standard,dv_native_lldv; };
''' + helper + r'''
int main(void) {
 struct dc_context ctx={DCE_VERSION_11_22};
 struct dc_plane_state plane={&ctx}; struct dc_stream_state stream={false};
 assert(resource_get_lb_depth(&plane,&stream)==30);
 stream.dv_standard=true;
 assert(resource_get_lb_depth(&plane,&stream)==24);
 stream.dv_native_lldv=true;
 assert(resource_get_lb_depth(&plane,&stream)==30);
 ctx.dce_version=DCE_VERSION_11_2;
 assert(resource_get_lb_depth(&plane,&stream)==30);
 stream.dv_native_lldv=false;
 assert(resource_get_lb_depth(&plane,&stream)==24);
 stream.dv_standard=false;
 assert(resource_get_lb_depth(&plane,&stream)==30);
 ctx.dce_version=DCN_VERSION_1_0;
 assert(resource_get_lb_depth(&plane,&stream)==36);
 stream.dv_standard=false;
 assert(resource_get_lb_depth(&plane,&stream)==36);
 return 0;
}
''')

    def test_native_422_uses_bt2020_csc_without_expanding_the_low_bits(self):
        source = self.source('dc/hwss/dce110/dce110_hwseq.c')
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
enum { DCE_VERSION_11_2, DCE_VERSION_11_22, DCN_VERSION_1_0,
       DCN_VERSION_2_01, DCN_VERSION_4_01 };
enum dc_color_depth { COLOR_DEPTH_UNDEFINED, COLOR_DEPTH_888, COLOR_DEPTH_101010 };
enum { COLOR_SPACE_YCBCR601, COLOR_SPACE_SRGB, COLOR_SPACE_2020_YCBCR_LIMITED,
       GRAPHICS_CSC_ADJUST_TYPE_SW, PIXEL_ENCODING_YCBCR422, PIXEL_ENCODING_YCBCR444 };
struct dc_context { int dce_version; };
struct dc_stream_state {
 bool dv_standard,dv_native_lldv; struct dc_context *ctx;
 struct { enum dc_color_depth display_color_depth; int pixel_encoding; } timing;
 int signal,output_color_space;
};
struct output_pixel_processor;
struct opp_funcs {
 void (*opp_set_dyn_expansion)(struct output_pixel_processor *,int,enum dc_color_depth,int);
};
struct output_pixel_processor { const struct opp_funcs *funcs; };
struct default_adjustment {
 bool force_hw_default; int in_color_space,out_color_space,csc_adjust_type;
 int surface_pixel_format,color_depth,lb_color_depth;
};
struct transform;
struct transform_funcs {void (*opp_set_csc_default)(struct transform *,const struct default_adjustment *);};
struct transform { const struct transform_funcs *funcs; };
struct dc_plane_state { int color_space; };
struct pipe_ctx {
 struct dc_stream_state *stream; struct dc_plane_state *plane_state;
 struct { struct transform *xfm; struct { int format; struct {int depth;}lb_params;}scl_data;}plane_res;
};
static enum dc_color_depth programmed_depth;
static struct default_adjustment programmed_csc;
static void expansion(struct output_pixel_processor *opp,int color,enum dc_color_depth depth,int signal)
{ (void)opp;(void)signal;assert(color==COLOR_SPACE_YCBCR601);programmed_depth=depth; }
static void csc(struct transform *xfm,const struct default_adjustment *adjust)
{ (void)xfm;programmed_csc=*adjust; }
''' + function(source, 'dce110_program_stream_expansion') + '\n' +
            function(source, 'set_default_colors') + r'''
int main(void)
{
 const struct opp_funcs opp_funcs={expansion}; struct output_pixel_processor opp={&opp_funcs};
 const struct transform_funcs xfm_funcs={csc}; struct transform xfm={&xfm_funcs};
 struct dc_context ctx={0}; struct dc_stream_state stream={.ctx=&ctx};
 struct dc_plane_state plane={0}; struct pipe_ctx pipe={.stream=&stream,.plane_state=&plane,
     .plane_res={.xfm=&xfm,.scl_data={.lb_params={30}}}};
 const int families[]={DCE_VERSION_11_2,DCE_VERSION_11_22,DCN_VERSION_1_0,
                       DCN_VERSION_2_01,DCN_VERSION_4_01};
 for (unsigned i=0;i<sizeof(families)/sizeof(families[0]);i++) {
  ctx.dce_version=families[i]; stream.dv_standard=true;stream.dv_native_lldv=true;
  stream.timing.display_color_depth=COLOR_DEPTH_101010;
  stream.timing.pixel_encoding=PIXEL_ENCODING_YCBCR422;
  stream.output_color_space=COLOR_SPACE_2020_YCBCR_LIMITED;
  dce110_program_stream_expansion(&opp,&stream);set_default_colors(&pipe);
  assert(programmed_depth==COLOR_DEPTH_UNDEFINED);
  assert(!programmed_csc.force_hw_default);
  assert(programmed_csc.out_color_space==COLOR_SPACE_2020_YCBCR_LIMITED);
  assert(programmed_csc.color_depth==COLOR_DEPTH_101010 && programmed_csc.lb_color_depth==30);
  stream.timing.pixel_encoding=PIXEL_ENCODING_YCBCR444;
  dce110_program_stream_expansion(&opp,&stream);
  assert(programmed_depth==COLOR_DEPTH_101010);
  stream.dv_native_lldv=false;stream.timing.display_color_depth=COLOR_DEPTH_888;
  stream.output_color_space=COLOR_SPACE_SRGB;
  dce110_program_stream_expansion(&opp,&stream);set_default_colors(&pipe);
  assert(programmed_depth==(families[i]==DCE_VERSION_11_2 ? COLOR_DEPTH_UNDEFINED:COLOR_DEPTH_888));
  assert(programmed_csc.force_hw_default==(families[i]==DCE_VERSION_11_2));
  stream.dv_standard=false;stream.timing.display_color_depth=COLOR_DEPTH_101010;
  dce110_program_stream_expansion(&opp,&stream);set_default_colors(&pipe);
  assert(programmed_depth==COLOR_DEPTH_101010 && !programmed_csc.force_hw_default);
 }
}
''')

    def test_native_expansion_survives_dcn_pipe_reprogramming(self):
        blocks = []
        for family, owner in (('dcn20', 'dcn20_program_pipe'),
                              ('dcn401', 'dcn401_program_pipe'),
                              ('dcn401', 'dcn401_program_pipe_sequence')):
            body = function(self.source(f'dc/hwss/{family}/{family}_hwseq.c'), owner)
            start = body.index('\t/* If the pipe has been enabled or has a different opp,')
            end = body.index('\t/* Set ABM pipe after other pipe configurations done */', start)
            blocks.append('static void ' + owner + '(struct pipe_ctx *pipe_ctx) {\n'
                          'struct block_sequence_state *seq_state=0;(void)seq_state;\n'
                          + body[start:end] + '\n}')
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
enum { COLOR_DEPTH_UNDEFINED, COLOR_DEPTH_101010, COLOR_SPACE_YCBCR601,
       PIXEL_ENCODING_YCBCR422,PIXEL_ENCODING_YCBCR444 };
struct block_sequence_state { int unused; };
struct output_pixel_processor;
struct opp_funcs {
 void (*opp_set_dyn_expansion)(struct output_pixel_processor *,int,int,int);
 void (*opp_program_fmt)(struct output_pixel_processor *,const int *,const int *);
};
struct output_pixel_processor { const struct opp_funcs *funcs; };
struct dc_stream_state {bool dv_native_lldv;struct {int display_color_depth,pixel_encoding;}timing;
                       int signal,bit_depth_params,clamping;};
struct pipe_ctx {
 struct dc_stream_state *stream;struct {struct output_pixel_processor *opp;}stream_res;
 struct {struct {bool enable,opp_changed;}bits;}update_flags;
};
static int programmed_depth,fmt_calls;
static void expansion(struct output_pixel_processor *o,int color,int depth,int signal)
{(void)o;(void)color;(void)signal;programmed_depth=depth;}
static void fmt(struct output_pixel_processor *o,const int *depth,const int *clamp)
{(void)o;assert(*depth==10 && *clamp==10);++fmt_calls;}
static void hwss_add_opp_set_dyn_expansion(struct block_sequence_state *s,
 struct output_pixel_processor *o,int color,int depth,int signal)
{(void)s;expansion(o,color,depth,signal);}
static void hwss_add_opp_program_fmt(struct block_sequence_state *s,
 struct output_pixel_processor *o,const int *depth,const int *clamp)
{(void)s;fmt(o,depth,clamp);}
''' + '\n'.join(blocks) + r'''
int main(void)
{
 const struct opp_funcs funcs={expansion,fmt}; struct output_pixel_processor opp={&funcs};
 struct dc_stream_state stream={.timing={COLOR_DEPTH_101010,PIXEL_ENCODING_YCBCR422},.bit_depth_params=10,.clamping=10};
 struct pipe_ctx pipe={.stream=&stream,.stream_res={&opp}};
 void (*program[])(struct pipe_ctx *)={dcn20_program_pipe,dcn401_program_pipe,dcn401_program_pipe_sequence};
 for (unsigned i=0;i<sizeof(program)/sizeof(program[0]);i++) {
  for (unsigned changed=0;changed<2;changed++) {
   pipe.update_flags.bits.enable=!changed;pipe.update_flags.bits.opp_changed=changed;
   stream.dv_native_lldv=true;stream.timing.pixel_encoding=PIXEL_ENCODING_YCBCR422;fmt_calls=0;program[i](&pipe);
   assert(programmed_depth==COLOR_DEPTH_UNDEFINED && fmt_calls==1);
   stream.timing.pixel_encoding=PIXEL_ENCODING_YCBCR444;fmt_calls=0;program[i](&pipe);
   assert(programmed_depth==COLOR_DEPTH_101010 && fmt_calls==1);
   stream.dv_native_lldv=false;fmt_calls=0;program[i](&pipe);
   assert(programmed_depth==COLOR_DEPTH_101010 && fmt_calls==1);
  }
 }
}
''')


if __name__ == '__main__':
    unittest.main()
