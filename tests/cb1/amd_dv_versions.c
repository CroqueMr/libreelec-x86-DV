/* SPDX-License-Identifier: MIT */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <errno.h>
#include <stddef.h>
#include <string.h>
#include <sys/types.h>
#include <linux/types.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
#define BIT(n) (1u<<(n))
struct device;
#include "hdmi-test.h"
#include "drm_dvbridge.h"
@@PACKERS@@
enum dce_version {@@FAMILIES@@};
enum {DRM_MODE_CONNECTOR_HDMIA=1, SIGNAL_TYPE_HDMI_TYPE_A=2,
      PIXEL_ENCODING_RGB=3, DRM_HDMI_BROADCAST_RGB_FULL=4, COLOR_DEPTH_888=5,
      RMX_OFF=6, COLOR_SPACE_SRGB=7, TF_TYPE_BYPASS=8,
      TRANSFER_FUNCTION_LINEAR=9, DITHER_OPTION_DISABLE=10};
enum {DRM_MODE_FLAG_INTERLACE=1, DRM_MODE_FLAG_DBLSCAN=2,
      DRM_MODE_FLAG_DBLCLK=4, DRM_MODE_FLAG_3D_MASK=8};
struct dc_edid {unsigned length; u8 raw_edid[256];};
struct drm_connector {
    int connector_type;
    struct {bool is_hdmi,has_hdmi_infoframe;}display_info;
};
struct amdgpu_dm_connector {
    struct drm_connector base; bool dv_standard_property,timing_changed;
};
#define to_amdgpu_dm_connector(p) ((struct amdgpu_dm_connector *)(p))
struct dm_connector_state {
    struct {struct drm_connector *connector; struct{int broadcast_rgb;}hdmi;
        void *hdr_output_metadata; unsigned max_requested_bpc,colorspace;}base;
    bool dv_standard,hdr10_deep_color,underscan_enable; int scaling;
};
struct drm_display_mode {int hdisplay,vdisplay,clock,flags,vic,refresh;};
struct dc_info_packet {u8 hb0,hb1,hb2,sb[32];bool valid;};
struct dc_stream_state {
    struct {struct dc_edid dc_edid;}*sink;
    struct {enum dce_version dce_version;}*ctx;
    struct {int connector_signal;}*link;
    bool dv_standard;
    int signal,output_color_space,dither_option,qs_bit;
    struct {int type,tf;}out_transfer_func;
    struct {int pixel_encoding,display_color_depth,h_addressable,v_addressable;
        int pix_clk_100hz,hdmi_vic,vic;struct{bool DSC;}flags;}timing;
    struct dc_info_packet avi_infopacket,vsp_infopacket;
};
static bool dv_standard=true;
static int drm_mode_vrefresh(const struct drm_display_mode *m){return m->refresh;}
static int drm_match_cea_mode(const struct drm_display_mode *m){return m->vic;}
static int drm_hdmi_avi_infoframe_from_display_mode(struct hdmi_avi_infoframe *a,
    struct drm_connector *c,const struct drm_display_mode *m){
    hdmi_avi_infoframe_init(a);a->video_code=m->vic;return 0;
}
@@AMD@@
static void checksum(u8 *p){
    u8 sum=0;p[127]=0;for(int i=0;i<127;i++)sum+=p[i];p[127]=-sum;
}
static void edid(struct dc_edid *e,unsigned version,unsigned length,bool ll,bool sixty){
    memset(e,0,sizeof(*e));e->length=256;
    const u8 magic[]={0,255,255,255,255,255,255,0};
    memcpy(e->raw_edid,magic,8);e->raw_edid[126]=1;
    u8 *b=e->raw_edid+128;b[0]=2;b[1]=3;b[2]=5+length;b[4]=0xe0|length;
    b[5]=1;b[6]=0x46;b[7]=0xd0;b[9]=(version<<5)|(sixty?2:0);
    b[11]=2;b[12]=ll?1:0;checksum(e->raw_edid);checksum(b);
}
static unsigned sum(const struct dc_info_packet *p){
    u8 n=p->hb0+p->hb1+p->hb2;
    for(unsigned i=0;i<=p->hb2;i++)n+=p->sb[i];
    return n;
}
int main(void){
    struct amdgpu_dm_connector c={.base={DRM_MODE_CONNECTOR_HDMIA,{true,true}},
        .dv_standard_property=true};
    struct dm_connector_state state={.base={.connector=&c.base,.hdmi={DRM_HDMI_BROADCAST_RGB_FULL},
        .max_requested_bpc=8},.dv_standard=true,.scaling=RMX_OFF};
    struct drm_display_mode mode={3840,2160,297000,0,95,30};
    struct dc_stream_state s={.signal=SIGNAL_TYPE_HDMI_TYPE_A,
        .timing={.pixel_encoding=PIXEL_ENCODING_RGB,.display_color_depth=COLOR_DEPTH_888,
        .h_addressable=3840,.v_addressable=2160,.pix_clk_100hz=2970000}};
    typeof(*s.ctx) ctx={DCN_VERSION_1_0};s.ctx=&ctx;
    typeof(*s.link) link={SIGNAL_TYPE_HDMI_TYPE_A};s.link=&link;
    typeof(*s.sink) sink;s.sink=&sink;
    edid(&sink.dc_edid,2,11,false,true);
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==0);
    /* Frozen modern V2 bytes, including header/checksum and reserved tail. */
    const u8 v2[]={0x4b,0x46,0xd0,0,2,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0};
    assert(s.vsp_infopacket.hb0==0x81 && s.vsp_infopacket.hb1==1 && s.vsp_infopacket.hb2==27);
    assert(!memcmp(s.vsp_infopacket.sb,v2,sizeof(v2)));
    assert(s.timing.vic==95 && s.timing.hdmi_vic==0 && !sum(&s.vsp_infopacket));
    struct dc_info_packet frozen=s.vsp_infopacket;
    for(unsigned length=11;length<=14;length+=3)for(unsigned ll=0;ll<2;ll++){
        edid(&sink.dc_edid,1,length,ll,true);
        for(int vic=93;vic<=97;vic++){
            mode.vic=vic;mode.refresh=vic<96?30:60;
            assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==0);
            bool legacy=length==14 || !ll;
            if(legacy){
                assert(s.vsp_infopacket.sb[1]==3 && s.vsp_infopacket.sb[2]==0x0c);
                assert(s.timing.vic==(vic<=95?0:vic));
                assert(s.timing.hdmi_vic==(vic<=95?96-vic:0));
            }else assert(!memcmp(&s.vsp_infopacket,&frozen,sizeof(frozen)));
            assert(!sum(&s.vsp_infopacket) && !sum(&s.avi_infopacket));
        }
    }
    edid(&sink.dc_edid,1,14,false,false);
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==-EOPNOTSUPP);
    mode.refresh=30;mode.vic=95;
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==0);
    struct dc_info_packet saved=s.vsp_infopacket;
    edid(&sink.dc_edid,0,21,false,true);
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==-EOPNOTSUPP);
    edid(&sink.dc_edid,2,11,false,true);sink.dc_edid.raw_edid[139]=0;
    checksum(sink.dc_edid.raw_edid+128);
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==-EOPNOTSUPP);
    edid(&sink.dc_edid,1,12,false,true);
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==-EOPNOTSUPP);
    assert(!memcmp(&saved,&s.vsp_infopacket,sizeof(saved)));
    state.dv_standard=false;
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==0);
    assert(!memcmp(&saved,&s.vsp_infopacket,sizeof(saved)));
    state.dv_standard=true;edid(&sink.dc_edid,2,11,false,true);
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==0);
    assert(!memcmp(&frozen,&s.vsp_infopacket,sizeof(frozen)));
    state.base.hdr_output_metadata=&state;
    assert(amdgpu_dm_dv_configure_stream(&s,&state,&mode)==-EINVAL);
}
