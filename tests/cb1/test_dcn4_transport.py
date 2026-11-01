"""Execute DCN4's actual color-block programming across ordinary/DV transitions."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class DCN4Transport(unittest.TestCase):
    def test_native_rmcm_gate_is_independent_of_legacy_lut_state(self):
        source=(Path(os.environ['CB1_KERNEL_SOURCE'])/
            'drivers/gpu/drm/amd/display/dc/hwss/dcn42/dcn42_hwseq.c').read_text()
        owner=function(source,'dcn42_populate_mcm_luts')
        block=owner[owner.index('\tif (mcm_luts.lut3d_data.rmcm_3dlut_enable &&'):
                    owner.index('\n\t/* 1D LUT */')]
        code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
enum dc_cm2_gpu_mem_size {DC_CM2_GPU_MEM_SIZE_171717,DC_CM2_GPU_MEM_SIZE_333333,DC_CM2_GPU_MEM_SIZE_TRANSFORMED};
struct dc {struct {struct {struct {struct {bool dma_3d_lut;
 struct {unsigned dim_17,dim_33;}lut_dim_caps;}rmcm_3d_lut_caps;}mpc;}color;}caps;};
struct dc_cm2_func_luts {struct {bool rmcm_3dlut_enable;
 struct {enum dc_cm2_gpu_mem_size size;uint64_t addr;}gpu_mem_params;}lut3d_data;};
struct pipe_ctx {int unused;};struct hubp {int unused;};struct mpc {int unused;};
static unsigned programmed;static uint64_t address;
// Hardware-programming API boundary; never clears or normalizes the candidate.
static bool dcn42_program_rmcm_luts(struct hubp *hubp,struct pipe_ctx *pipe,int src,
 struct dc_cm2_func_luts *luts,struct mpc *mpc,bool bank,int id)
{(void)hubp;(void)pipe;(void)src;(void)mpc;(void)bank;(void)id;
 ++programmed;address=luts->lut3d_data.gpu_mem_params.addr;return true;}
''' + function(source,'is_rmcm_3dlut_fl_supported') + r'''
static void native_rmcm_admission(struct dc *dc,struct dc_cm2_func_luts mcm_luts)
{struct hubp *hubp=0;struct pipe_ctx *pipe_ctx=0;struct mpc *mpc=0;
 int lut3d_src=1,mpcc_id=0;bool lut_bank_a=false;
''' + block + r'''
}
int main(void)
{
 struct dc dc={0};struct dc_cm2_func_luts luts={0};
 luts.lut3d_data.rmcm_3dlut_enable=true;
 luts.lut3d_data.gpu_mem_params.addr=0x12340000;
 native_rmcm_admission(&dc,luts);assert(!programmed);
 dc.caps.color.mpc.rmcm_3d_lut_caps.dma_3d_lut=true;
 dc.caps.color.mpc.rmcm_3d_lut_caps.lut_dim_caps.dim_17=1;
 native_rmcm_admission(&dc,luts);assert(programmed==1 && address==0x12340000);
 luts.lut3d_data.rmcm_3dlut_enable=false;
 native_rmcm_admission(&dc,luts);assert(programmed==1);
 luts.lut3d_data.rmcm_3dlut_enable=true;
 luts.lut3d_data.gpu_mem_params.size=DC_CM2_GPU_MEM_SIZE_333333;
 native_rmcm_admission(&dc,luts);assert(programmed==1);
 dc.caps.color.mpc.rmcm_3d_lut_caps.lut_dim_caps.dim_33=1;
 native_rmcm_admission(&dc,luts);assert(programmed==2);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source,binary=Path(directory)/'test.c',Path(directory)/'test'
            source.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_native_1to1_scaler_override_is_not_a_neutral_debug_setting(self):
        dc=Path(os.environ['CB1_KERNEL_SOURCE'])/'drivers/gpu/drm/amd/display/dc'
        functions=[]
        for folder,prefix in (('dcn10','dpp1'),('dcn401','dpp401')):
            source=(dc/'dpp'/folder/(folder+'_dpp_dscl.c')).read_text()
            functions.extend(function(source,prefix+name) for name in (
                '_dscl_is_video_format','_dscl_is_420_format','_dscl_get_dscl_mode'))
        code=r'''
#include <assert.h>
#include <stdbool.h>
enum dc_pixel_format {PIXEL_FORMAT_RGB=1,PIXEL_FORMAT_FP16,
 PIXEL_FORMAT_VIDEO_BEGIN=100,PIXEL_FORMAT_420BPP8,PIXEL_FORMAT_420BPP10,PIXEL_FORMAT_VIDEO_END=200};
enum {DSCL_DATA_PRCESSING_FIXED_FORMAT,DSCL_DATA_PRCESSING_FLOAT_FORMAT};
enum dscl_mode_sel {DSCL_MODE_DSCL_BYPASS,DSCL_MODE_SCALING_444_BYPASS,
 DSCL_MODE_SCALING_444_YCBCR_ENABLE,DSCL_MODE_SCALING_444_RGB_ENABLE,
 DSCL_MODE_SCALING_420_LUMA_BYPASS,DSCL_MODE_SCALING_420_CHROMA_BYPASS,
 DSCL_MODE_SCALING_420_YCBCR_ENABLE};
enum dcn401_dscl_mode_sel {DCN401_DSCL_MODE_DSCL_BYPASS,DCN401_DSCL_MODE_SCALING_444_BYPASS,
 DCN401_DSCL_MODE_SCALING_444_YCBCR_ENABLE,DCN401_DSCL_MODE_SCALING_444_RGB_ENABLE,
 DCN401_DSCL_MODE_SCALING_420_LUMA_BYPASS,DCN401_DSCL_MODE_SCALING_420_CHROMA_BYPASS,
 DCN401_DSCL_MODE_SCALING_420_YCBCR_ENABLE};
struct fixed {long long value;};
static const struct fixed dc_fixpt_one={1LL<<32};
struct scaler_data {enum dc_pixel_format format;struct {struct fixed horz,vert,horz_c,vert_c;}ratios;};
struct dpp {struct {int dscl_data_proc_format;} *caps;};
'''+'\n'.join(functions)+r'''
int main(void)
{
 struct {int dscl_data_proc_format;}caps={DSCL_DATA_PRCESSING_FIXED_FORMAT};
 struct dpp dpp={(void *)&caps};
 struct scaler_data data={.format=PIXEL_FORMAT_RGB,
     .ratios={dc_fixpt_one,dc_fixpt_one,dc_fixpt_one,dc_fixpt_one}};
 assert(dpp1_dscl_get_dscl_mode(&dpp,&data,false)==DSCL_MODE_SCALING_444_BYPASS);
 assert(dpp1_dscl_get_dscl_mode(&dpp,&data,true)==DSCL_MODE_SCALING_444_RGB_ENABLE);
 assert(dpp401_dscl_get_dscl_mode(&dpp,&data,false)==DCN401_DSCL_MODE_SCALING_444_BYPASS);
 assert(dpp401_dscl_get_dscl_mode(&dpp,&data,true)==DCN401_DSCL_MODE_SCALING_444_RGB_ENABLE);
}
'''
        with tempfile.TemporaryDirectory() as directory:
            source,binary=Path(directory)/'test.c',Path(directory)/'test'
            source.write_text(code)
            result=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

    def test_real_atomic_neutral_plane_and_exit_contract(self):
        kernel=Path(os.environ['CB1_KERNEL_SOURCE'])
        source=(kernel/'drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm_dv.c').read_text()
        names=('dv_stream_edid','dv_sink_supported','dv_identity_tf',
               'dv_plane_neutral','amdgpu_dm_dv_atomic_check')
        code=Path(__file__).with_name('amd_dv_atomic.c').read_text().replace(
            '@@FUNCTIONS@@','\n'.join(function(source,name) for name in names))
        with tempfile.TemporaryDirectory() as directory:
            src,binary=Path(directory)/'test.c',Path(directory)/'test'
            src.write_text(code)
            built=subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-unused-parameter','-Wno-sign-compare','-Wno-unused-but-set-variable',
                '-fsanitize=address,undefined',
                '-I'+str(kernel/'include/drm'),str(src),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_native_neutral_blocks_and_ordinary_restoration(self):
        dc = Path(os.environ['CB1_KERNEL_SOURCE'])/'drivers/gpu/drm/amd/display/dc'
        sources = {
            '32': (dc/'hwss/dcn32/dcn32_hwseq.c').read_text(),
            '401': (dc/'hwss/dcn401/dcn401_hwseq.c').read_text(),
            '42': (dc/'hwss/dcn42/dcn42_hwseq.c').read_text(),
        }
        names = [('32', 'dcn32_set_mpc_shaper_3dlut'),
                 ('401', 'dcn401_program_gamut_remap'),
                 ('401', 'dcn401_set_mcm_luts'), ('42', 'dcn42_set_mcm_luts'),
                 ('32', 'dcn32_set_input_transfer_func'),
                 ('401', 'dcn401_set_output_transfer_func')]
        code = Path(__file__).with_name('dcn4_transport.c').read_text().replace(
            '@@FUNCTIONS@@', '\n'.join(function(sources[key], name) for key, name in names))
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'test.c', Path(directory)/'test'
            source.write_text(code)
            built = subprocess.run(['cc', '-std=gnu11', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-fsanitize=undefined,address',
                str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

