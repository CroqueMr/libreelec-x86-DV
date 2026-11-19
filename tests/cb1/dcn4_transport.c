/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdbool.h>
#include <string.h>
#define ASSERT assert
#define BREAK_TO_DEBUGGER() assert(0)
#define DC_LOG_ERROR(...) do {(void)dc; assert(0);} while(0)
#define CSC_TEMPERATURE_MATRIX_SIZE 12
enum { TF_TYPE_BYPASS, TF_TYPE_HWPWL, TF_TYPE_DISTRIBUTED_POINTS, TF_TYPE_PREDEFINED };
enum dc_transfer_func_predefined {TRANSFER_FUNCTION_UNITY, TRANSFER_FUNCTION_PQ};
enum { GRAPHICS_GAMUT_ADJUST_TYPE_BYPASS, GRAPHICS_GAMUT_ADJUST_TYPE_SW,
       MPCC_MCM_FIRST_GAMUT_REMAP, MPCC_MCM_SECOND_GAMUT_REMAP, MPCC_OGAM_GAMUT_REMAP,
       MPCC_MOVABLE_CM_LOCATION_BEFORE, DC_CM2_TRANSFER_FUNC_SOURCE_VIDMEM, OPP_HEAD };
struct pwl_params {int value;};
struct transfer {int type;enum dc_transfer_func_predefined tf;struct pwl_params pwl;};
struct gamut {bool enable_remap;int matrix[12];};
struct lut3d {struct {struct {unsigned initialized;}bits;}state;int lut_3d;};
struct mcm {struct {int lut3d_src;}lut3d_data;};
struct dc;
struct context {struct dc *dc;};
struct dc_plane_state {
    struct context *ctx;struct transfer blend_tf,in_shaper_func,in_transfer_func;
    struct lut3d lut3d_func;struct gamut gamut_remap_matrix;
    struct mcm mcm_luts;bool lut_bank_a;int mcm_location;
};
struct dc_stream_state {
    struct context *ctx;struct transfer out_transfer_func,*func_shaper;
    struct lut3d *lut3d_func;struct gamut gamut_remap_matrix;
};
struct mpc_grph_gamut_adjustment {int gamut_adjust_type,mpcc_gamut_remap_block_id,temperature_matrix[12];};
struct mpc;
struct mpc_funcs {
    void (*set_gamut_remap)(struct mpc*,int,struct mpc_grph_gamut_adjustment*);
    bool (*program_1dlut)(struct mpc*,const struct pwl_params*,int);
    bool (*program_shaper)(struct mpc*,const struct pwl_params*,int);
    bool (*program_3dlut)(struct mpc*,const int*,int);
    void (*set_movable_cm_location)(struct mpc*,int,int);
    void (*set_output_gamma)(struct mpc*,int,const struct pwl_params*);
};
struct mpc {struct mpc_funcs *funcs;struct pwl_params blender_params;};
struct dpp;
struct dpp_funcs {
    void (*dpp_set_pre_degam)(struct dpp*,enum dc_transfer_func_predefined);
    void (*dpp_program_gamcor_lut)(struct dpp*,const struct pwl_params*);
};
struct dpp {struct dpp_funcs *funcs;struct pwl_params regamma_params,shaper_params,degamma_params;};
struct pipe_ctx {
    struct dc_plane_state *plane_state;struct dc_stream_state *stream;struct pipe_ctx *top_pipe;
    struct {int mpcc_inst;struct dpp *dpp;struct {int inst;}*hubp;}plane_res;
    struct {struct {struct context *ctx;}*opp;}stream_res;
};
struct dce_hwseq {struct {bool (*set_mcm_luts)(struct pipe_ctx*,const struct dc_plane_state*);}funcs;};
struct dc {struct {struct mpc *mpc;}*res_pool;struct dce_hwseq *hwseq;};
static struct {int gamut[6],one,shaper,lut3d,ogam,igam,pre,vidmem;} trace;
static void gamut(struct mpc*m,int id,struct mpc_grph_gamut_adjustment*a){trace.gamut[a->mpcc_gamut_remap_block_id]=a->gamut_adjust_type;}
static bool one(struct mpc*m,const struct pwl_params*p,int id){trace.one=p!=NULL;return trace.one;}
static bool shaper(struct mpc*m,const struct pwl_params*p,int id){trace.shaper=p!=NULL;return trace.shaper;}
static bool lut(struct mpc*m,const int*p,int id){trace.lut3d=p!=NULL;return trace.lut3d;}
static void location(struct mpc*m,int loc,int id){}
static void ogam(struct mpc*m,int id,const struct pwl_params*p){trace.ogam=p!=NULL;}
static void pre(struct dpp*d,enum dc_transfer_func_predefined tf){trace.pre=tf;}
static void igam(struct dpp*d,const struct pwl_params*p){trace.igam=p!=NULL;}
static bool cm3_helper_translate_curve_to_hw_format(struct context*c,const struct transfer*t,struct pwl_params*p,bool s){return true;}
static void cm_helper_translate_curve_to_hw_format(struct context*c,const struct transfer*t,struct pwl_params*p,bool s){}
static bool resource_is_pipe_type(struct pipe_ctx*p,int t){return p->top_pipe==NULL;}
static void dcn401_populate_mcm_luts(struct dc*d,struct pipe_ctx*p,struct mcm m,bool b){trace.vidmem++;}
static void dcn42_populate_mcm_luts(struct dc*d,struct pipe_ctx*p,struct mcm m,bool b){trace.vidmem++;}
@@FUNCTIONS@@
int main(void){
    struct mpc_funcs mf={gamut,one,shaper,lut,location,ogam};struct mpc mpc={.funcs=&mf};
    struct dpp_funcs df={pre,igam};struct dpp dpp={.funcs=&df};
    typeof(*((struct dc*)0)->res_pool) pool={&mpc};struct dce_hwseq hws={0};
    struct dc dc={&pool,&hws};struct context ctx={&dc};
    struct dc_plane_state plane={.ctx=&ctx};struct dc_stream_state stream={.ctx=&ctx};
    typeof(*((struct pipe_ctx*)0)->plane_res.hubp) hubp={0};
    typeof(*((struct pipe_ctx*)0)->stream_res.opp) opp={&ctx};
    struct pipe_ctx pipe={.plane_state=&plane,.stream=&stream,
        .plane_res={.dpp=&dpp,.hubp=&hubp},.stream_res={.opp=&opp}};
    bool (*mcm[])(struct pipe_ctx*,const struct dc_plane_state*)={dcn401_set_mcm_luts,dcn42_set_mcm_luts};
    for(unsigned variant=0;variant<2;variant++){
        hws.funcs.set_mcm_luts=mcm[variant];
        for(unsigned cycle=0;cycle<3;cycle++){
            /* Native ordinary HDR uses its real LUTs, then neutral DV clears them. */
            plane.mcm_location=MPCC_MOVABLE_CM_LOCATION_BEFORE;
            plane.mcm_luts.lut3d_data.lut3d_src=-1;
            plane.in_transfer_func.type=plane.blend_tf.type=plane.in_shaper_func.type=TF_TYPE_HWPWL;
            plane.lut3d_func.state.bits.initialized=1;
            stream.out_transfer_func.type=TF_TYPE_HWPWL;
            plane.gamut_remap_matrix.enable_remap=stream.gamut_remap_matrix.enable_remap=true;
            dcn401_program_gamut_remap(&pipe);
            assert(dcn32_set_input_transfer_func(&dc,&pipe,&plane));
            dcn401_set_output_transfer_func(&dc,&pipe,&stream);
            assert(trace.one && trace.shaper && trace.lut3d && trace.igam && trace.ogam);
            assert(trace.gamut[MPCC_MCM_FIRST_GAMUT_REMAP]==GRAPHICS_GAMUT_ADJUST_TYPE_SW);
            assert(trace.gamut[MPCC_OGAM_GAMUT_REMAP]==GRAPHICS_GAMUT_ADJUST_TYPE_SW);
            plane.in_transfer_func.type=plane.blend_tf.type=plane.in_shaper_func.type=TF_TYPE_BYPASS;
            plane.lut3d_func.state.bits.initialized=0;stream.out_transfer_func.type=TF_TYPE_BYPASS;
            plane.gamut_remap_matrix.enable_remap=stream.gamut_remap_matrix.enable_remap=false;
            dcn401_program_gamut_remap(&pipe);
            assert(!dcn32_set_input_transfer_func(&dc,&pipe,&plane));
            dcn401_set_output_transfer_func(&dc,&pipe,&stream);
            assert(!trace.one && !trace.shaper && !trace.lut3d && !trace.igam && !trace.ogam);
            assert(trace.pre==TRANSFER_FUNCTION_UNITY && !trace.vidmem);
            assert(trace.gamut[MPCC_MCM_FIRST_GAMUT_REMAP]==GRAPHICS_GAMUT_ADJUST_TYPE_BYPASS);
            assert(trace.gamut[MPCC_MCM_SECOND_GAMUT_REMAP]==GRAPHICS_GAMUT_ADJUST_TYPE_BYPASS);
            assert(trace.gamut[MPCC_OGAM_GAMUT_REMAP]==GRAPHICS_GAMUT_ADJUST_TYPE_BYPASS);
        }
        // The real VIDMEM entry delegates unchanged data, not the legacy LUT path.
        plane.mcm_luts.lut3d_data.lut3d_src=DC_CM2_TRANSFER_FUNC_SOURCE_VIDMEM;
        trace.vidmem=0;
        hws.funcs.set_mcm_luts(&pipe,&plane);
        assert(trace.vidmem==1);
        assert(plane.mcm_luts.lut3d_data.lut3d_src==DC_CM2_TRANSFER_FUNC_SOURCE_VIDMEM);
        trace.vidmem=0;
    }
}
