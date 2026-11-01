/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <errno.h>
#include <linux/types.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#include <sys/types.h>
typedef uint8_t u8;
typedef uint16_t u16;
typedef uint32_t u32;
struct device;
#include "hdmi-test.h"
#include "drm_hdr10plus.h"
#include "hdmi-functions.inc"
#define DRM_MODE_FLAG_3D_MASK 0xf00
enum { DRM_MODE_CONNECTOR_HDMIA=11,
       DRM_MODE_COLORIMETRY_BT2020_RGB=9, DRM_MODE_COLORIMETRY_BT2020_YCC=10 };
struct drm_crtc { void *primary; };
struct drm_plane_state { struct drm_crtc *crtc; void *fb; };
struct drm_atomic_commit { struct drm_plane_state *plane; };
struct intel_crtc { struct drm_crtc base; };
struct intel_connector { int unused; };
struct drm_property_blob {size_t length;void *data;};
struct hdr_output_metadata {unsigned metadata_type;struct {u8 eotf,metadata_type;} hdmi_metadata_type1;};
struct drm_display_info {bool hdr10plus_supported;unsigned hdr10plus_version;};
struct drm_connector {struct drm_display_info display_info;unsigned connector_type;};
struct drm_connector_state {
 struct drm_connector *connector;struct drm_crtc *crtc;unsigned max_bpc,colorspace;
 struct drm_property_blob *hdr_output_metadata,*hdr10plus_metadata;
};
#include "connector_check.inc"
struct intel_digital_connector_state {struct drm_connector_state base;bool dv_lab_standard;};
struct intel_crtc_state {
 bool has_hdmi_sink,has_infoframe;int pipe_bpp;
 struct {bool active,async_flip;}uapi;
 struct {struct {unsigned flags;}adjusted_mode;}hw;
 struct {union hdmi_infoframe hdmi;unsigned enable;}infoframes;
};
struct intel_atomic_state {
 struct drm_atomic_commit base;
 struct intel_crtc_state *pipe;
 struct intel_digital_connector_state *conn;
 unsigned hdr10plus_primary_mask;
};
static unsigned drm_crtc_mask(const struct drm_crtc *c){(void)c;return 1;}
#define __maybe_unused __attribute__((unused))
#define for_each_new_intel_connector_in_state(s,c,n,i) \
 for((i)=0;(i)<1 && (((n)=(s)->conn),true);++(i))
static struct intel_crtc_state *intel_atomic_get_new_crtc_state(struct intel_atomic_state*s,struct intel_crtc*c)
{(void)c;return s->pipe;}
static struct drm_plane_state *drm_atomic_get_new_plane_state(struct drm_atomic_commit*s,void*p)
{(void)p;return s->plane;}
static unsigned intel_hdmi_infoframe_enable(unsigned n){(void)n;return 1;}
#include "intel_check.inc"
int main(void)
{
 uint8_t packet[31]={0x81,1,27,0,0x8b,0x84,0x90,0x7e,
     10,1,0,255,4,8,16,32,64,128,0,0,0,0,0,0,0,0,0,0,0,0,0x40};
 struct intel_crtc crtc={0};struct drm_property_blob blob={sizeof(packet),packet};
 struct drm_connector connector={{true,1},DRM_MODE_CONNECTOR_HDMIA};
 struct hdr_output_metadata hdr={0,{HDMI_EOTF_SMPTE_ST2084,0}};
 struct drm_property_blob static_blob={sizeof(hdr),&hdr};
 struct intel_digital_connector_state conn={.base={&connector,&crtc.base,10,
     DRM_MODE_COLORIMETRY_BT2020_RGB,&static_blob,&blob}};
 struct intel_crtc_state pipe={.has_hdmi_sink=true,.has_infoframe=true,.pipe_bpp=30,.uapi={true,false}};
 struct drm_plane_state primary={&crtc.base,&blob};
 struct intel_atomic_state state={{&primary},&pipe,&conn,1};
 assert(intel_hdmi_hdr10plus_check(&state,&crtc)==0);
 state.hdr10plus_primary_mask=0;assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 state.hdr10plus_primary_mask=1;
 state.base.plane=NULL;assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 state.base.plane=&primary;primary.fb=NULL;assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 primary.fb=&blob;primary.crtc=NULL;assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 primary.crtc=&crtc.base;pipe.uapi.active=false;assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 pipe.uapi.active=true;pipe.uapi.async_flip=true;assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 pipe.uapi.async_flip=false;pipe.pipe_bpp=24;assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 pipe.pipe_bpp=30;
 const uint8_t modern_fields[][3]={{38,98,119},{30,82,143},{8,93,154}};
 for(unsigned i=0;i<sizeof(modern_fields)/sizeof(modern_fields[0]);i++){
     packet[3]=modern_fields[i][2];
     packet[10]=modern_fields[i][0];
     packet[11]=modern_fields[i][1];
     assert(intel_hdmi_hdr10plus_check(&state,&crtc)==0);
     u8 packed[31];
     assert(hdmi_vendor_any_infoframe_pack_only(&pipe.infoframes.hdmi.vendor,packed,sizeof(packed))==31);
     assert(!memcmp(packed,packet,sizeof(packet)));
     union hdmi_infoframe before=pipe.infoframes.hdmi;
     packet[15]^=1;
     assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
     assert(!memcmp(&before,&pipe.infoframes.hdmi,sizeof(before)));
     packet[15]^=1;
 }
 connector.display_info.hdr10plus_supported=false;
 assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 connector.display_info.hdr10plus_supported=true;
 connector.display_info.hdr10plus_version=0;
 assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
 connector.display_info.hdr10plus_version=1;
 conn.base.max_bpc=8;
 assert(intel_hdmi_hdr10plus_check(&state,&crtc)==-EINVAL);
}
