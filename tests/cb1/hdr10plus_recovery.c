/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Compile production recovery and frame-mask functions; no display hardware. */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
typedef uint32_t u32;
struct drm_plane;
struct drm_crtc { struct drm_plane *primary; unsigned mask; };
struct drm_plane_state { struct drm_crtc *crtc; void *fb; };
struct drm_plane { unsigned index; struct drm_plane_state current; };
struct intel_crtc_state { struct { bool connectors_changed; } uapi; };
struct intel_crtc { struct drm_crtc base; unsigned pipe; };
struct drm_modeset_acquire_ctx { int unused; };
struct intel_display { void *drm; struct intel_crtc crtcs[2]; };
struct drm_atomic_commit {
 struct drm_modeset_acquire_ctx *acquire_ctx;
 struct drm_plane *planes[2]; struct drm_plane_state *new_states[2];
 struct intel_crtc_state crtcs[2]; bool internal;
};
static struct drm_atomic_commit transaction;
static struct drm_plane planes[2];
static struct intel_display display;
static struct drm_modeset_acquire_ctx context;
static int allocation_fails, crtc_error, plane_error, commit_error;
static unsigned released, committed, requested, acquired, captured;
#define IS_ERR(p) ((uintptr_t)(p) >= (uintptr_t)-4095)
#define PTR_ERR(p) ((int)(intptr_t)(p))
#define ERR_PTR(e) ((void *)(intptr_t)(e))
#define to_intel_atomic_state(s) (s)
#define for_each_intel_crtc_in_pipe_mask(d,c,m) \
 for (unsigned index=0; index<2; ++index) \
  if (((c)=&(d)->crtcs[index]), (m)&(1u<<index))
#define for_each_new_plane_in_state(s,p,n,i) \
 for ((i)=0; (i)<2; ++(i)) \
  if (((p)=(s)->planes[i]), ((n)=(s)->new_states[i]))
static u32 drm_crtc_mask(const struct drm_crtc *crtc) { return crtc->mask; }
static struct drm_atomic_commit *drm_atomic_commit_alloc(void *device)
{ assert(device==&display); return allocation_fails ? NULL : &transaction; }
static void drm_atomic_commit_put(struct drm_atomic_commit *state)
{ assert(state==&transaction); ++released; }
static struct intel_crtc_state *intel_atomic_get_crtc_state(
 struct drm_atomic_commit *state, struct intel_crtc *crtc)
{
 assert(state->acquire_ctx==&context && state->internal);
 requested |= 1u<<crtc->pipe;
 return crtc_error ? ERR_PTR(crtc_error) : &state->crtcs[crtc->pipe];
}
static struct drm_plane_state *drm_atomic_get_plane_state(
 struct drm_atomic_commit *state, struct drm_plane *plane)
{
 assert(state->acquire_ctx==&context && state->internal);
 if (plane_error) return ERR_PTR(plane_error);
 acquired |= 1u<<plane->index;
 state->planes[plane->index]=plane;
 state->new_states[plane->index]=&plane->current;
 return &plane->current;
}
#include "frame_mask.inc"
static int drm_atomic_commit(struct drm_atomic_commit *state)
{
 ++committed;
 /* intel_atomic_check snapshots before helper expansion. */
 captured=drm_atomic_hdr10plus_frame_mask(state);
 for (unsigned i=0;i<2;++i) {
  if (!(requested & (1u<<i))) continue;
  assert(state->crtcs[i].uapi.connectors_changed);
  state->planes[i]=&planes[i]; state->new_states[i]=&planes[i].current;
 }
 /* The existing six contracts test the complete HDMI admission separately. */
 if (captured!=requested) return -EINVAL;
 return commit_error;
}
#include "recovery.inc"
static void reset(void)
{
 memset(&transaction,0,sizeof(transaction));
 allocation_fails=crtc_error=plane_error=commit_error=0;
 released=committed=requested=acquired=captured=0;
 display.drm=&display;
 for (unsigned i=0;i<2;++i) {
  display.crtcs[i]=(struct intel_crtc){{&planes[i],1u<<i},i};
  planes[i]=(struct drm_plane){i,{&display.crtcs[i].base,&planes[i]}};
 }
}
int main(void)
{
 const unsigned masks[]={1,2,3};
 for (unsigned i=0;i<3;++i) {
  reset(); int ret=intel_modeset_commit_pipes(&display,masks[i],&context);
  if (ret) { fprintf(stderr,"valid existing primary: ret=%d mask=%u expected=%u\n",ret,captured,masks[i]); return 1; }
  assert(acquired==masks[i] && captured==masks[i] && committed==1 && released==1);
 }
 for (unsigned i=0;i<2;++i) {
  const int errors[]={-EDEADLK,-ENOMEM};
  reset(); plane_error=errors[i];
  assert(intel_modeset_commit_pipes(&display,1,&context)==errors[i]);
  assert(!committed && released==1);
  reset(); crtc_error=errors[i];
  assert(intel_modeset_commit_pipes(&display,1,&context)==errors[i]);
  assert(!committed && !acquired && released==1);
 }
 reset(); allocation_fails=1;
 assert(intel_modeset_commit_pipes(&display,1,&context)==-ENOMEM);
 assert(!committed && !released);
 reset(); commit_error=-EDEADLK;
 assert(intel_modeset_commit_pipes(&display,1,&context)==-EDEADLK);
 assert(committed==1 && released==1);
 reset(); planes[0].current.fb=NULL;
 assert(intel_modeset_commit_pipes(&display,1,&context)==-EINVAL);
 reset(); planes[0].current.crtc=NULL;
 assert(intel_modeset_commit_pipes(&display,1,&context)==-EINVAL);
 puts("PASS: existing primaries, pipe selection, acquisition errors/deadlock, release, and invalid primary rejection");
}
