/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <string.h>
#include <stddef.h>
#include <stdio.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
#define BIT(n) (1u<<(n))
#include "drm_dvbridge.h"
enum amdgpu_transfer_function {AMDGPU_TRANSFER_FUNCTION_DEFAULT,AMDGPU_TRANSFER_FUNCTION_IDENTITY,AMDGPU_TRANSFER_FUNCTION_PQ};
enum {DRM_PLANE_TYPE_PRIMARY=1,DRM_PLANE_TYPE_CURSOR,DRM_FORMAT_XRGB8888,DRM_FORMAT_XBGR8888,
      DRM_MODE_ROTATE_0,DRM_BLEND_ALPHA_OPAQUE,AMDGPU_HDR_MULT_DEFAULT,ROTATION_ANGLE_0,
      TF_TYPE_BYPASS,VRR_STATE_ACTIVE_FIXED,VRR_STATE_ACTIVE_VARIABLE,DITHER_OPTION_DISABLE,
      COLOR_SPACE_SRGB,SIGNAL_TYPE_HDMI_TYPE_A,TIMING_3D_FORMAT_NONE,PIXEL_ENCODING_RGB,
      COLOR_DEPTH_888,DRM_MODE_CONNECTOR_HDMIA,DRM_HDMI_BROADCAST_RGB_FULL,RMX_OFF};
enum {SHARPNESS_HW_OFF,SHARPNESS_ZERO,SHARPNESS_CUSTOM};
enum {VISUAL_CONFIRM_DISABLE,VISUAL_CONFIRM_SURFACE};
enum {DC_CM2_TRANSFER_FUNC_SOURCE_SYSMEM,DC_CM2_TRANSFER_FUNC_SOURCE_VIDMEM};
enum {DC_CM2_SHAPER_3DLUT_SETTING_BYPASS_ALL,DC_CM2_SHAPER_3DLUT_SETTING_ENABLE_SHAPER};
struct dc {struct {bool use_spl;}config;
 struct {int visual_confirm;bool disable_spl,always_scale;unsigned force_sharpness,force_sharpness_level;}debug;};
struct dc_context {struct dc *dc;};
struct dc_transfer_func {int type;};
struct dc_3dlut {struct {struct {bool initialized;}bits;}state;};
struct dc_cm2_func_luts {
 const struct dc_transfer_func *shaper;
 struct {int lut3d_src;union {const struct dc_3dlut *lut3d_func;
  struct {uint64_t addr;}gpu_mem_params;};
  bool rmcm_3dlut_shaper_select,mpc_3dlut_enable,rmcm_3dlut_enable,mpc_mcm_post_blend;
  uint8_t rmcm_tmz;}lut3d_data;
 const struct dc_transfer_func *lut1d_func;
};
struct dc_edid {u8 raw_edid[256];unsigned length;};
struct dc_stream_state {
 struct dc_context *ctx;
 const struct dc_transfer_func *func_shaper;
 const struct dc_3dlut *lut3d_func;
 struct {struct dc_edid dc_edid;}*sink;
 bool dv_standard;int dither_option,output_color_space,signal;
 struct {int type;}out_transfer_func;
 struct {bool enable_remap;}gamut_remap_matrix;
 struct {bool enable_adjustment;}csc_color_matrix;
 struct {bool valid;}avi_infopacket,vsp_infopacket;
 struct {struct {bool INTERLACE,DSC;}flags;int timing_3d_format;
  int h_border_left,h_border_right,v_border_top,v_border_bottom;
  int h_addressable,v_addressable,pixel_encoding,display_color_depth;}timing;
 struct {int x,y,width,height;}src,dst;
};
struct dc_plane_state {
 struct dc_context *ctx;
 bool adaptive_sharpness_en,mcm_lut1d_enable;
 unsigned sharpness_level;int mcm_shaper_3dlut_setting;
 struct dc_cm2_func_luts mcm_luts;
 bool visible,horizontal_mirror,per_pixel_alpha,global_alpha;int rotation;
 struct {bool is_identity;}gamma_correction;
 struct {int type;}in_transfer_func,in_shaper_func,blend_tf;
 struct {struct {struct {bool initialized;}bits;}state;}lut3d_func;
 struct {long value;}hdr_mult;
 struct {bool enable_remap;}gamut_remap_matrix;
 struct {bool enable_adjustment;}input_csc_color_matrix;
};
static const struct {long value;}dc_fixpt_one={1};
struct drm_display_mode {int hdisplay,vdisplay,refresh;};
static int drm_mode_vrefresh(const struct drm_display_mode*m){return m->refresh;}
struct drm_crtc {int unused;};
struct drm_crtc_state {
 bool active,vrr_enabled,async_flip;void *ctm,*gamma_lut,*degamma_lut;
 struct drm_display_mode mode;unsigned connector_mask,plane_mask;
};
struct dm_crtc_state {struct drm_crtc_state base;struct dc_stream_state *stream;
 struct {int state;}freesync_config;enum amdgpu_transfer_function regamma_tf;};
struct drm_connector {int connector_type;};
struct drm_connector_state {struct drm_crtc *crtc;void *hdr_output_metadata;
 unsigned colorspace,max_requested_bpc;struct {int broadcast_rgb;}hdmi;};
struct dm_connector_state {struct drm_connector_state base;bool dv_standard,hdr10_deep_color,underscan_enable;int scaling;};
struct drm_plane {int type;};
struct drm_framebuffer {struct {unsigned format;}*format;int width,height;};
struct drm_plane_state {
 struct drm_plane*plane;struct drm_crtc *crtc;struct drm_framebuffer *fb;
 int rotation,alpha;void *color_pipeline;bool visible;
 unsigned src_x,src_y,src_w,src_h;int crtc_x,crtc_y,crtc_w,crtc_h;
};
struct dm_plane_state {struct drm_plane_state base;struct dc_plane_state *dc_state;
 void *degamma_lut,*ctm,*shaper_lut,*lut3d,*blend_lut;
 enum amdgpu_transfer_function degamma_tf,shaper_tf,blend_tf;int hdr_mult;};
struct drm_atomic_commit {struct drm_crtc *crtc;struct drm_connector *connector;
 struct drm_plane *plane;struct drm_crtc_state *cs;struct drm_connector_state *con;struct drm_plane_state *ps;};
#define to_dm_crtc_state(p) ((struct dm_crtc_state*)(p))
#define to_dm_connector_state(p) ((struct dm_connector_state*)(p))
#define to_dm_plane_state(p) ((struct dm_plane_state*)(p))
#define for_each_new_crtc_in_state(s,c,cs,i) for((i)=0,(c)=(s)->crtc,(cs)=(s)->cs;(i)<1;(i)++)
#define for_each_new_connector_in_state(s,c,cs,i) for((i)=0,(c)=(s)->connector,(cs)=(s)->con;(i)<1;(i)++)
#define for_each_new_plane_in_state(s,c,cs,i) for((i)=0,(c)=(s)->plane,(cs)=(s)->ps;(i)<1;(i)++)
static int hweight32(unsigned n){return __builtin_popcount(n);}
@@FUNCTIONS@@
static void checksum(u8*p){u8 n=0;p[127]=0;for(unsigned i=0;i<127;i++)n+=p[i];p[127]=-n;}
int main(void){
 struct dc display={0};struct dc_context ctx={&display};
 struct drm_crtc crtc={0};struct drm_connector connector={DRM_MODE_CONNECTOR_HDMIA};
 struct drm_plane plane={DRM_PLANE_TYPE_PRIMARY};
 typeof(*((struct drm_framebuffer*)0)->format)format={DRM_FORMAT_XRGB8888};
 struct drm_framebuffer fb={&format,3840,2160};
 struct dc_plane_state dp={.ctx=&ctx,.visible=true,.rotation=ROTATION_ANGLE_0,
  .gamma_correction={true},.in_transfer_func={TF_TYPE_BYPASS},.in_shaper_func={TF_TYPE_BYPASS},
  .blend_tf={TF_TYPE_BYPASS},.hdr_mult={1}};
 struct dm_plane_state ps={.base={.plane=&plane,.crtc=&crtc,.fb=&fb,
  .rotation=DRM_MODE_ROTATE_0,.alpha=DRM_BLEND_ALPHA_OPAQUE,.visible=true,
  .src_w=3840u<<16,.src_h=2160u<<16,.crtc_w=3840,.crtc_h=2160},
  .dc_state=&dp,.hdr_mult=AMDGPU_HDR_MULT_DEFAULT};
 typeof(*((struct dc_stream_state*)0)->sink)sink={0};
 struct dc_stream_state stream={.ctx=&ctx,.sink=&sink,.dv_standard=true,.dither_option=DITHER_OPTION_DISABLE,
  .output_color_space=COLOR_SPACE_SRGB,.signal=SIGNAL_TYPE_HDMI_TYPE_A,
  .out_transfer_func={TF_TYPE_BYPASS},.avi_infopacket={true},.vsp_infopacket={true},
  .timing={.timing_3d_format=TIMING_3D_FORMAT_NONE,.h_addressable=3840,.v_addressable=2160,
    .pixel_encoding=PIXEL_ENCODING_RGB,.display_color_depth=COLOR_DEPTH_888},
  .src={0,0,3840,2160},.dst={0,0,3840,2160}};
 struct dm_crtc_state cs={.base={.active=true,.mode={3840,2160,30},.connector_mask=1,.plane_mask=1},.stream=&stream};
 struct dm_connector_state con={.base={.crtc=&crtc,.max_requested_bpc=8,.hdmi={DRM_HDMI_BROADCAST_RGB_FULL}},
  .dv_standard=true,.scaling=RMX_OFF};
 struct drm_atomic_commit atomic={&crtc,&connector,&plane,&cs.base,&con.base,&ps.base};
 const u8 magic[]={0,255,255,255,255,255,255,0};
 memcpy(sink.dc_edid.raw_edid,magic,8);sink.dc_edid.length=256;sink.dc_edid.raw_edid[126]=1;
 u8*b=sink.dc_edid.raw_edid+128;b[0]=2;b[1]=3;b[2]=16;b[4]=0xeb;
 b[5]=1;b[6]=0x46;b[7]=0xd0;b[9]=(2<<5)|2;b[11]=2;
 checksum(sink.dc_edid.raw_edid);checksum(b);
 assert(dv_plane_neutral(&ps.base,&cs.base.mode));assert(!amdgpu_dm_dv_atomic_check(&atomic));
 unsigned missed=0;
 #define REJECT(field,bad) do {typeof(field) saved=(field);(field)=(bad);if(amdgpu_dm_dv_atomic_check(&atomic)!=-EINVAL){fprintf(stderr,"Unprotected: %s\n",#field);++missed;}stream.dv_standard=false;assert(!amdgpu_dm_dv_atomic_check(&atomic));stream.dv_standard=true;(field)=saved;assert(!amdgpu_dm_dv_atomic_check(&atomic));}while(0)
 REJECT(dp.in_transfer_func.type,TF_TYPE_BYPASS+1);REJECT(dp.blend_tf.type,TF_TYPE_BYPASS+1);
 REJECT(dp.lut3d_func.state.bits.initialized,true);REJECT(dp.input_csc_color_matrix.enable_adjustment,true);
 REJECT(ps.ctm,&ps);REJECT(ps.degamma_tf,AMDGPU_TRANSFER_FUNCTION_PQ);
 REJECT(ps.base.src_w,1920u<<16);REJECT(ps.base.crtc_h,1080);REJECT(format.format,999);
 REJECT(plane.type,DRM_PLANE_TYPE_CURSOR);REJECT(stream.timing.flags.DSC,true);
 REJECT(stream.timing.display_color_depth,COLOR_DEPTH_888+1);REJECT(stream.gamut_remap_matrix.enable_remap,true);
 REJECT(con.hdr10_deep_color,true);REJECT(con.base.hdr_output_metadata,&con);
 REJECT(con.base.max_requested_bpc,10);REJECT(connector.connector_type,999);
 REJECT(cs.base.vrr_enabled,true);REJECT(cs.base.ctm,&cs);REJECT(cs.base.connector_mask,3);
 REJECT(display.debug.visual_confirm,VISUAL_CONFIRM_SURFACE);
 REJECT(display.debug.always_scale,true);
 struct dc_transfer_func stream_shaper={TF_TYPE_BYPASS},mcm_shaper=stream_shaper,mcm_one=stream_shaper;
 struct dc_3dlut stream_lut={0},mcm_lut={0};
 stream.func_shaper=&stream_shaper;stream.lut3d_func=&stream_lut;
 dp.mcm_luts.shaper=&mcm_shaper;dp.mcm_luts.lut1d_func=&mcm_one;
 dp.mcm_luts.lut3d_data.lut3d_func=&mcm_lut;
 assert(!amdgpu_dm_dv_atomic_check(&atomic));
 REJECT(stream_shaper.type,TF_TYPE_BYPASS+1);
 REJECT(stream_lut.state.bits.initialized,true);
 REJECT(mcm_shaper.type,TF_TYPE_BYPASS+1);
 REJECT(mcm_one.type,TF_TYPE_BYPASS+1);
 REJECT(mcm_lut.state.bits.initialized,true);
 REJECT(dp.mcm_lut1d_enable,true);
 REJECT(dp.mcm_shaper_3dlut_setting,DC_CM2_SHAPER_3DLUT_SETTING_ENABLE_SHAPER);
 REJECT(dp.mcm_luts.lut3d_data.mpc_3dlut_enable,true);
 REJECT(dp.mcm_luts.lut3d_data.rmcm_3dlut_enable,true);
 // A VIDMEM address is not a kernel pointer, even when enable bits are zero.
 typeof(dp.mcm_luts.lut3d_data) vidmem={.lut3d_src=DC_CM2_TRANSFER_FUNC_SOURCE_VIDMEM,
     .gpu_mem_params.addr=0x12340000};
 REJECT(dp.mcm_luts.lut3d_data,vidmem);
 display.config.use_spl=true;
 REJECT(display.debug.force_sharpness,SHARPNESS_ZERO);
 display.debug.force_sharpness=SHARPNESS_CUSTOM;
 REJECT(display.debug.force_sharpness_level,2);
 REJECT(dp.adaptive_sharpness_en,true);
 display.debug.disable_spl=true;dp.adaptive_sharpness_en=true;
 assert(!amdgpu_dm_dv_atomic_check(&atomic));
 display.debug.disable_spl=false;display.debug.force_sharpness=SHARPNESS_HW_OFF;
 assert(!amdgpu_dm_dv_atomic_check(&atomic));
 display.config.use_spl=false;dp.adaptive_sharpness_en=false;
 assert(!missed);
 /* A stop/ordinary commit is not constrained by the DV byte-preserving contract. */
 stream.dv_standard=false;cs.base.ctm=&cs;con.base.hdr_output_metadata=&con;
 assert(!amdgpu_dm_dv_atomic_check(&atomic));
}
