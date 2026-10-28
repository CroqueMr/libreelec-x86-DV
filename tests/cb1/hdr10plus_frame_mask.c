/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
typedef uint32_t u32;
struct drm_plane;
struct drm_crtc {struct drm_plane *primary;unsigned mask;};
struct drm_plane {struct drm_crtc *crtc;void *fb;};
struct drm_plane_state {struct drm_crtc *crtc;void *fb;};
struct drm_atomic_commit {struct drm_plane *plane;struct drm_plane_state *state;};
#define for_each_new_plane_in_state(s,p,n,i) \
 for((i)=0;(i)<1 && (s)->state && (((p)=(s)->plane),((n)=(s)->state),true);++(i))
static u32 drm_crtc_mask(const struct drm_crtc *c){return c->mask;}
#include "frame_mask.inc"
int main(void)
{
 struct drm_plane plane={0};struct drm_crtc crtc={&plane,2};
 struct drm_plane_state primary={&crtc,&plane};
 struct drm_atomic_commit state={&plane,NULL};
 const u32 request_mask=drm_atomic_hdr10plus_frame_mask(&state);
 assert(request_mask==0);
 state.state=&primary; /* Native helpers add an inherited primary later. */
 assert(request_mask==0 && drm_atomic_hdr10plus_frame_mask(&state)==2);
 primary.fb=NULL;assert(drm_atomic_hdr10plus_frame_mask(&state)==0);
 primary.fb=&plane;crtc.primary=NULL;assert(drm_atomic_hdr10plus_frame_mask(&state)==0);
 crtc.primary=&plane;primary.crtc=NULL;assert(drm_atomic_hdr10plus_frame_mask(&state)==0);
}
