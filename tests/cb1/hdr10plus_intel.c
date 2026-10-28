/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
#define EINVAL 22
#define DRM_MODE_FLAG_3D_MASK 0xf00
#define HDMI_INFOFRAME_TYPE_VENDOR 0x81
struct drm_crtc { void *primary; };
struct drm_plane_state { struct drm_crtc *crtc; void *fb; };
struct drm_atomic_commit { struct drm_plane_state *plane; };
struct intel_crtc { struct drm_crtc base; };
struct intel_connector { int unused; };
struct packet {void *data;unsigned length;};
struct drm_connector_state { struct drm_crtc *crtc; struct packet *hdr10plus_metadata; };
struct intel_digital_connector_state {struct drm_connector_state base;bool dv_lab_standard;};
struct intel_crtc_state {
 bool has_hdmi_sink,has_infoframe;int pipe_bpp;
 struct {bool active,async_flip;}uapi;
 struct {struct {unsigned flags;}adjusted_mode;}hw;
 struct {int hdmi;unsigned enable;}infoframes;
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
static int drm_connector_check_hdr10plus(const struct drm_connector_state*s){(void)s;return 0;}
static int hdmi_infoframe_unpack(int*p,const void*d,unsigned n){(void)p;(void)d;(void)n;return 0;}
static unsigned intel_hdmi_infoframe_enable(unsigned n){(void)n;return 1;}
#include "intel_check.inc"
int main(void)
{
 struct intel_crtc crtc={0};struct packet blob={0,31};
 struct intel_digital_connector_state conn={.base={.crtc=&crtc.base}};
 conn.base.hdr10plus_metadata=&blob;
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
}
