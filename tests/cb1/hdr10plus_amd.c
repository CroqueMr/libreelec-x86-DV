/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
typedef uint8_t u8;
struct drm_property_blob { unsigned long length; void *data; };
struct dc_info_packet { bool valid; u8 hb0, hb1, hb2, hb3, sb[32]; };
#include "drm_hdr10plus.h"
#include "amd_packet.inc"
struct dc_stream_state {struct {unsigned vic,hdmi_vic;}timing;struct dc_info_packet vsp_infopacket;};
struct drm_display_mode {unsigned vic;};
static unsigned drm_match_cea_mode(const struct drm_display_mode *m){return m->vic;}
#include "amd_stream.inc"
struct drm_plane {int unused;};
struct drm_crtc {struct drm_plane *primary;};
struct drm_plane_state {struct drm_crtc *crtc;void *fb;void *dc_state;};
struct drm_atomic_commit {struct drm_plane_state *plane;};
static inline struct drm_plane_state *drm_atomic_get_new_plane_state(struct drm_atomic_commit *s,struct drm_plane *p)
{(void)p;return s->plane;}
#define to_dm_plane_state(p) (p)
#include "amd_frame.inc"
int main(void)
{
    struct drm_plane primary={0};struct drm_crtc crtc={&primary},other={&primary};
    struct drm_atomic_commit state={0};
    assert(!hdr10plus_has_frame_update(&state,&crtc));
    struct drm_plane_state plane={.crtc=&crtc,.fb=&primary,.dc_state=&primary};
    state.plane=&plane;assert(hdr10plus_has_frame_update(&state,&crtc));
    plane.crtc=&other;assert(!hdr10plus_has_frame_update(&state,&crtc));
    plane.crtc=&crtc;plane.fb=NULL;assert(!hdr10plus_has_frame_update(&state,&crtc));
    plane.fb=&primary;plane.dc_state=NULL;assert(!hdr10plus_has_frame_update(&state,&crtc));
    u8 data[31]={0x81,1,27,0,0x8b,0x84,0x90,0x7e,
        10,1,0,255,4,8,16,32,64,128,0,0,0,0,0,0,0,0,0,0,0,0,0x40};
    struct drm_property_blob blob={31,data};
    struct dc_info_packet p={0},before;
    assert(fill_hdr10plus_info_packet(&blob,&p)==0);
    assert(p.valid && p.hb0==0x81 && p.hb1==1 && p.hb2==27 && p.hb3==0);
    assert(!memcmp(p.sb,data+3,28));
    for(unsigned vic=93;vic<=95;++vic){
        struct drm_display_mode mode={vic};
        struct dc_stream_state stream={.timing={0,96-vic}};
        assert(fill_hdr10plus_stream_packet(&blob,&stream,&mode)==0);
        assert(stream.timing.vic==vic && stream.timing.hdmi_vic==0);
        assert(stream.vsp_infopacket.valid && !memcmp(stream.vsp_infopacket.sb,data+3,28));
    }
    struct drm_display_mode cinema={98},unknown={0};
    struct dc_stream_state stream={.timing={0,4}};
    assert(fill_hdr10plus_stream_packet(&blob,&stream,&cinema)==0);
    assert(stream.timing.vic==98 && stream.timing.hdmi_vic==0);
    stream.timing.hdmi_vic=4;assert(fill_hdr10plus_stream_packet(&blob,&stream,&unknown)==-EINVAL);
    stream.timing.hdmi_vic=0;stream.timing.vic=97;
    assert(fill_hdr10plus_stream_packet(&blob,&stream,&unknown)==0 && stream.timing.vic==97);
    for(unsigned i=28;i<32;i++)assert(!p.sb[i]);
    before=p;
    blob.length=30;
    assert(fill_hdr10plus_info_packet(&blob,&p)==-EINVAL);
    assert(!memcmp(&p,&before,sizeof(p)));
    blob.length=31;data[8]^=1;
    assert(fill_hdr10plus_info_packet(&blob,&p)==-EINVAL);
    assert(!memcmp(&p,&before,sizeof(p)));
    puts("hdr10plus AMD packet: pass");
}
