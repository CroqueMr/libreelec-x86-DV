"""Native Vega M IPP MMIO lifecycle and zero-update-bit dispatch boundaries."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class VegaMLifecycle(unittest.TestCase):
    def source(self, name):
        return (Path(os.environ['CB1_KERNEL_SOURCE']) /
                'drivers/gpu/drm/amd/display/dc' / name).read_text()

    def run_c(self, code):
        with tempfile.TemporaryDirectory() as directory:
            source,binary=Path(directory)/'test.c',Path(directory)/'test'
            source.write_text(code)
            result=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',
                '-Wno-unused-function','-fsanitize=address,undefined',
                str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_csc_save_repeat_exit_and_native_d0_reset_are_per_ipp(self):
        ipp=self.source('dce/dce_ipp.c')
        header=self.source('dce/dce_ipp.h')
        hwseq=self.source('hwss/dce110/dce110_hwseq.c')
        native_init=function(hwseq,'dce110_init_hw')
        init_loop=native_init[native_init.index('\tbp = dc->ctx->dc_bios;'):
                              native_init.index('\n\tdce_clock_gating_power_up(')]
        structures='\n'.join(re.search(r'struct '+name+r' \{.*?\n\};',header,re.S).group()
            for name in ('dce_ipp_registers','dce_ipp'))
        reset=(function(ipp,'dce_ipp_reset_dv') if 'dce_ipp_reset_dv(' in ipp else '')
        register_init='.INPUT_CSC_CONTROL=1' if 'uint32_t INPUT_CSC_CONTROL;' in header else '0'
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
enum {DCE_VERSION_11_2,DCE_VERSION_11_22,DCE_VERSION_12_0};
enum ipp_prescale_mode {IPP_PRESCALE_MODE_BYPASS,IPP_PRESCALE_MODE_FIXED_SIGNED,
 IPP_PRESCALE_MODE_FLOAT_SIGNED,IPP_PRESCALE_MODE_FIXED_UNSIGNED,
 IPP_PRESCALE_MODE_FLOAT_UNSIGNED,IPP_PRESCALE_MODE_BYPASS_LUT};
struct ipp_prescale_params {enum ipp_prescale_mode mode;uint16_t bias,scale;};
struct dc_bios {int unused;};
struct dc_context {int dce_version;struct dc_bios *dc_bios;};
struct input_pixel_processor {struct dc_context *ctx;unsigned inst;const void *funcs;};
@@STRUCTURES@@
#define TO_DCE_IPP(p) ((struct dce_ipp *)(p))
#define REG(r) (ipp_dce->regs->r)
static uint32_t mmio[2][64];
static unsigned reads[2];
static void read_csc(struct dce_ipp *p,uint32_t address,uint32_t *value)
{ ++reads[p->base.inst];*value=mmio[p->base.inst][address]&3; }
static void update(struct dce_ipp *p,const char *field,uint32_t value)
{
 if(!strcmp(field,"INPUT_CSC_GRPH_MODE"))
    mmio[p->base.inst][1]=(mmio[p->base.inst][1]&~3U)|(value&3);
}
#define REG_GET(r,f,p) read_csc(ipp_dce,REG(r),p)
#define REG_UPDATE(r,f,v) update(ipp_dce,#f,v)
#define REG_SET_2(r,init,f1,v1,f2,v2) ((void)ipp_dce,(void)(v1),(void)(v2))
@@IPP@@
struct dc;
struct transform {const struct {void(*transform_reset)(struct transform *);} *funcs;};
struct resource_pool {unsigned pipe_count;struct transform *transforms[2];
                     struct input_pixel_processor *ipps[2];};
struct dce_hwseq {struct {
 void(*enable_display_power_gating)(struct dc *,uint8_t,struct dc_bios *,int);
 void(*enable_display_pipe_clock_gating)(struct dc_context *,bool);
}funcs;};
struct dc {struct dc_context *ctx;struct resource_pool *res_pool;struct dce_hwseq *hwseq;};
enum {PIPE_GATING_CONTROL_INIT,PIPE_GATING_CONTROL_DISABLE};
static void transform_reset(struct transform *t){(void)t;}
static void power_gating(struct dc *dc,uint8_t i,struct dc_bios *bp,int mode)
{(void)dc;(void)bp;if(mode==PIPE_GATING_CONTROL_INIT)mmio[i][1]=0x92;}
static void clock_gating(struct dc_context *c,bool enabled){(void)c;(void)enabled;}
static void native_d0_first_loop(struct dc *dc)
{
 unsigned i;struct dc_bios *bp;struct transform *xfm;struct dce_hwseq *hws=dc->hwseq;
@@INIT@@
}
int main(void)
{
 struct dc_context ctx={.dce_version=DCE_VERSION_11_22};
 const struct dce_ipp_registers regs={@@REG@@};
 struct dce_ipp a={.base={.ctx=&ctx,.inst=0},.regs=&regs};
 struct dce_ipp b={.base={.ctx=&ctx,.inst=1},.regs=&regs};
 struct ipp_prescale_params dv={.mode=IPP_PRESCALE_MODE_BYPASS_LUT};
 struct ipp_prescale_params ordinary={.mode=IPP_PRESCALE_MODE_FIXED_UNSIGNED};
 mmio[0][1]=0xa3;mmio[1][1]=0xb2;
 dce_ipp_program_prescale(&a.base,&dv);
 assert(mmio[0][1]==0xa0 && reads[0]==1 && mmio[1][1]==0xb2);
 dce_ipp_program_prescale(&a.base,&dv);
 assert(mmio[0][1]==0xa0 && reads[0]==1);
 dce_ipp_program_prescale(&b.base,&dv);
 assert(mmio[1][1]==0xb0 && reads[1]==1);
 dce_ipp_program_prescale(&a.base,&ordinary);
 assert(mmio[0][1]==0xa3 && mmio[1][1]==0xb0);
 dce_ipp_program_prescale(&b.base,&ordinary);
 assert(mmio[1][1]==0xb2);
 // D0 reset must discard the old saved3 before the next DV entry saves2.
 dce_ipp_program_prescale(&a.base,&dv);
 const __typeof__(*(((struct transform *)0)->funcs)) tf={transform_reset};
 struct transform xfm={&tf};
 struct resource_pool pool={.pipe_count=2,.transforms={&xfm,&xfm},.ipps={&a.base,&b.base}};
 struct dce_hwseq hws={.funcs={power_gating,clock_gating}};
 struct dc dc={&ctx,&pool,&hws};
 native_d0_first_loop(&dc);
 dce_ipp_program_prescale(&a.base,&dv);
 assert(mmio[0][1]==0x90);
 dce_ipp_program_prescale(&a.base,&ordinary);
 assert(mmio[0][1]==0x92);
 // The same register map on other DCE generations stays native.
 for(int i=0;i<3;i+=2) {
    ctx.dce_version=i;mmio[0][1]=0xc3;
    dce_ipp_program_prescale(&a.base,&dv);
    assert(mmio[0][1]==0xc3);
 }
}
'''.replace('@@STRUCTURES@@',structures).replace('@@IPP@@',reset+'\n'+
             function(ipp,'dce_ipp_program_prescale')).replace('@@INIT@@',init_loop)
        self.run_c(code.replace('@@REG@@',register_init))

    def test_real_frontend_calls_input_programming_with_zero_plane_update_bits(self):
        owner=function(self.source('hwss/dce110/dce110_hwseq.c'),
                       'dce110_program_front_end_for_pipe')
        block=owner[owner.index('\t/* Moved programming gamma'):
                    owner.index('\n\tDC_LOG_SURFACE(')]
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
enum {DCE_VERSION_11_2,DCE_VERSION_11_22,DCE_VERSION_12_0};
struct dc;struct pipe_ctx;struct dc_plane_state;struct dc_stream_state;
struct dce_hwseq {struct {
 bool(*set_input_transfer_func)(struct dc *,struct pipe_ctx *,const struct dc_plane_state *);
 bool(*set_output_transfer_func)(struct dc *,struct pipe_ctx *,const struct dc_stream_state *);
}funcs;};
struct dc {struct {int dce_version;} *ctx;struct dce_hwseq *hwseq;};
struct dc_plane_state {struct {struct {bool full_update,in_transfer_func_change,gamma_change;}bits;}update_flags;};
struct dc_stream_state {bool dv_standard;};
struct pipe_ctx {struct dc_plane_state *plane_state;struct dc_stream_state *stream;};
static unsigned input_calls,output_calls;
static bool input(struct dc *d,struct pipe_ctx *p,const struct dc_plane_state *s)
{(void)d;(void)p;(void)s;++input_calls;return true;}
static bool output(struct dc *d,struct pipe_ctx *p,const struct dc_stream_state *s)
{(void)d;(void)p;(void)s;++output_calls;return true;}
static void native_color_dispatch(struct dc *dc,struct pipe_ctx *pipe_ctx)
{struct dce_hwseq *hws=dc->hwseq;
''' + block + r'''
}
int main(void)
{
 struct dce_hwseq hws={.funcs={input,output}};
 struct {int dce_version;}ctx={DCE_VERSION_11_22};
 struct dc dc={(void *)&ctx,&hws};struct dc_plane_state plane={0};
 struct dc_stream_state stream={0};struct pipe_ctx pipe={&plane,&stream};
 native_color_dispatch(&dc,&pipe);assert(input_calls==1 && !output_calls);
 stream.dv_standard=true;native_color_dispatch(&dc,&pipe);assert(input_calls==2);
 native_color_dispatch(&dc,&pipe);assert(input_calls==3);
 stream.dv_standard=false;native_color_dispatch(&dc,&pipe);assert(input_calls==4);
 ctx.dce_version=DCE_VERSION_11_2;native_color_dispatch(&dc,&pipe);assert(input_calls==4);
 ctx.dce_version=DCE_VERSION_12_0;native_color_dispatch(&dc,&pipe);assert(input_calls==4);
 plane.update_flags.bits.full_update=true;native_color_dispatch(&dc,&pipe);
 assert(input_calls==5 && output_calls==1);
}
''')


if __name__=='__main__':
    unittest.main()
