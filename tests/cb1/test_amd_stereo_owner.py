"""Execute AMD's real stereo admission and transition owners, without a receiver."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


FLAGS = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
typedef uint32_t u32;
#define DRM_MODE_FLAG_INTERLACE (1 << 4)
#define DRM_MODE_FLAG_3D_MASK (0x1f << 14)
#define DRM_MODE_FLAG_3D_FRAME_PACKING (1 << 14)
#define DRM_MODE_FLAG_3D_FIELD_ALTERNATIVE (2 << 14)
#define DRM_MODE_FLAG_3D_LINE_ALTERNATIVE (3 << 14)
#define DRM_MODE_FLAG_3D_SIDE_BY_SIDE_FULL (4 << 14)
#define DRM_MODE_FLAG_3D_L_DEPTH (5 << 14)
#define DRM_MODE_FLAG_3D_L_DEPTH_GFX_GFX_DEPTH (6 << 14)
#define DRM_MODE_FLAG_3D_TOP_AND_BOTTOM (7 << 14)
#define DRM_MODE_FLAG_3D_SIDE_BY_SIDE_HALF (8 << 14)
#define DRM_MODE_CONNECTOR_HDMIA 11
#define DRM_MODE_CONNECTOR_DisplayPort 10
#define DRM_MODE_CONNECTOR_eDP 14
struct drm_display_mode { unsigned flags; };
struct drm_connector { int connector_type; struct {bool is_hdmi,has_hdmi_infoframe;}display_info; };
'''

MODES = FLAGS.replace('struct drm_display_mode { unsigned flags; };', r'''
struct drm_display_mode {
    unsigned flags;
    int clock,hdisplay,hsync_start,hsync_end,htotal,hskew;
    int vdisplay,vsync_start,vsync_end,vtotal,vscan;
    int crtc_clock,crtc_hdisplay,crtc_hsync_start,crtc_hsync_end,crtc_htotal,crtc_hskew;
    int crtc_vdisplay,crtc_vsync_start,crtc_vsync_end,crtc_vtotal;
    int crtc_vblank_start,crtc_vblank_end,crtc_hblank_start,crtc_hblank_end;
};
''') + r'''
#define DRM_MODE_FLAG_DBLSCAN (1 << 5)
#define CRTC_INTERLACE_HALVE_V 1
#define CRTC_NO_DBLSCAN 2
#define CRTC_NO_VSCAN 4
#define CRTC_STEREO_DOUBLE 8
#define min(a,b) ((a)<(b)?(a):(b))
#define max(a,b) ((a)>(b)?(a):(b))
'''


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class AMDNativeStereo(unittest.TestCase):
    def source(self, name):
        return (Path(os.environ['CB1_KERNEL_SOURCE']) /
                'drivers/gpu/drm/amd/display' / name).read_text()

    def run_c(self, code, headers=None):
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'test.c', Path(directory)/'test'
            source.write_text(code)
            for name, text in (headers or {}).items():
                (Path(directory)/name).write_text(text)
            built = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                '-fsanitize=address,undefined', str(source), '-o', str(binary)],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)

    def test_real_stream_entry_rejects_unrepresentable_stereo_before_allocation(self):
        source = self.source('amdgpu_dm/amdgpu_dm.c')
        owner = function(source.replace('struct dc_stream_state *\ncreate_stream_for_sink',
                                        'struct dc_stream_state *create_stream_for_sink'),
                         'create_stream_for_sink')
        # Keep the actual early returns; allocation starts after this boundary.
        admission = owner[owner.index('\tif (amdgpu_dm_hdr10_validate('):
                          owner.index('\tdrm_mode_init(')]
        helper = (function(source, 'amdgpu_dm_stereo_mode_supported')
                  if 'amdgpu_dm_stereo_mode_supported(' in source else '')
        self.run_c(FLAGS + r'''
struct dm_connector_state { bool dv_standard; };
static int amdgpu_dm_hdr10_validate(const struct dm_connector_state *state)
{ (void)state; return 0; }
''' + helper + r'''
static void *entry(struct drm_connector *connector,
                  const struct drm_display_mode *drm_mode,
                  const struct dm_connector_state *dm_state)
{
    (void)connector;
''' + admission + r'''
    return (void *)1;
}
int main(void)
{
    struct drm_connector connector = {.connector_type=DRM_MODE_CONNECTOR_HDMIA,
                                      .display_info={true,true}};
    struct drm_display_mode mode = {0};
    struct dm_connector_state state = {false};
    const unsigned accepted[] = {0, 1, 7, 8};
    for (unsigned layout=0; layout<32; ++layout) {
        bool supported = false;
        for (unsigned j=0; j<4; ++j) supported |= layout == accepted[j];
        mode.flags = layout << 14;
        assert((entry(&connector,&mode,&state) != NULL) == supported);
        mode.flags |= DRM_MODE_FLAG_INTERLACE;
        assert((entry(&connector,&mode,&state) != NULL) == (layout == 0));
        mode.flags = layout << 14;
        state.dv_standard = true;
        assert((entry(&connector,&mode,&state) != NULL) == (layout == 0));
        state.dv_standard = false;
        connector.connector_type = DRM_MODE_CONNECTOR_DisplayPort;
        assert((entry(&connector,&mode,&state) != NULL) == (layout == 0));
        connector.connector_type = DRM_MODE_CONNECTOR_eDP;
        assert((entry(&connector,&mode,&state) != NULL) == (layout == 0));
        connector.connector_type = DRM_MODE_CONNECTOR_HDMIA;
        connector.display_info.is_hdmi=false;
        assert((entry(&connector,&mode,&state) != NULL) == (layout == 0));
        connector.display_info.is_hdmi=true;
        connector.display_info.has_hdmi_infoframe=false;
        assert((entry(&connector,&mode,&state) != NULL) == (layout == 0));
        connector.display_info.has_hdmi_infoframe=true;
    }
}
''')

    def test_native_hdmi_packet_replaces_3d_with_explicit_2d(self):
        kernel = Path(os.environ['CB1_KERNEL_SOURCE'])
        source = self.source('amdgpu_dm/amdgpu_dm.c')
        owner = function(source.replace('struct dc_stream_state *\ncreate_stream_for_sink',
                                        'struct dc_stream_state *create_stream_for_sink'),
                         'create_stream_for_sink')
        start = owner.index('\tif (stream->signal == SIGNAL_TYPE_HDMI_TYPE_A')
        end = owner.index('\n\tif (stream->signal == SIGNAL_TYPE_DISPLAY_PORT', start)
        native = (function(source, 'amdgpu_dm_build_hdmi_vsif')
                  if 'amdgpu_dm_build_hdmi_vsif(' in source else '')
        hdmi = (kernel/'drivers/video/hdmi.c').read_text()
        edid = (kernel/'drivers/gpu/drm/drm_edid.c').read_text()
        packers = '\n'.join(function(hdmi, n) for n in (
            'hdmi_infoframe_checksum', 'hdmi_infoframe_set_checksum',
            'hdmi_vendor_infoframe_init', 'hdmi_vendor_infoframe_length',
            'hdmi_vendor_infoframe_check_only', 'hdmi_vendor_infoframe_check',
            'hdmi_vendor_infoframe_pack_only', 'hdmi_vendor_infoframe_pack'))
        dc_builder = function(self.source('modules/info_packet/info_packet.c'),
                              'mod_build_hf_vsif_infopacket')
        self.run_c(FLAGS.replace('struct drm_display_mode { unsigned flags; };',
                               'struct drm_display_mode { unsigned flags; int hdmi_vic; };')
            .replace('struct drm_connector { int connector_type; };',
                     'struct drm_connector { int connector_type; '
                     'struct { bool has_hdmi_infoframe; } display_info; };') + r'''
#include <sys/types.h>
#include <linux/types.h>
#include <errno.h>
typedef uint8_t u8; typedef uint16_t u16; typedef uint64_t u64;
struct device;
#include "hdmi-test.h"
#define ASSERT assert
#define HF_VSIF_VERSION 2
enum dc_timing_3d_format { TIMING_3D_FORMAT_NONE,
 TIMING_3D_FORMAT_HW_FRAME_PACKING, TIMING_3D_FORMAT_SW_FRAME_PACKING,
 TIMING_3D_FORMAT_SIDE_BY_SIDE, TIMING_3D_FORMAT_SBS_SW_PACKED,
 TIMING_3D_FORMAT_TOP_AND_BOTTOM, TIMING_3D_FORMAT_TB_SW_PACKED };
enum view_3d_format { VIEW_3D_FORMAT_NONE, VIEW_3D_FORMAT_TOP_AND_BOTTOM,
 VIEW_3D_FORMAT_SIDE_BY_SIDE, VIEW_3D_FORMAT_FRAME_SEQUENTIAL };
enum { COLOR_DEPTH_UNDEFINED,COLOR_DEPTH_666,COLOR_DEPTH_888,COLOR_DEPTH_101010,
 COLOR_DEPTH_121212,COLOR_DEPTH_141414,COLOR_DEPTH_161616,
 SIGNAL_TYPE_HDMI_TYPE_A,SIGNAL_TYPE_HDMI_FRL };
struct dc_info_packet { bool valid; uint8_t hb0,hb1,hb2,hb3,sb[32]; };
struct dc_stream_state {
    int signal;
    struct { int hdmi_vic,h_total,v_total,display_color_depth;
             enum dc_timing_3d_format timing_3d_format; } timing;
    enum view_3d_format view_format;
    struct dc_info_packet vsp_infopacket;
};
static int drm_mode_hdmi_vic(const struct drm_connector *c,const struct drm_display_mode *m)
{ (void)c; return m->hdmi_vic; }
static int s3d_structure_from_display_mode(const struct drm_display_mode *m)
{ (void)m; return HDMI_3D_STRUCTURE_INVALID; }
''' + packers + '\n' + function(edid, 'drm_hdmi_vendor_infoframe_from_display_mode')
            + '\n' + dc_builder + '\n' + native + r'''
static void build(struct dc_stream_state *stream,struct drm_connector *connector,
                  struct drm_display_mode mode)
{
    (void)connector;
''' + owner[start:end] + r'''
}
int main(void)
{
    struct drm_connector c={.display_info.has_hdmi_infoframe=true};
    struct dc_stream_state s={.signal=SIGNAL_TYPE_HDMI_TYPE_A};
    struct drm_display_mode m={0};
    // Start with a dirty old packet: all bytes must be deterministically replaced.
    memset(&s.vsp_infopacket,0xcc,sizeof(s.vsp_infopacket));
    build(&s,&c,m);
    assert(s.vsp_infopacket.valid);
    assert(s.vsp_infopacket.hb0==0x81 && s.vsp_infopacket.hb1==1);
    assert(s.vsp_infopacket.hb2==4 && s.vsp_infopacket.hb3==0);
    assert(s.vsp_infopacket.sb[0]==0x6b && s.vsp_infopacket.sb[1]==3);
    assert(s.vsp_infopacket.sb[2]==12 && !s.vsp_infopacket.sb[4]);
    for(unsigned i=5;i<32;++i) assert(!s.vsp_infopacket.sb[i]);
    const unsigned layouts[]={7,8,1};
    const unsigned lengths[]={6,6,5};
    const unsigned values[]={0x60,0x80,0};
    for(unsigned i=0;i<3;++i) {
        m.flags=layouts[i]<<14;
        build(&s,&c,m);
        assert(s.vsp_infopacket.valid && s.vsp_infopacket.hb2==lengths[i]);
        assert(s.vsp_infopacket.sb[4]==0x40 && s.vsp_infopacket.sb[5]==values[i]);
        unsigned sum=s.vsp_infopacket.hb0+s.vsp_infopacket.hb1+s.vsp_infopacket.hb2;
        for(unsigned j=0;j<=lengths[i];++j) sum+=s.vsp_infopacket.sb[j];
        assert(!(sum&255));
        assert(s.view_format==VIEW_3D_FORMAT_NONE);
        assert(s.timing.timing_3d_format==TIMING_3D_FORMAT_NONE);
    }
    m.flags=0;build(&s,&c,m);
    assert(s.vsp_infopacket.valid && s.vsp_infopacket.hb2==4);
    assert(!s.vsp_infopacket.sb[4] && !s.vsp_infopacket.sb[5]);
    c.display_info.has_hdmi_infoframe=false;
    build(&s,&c,m);assert(!s.vsp_infopacket.valid);
}
''', {'hdmi-test.h': re.sub(r'^#include .*$', '',
                (kernel/'include/linux/hdmi.h').read_text(), flags=re.M)})

    def test_vsif_change_reaches_both_stream_reuse_and_pipe_reprogram_gates(self):
        source = self.source('dc/core/dc_resource.c')
        owners = '\n'.join(function(source, name) for name in (
            'dc_is_timing_changed', 'are_stream_backends_same',
            'dc_is_stream_unchanged', 'pipe_need_reprogram'))
        self.run_c(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>
struct dc_info_packet { bool valid; uint8_t hb0,hb1,hb2,hb3,sb[32]; };
struct dc_crtc_timing { int clock; };
struct link_encoder { int unused; };
struct dc_stream_state;
struct pool_funcs { void *link_encs_assign; };
struct pool { struct pool_funcs *funcs; };
struct dc { struct { bool unify_link_enc_assignment; } config; struct pool *res_pool; };
struct dc_context { struct dc *dc; };
struct dc_stream_state {
    bool dv_standard,dpms_off,ignore_msa_timing_param;
    int output_color_space,audio_info,signal;
    struct dc_crtc_timing timing;
    struct dc_info_packet vsp_infopacket;
    void *sink;
    struct { bool link_state_valid; } *link;
    struct dc_context *ctx;
    struct link_encoder *link_enc;
};
struct pipe_ctx {
    struct dc_stream_state *stream;
    void *clock_source;
    struct { void *audio,*stream_enc,*dsc,*hpo_frl_stream_enc,*hpo_dp_stream_enc; } stream_res;
    struct { void *hpo_dp_link_enc,*dio_link_enc; } link_res;
};
static struct link_encoder *link_enc_cfg_get_link_enc_used_by_stream_current(
    struct dc *dc,struct dc_stream_state *stream)
{ (void)dc; return stream->link_enc; }
''' + owners + r'''
int main(void)
{
    struct pool_funcs funcs={0}; struct pool pool={&funcs};
    struct dc dc={.res_pool=&pool}; struct dc_context ctx={&dc};
    struct dc_stream_state old={.ctx=&ctx}, next=old;
    struct { bool link_state_valid; } link={true};
    old.link=(void *)&link;next.link=(void *)&link;
    struct pipe_ctx a={.stream=&old},b={.stream=&next};
    assert(dc_is_stream_unchanged(&old,&next));
    assert(!pipe_need_reprogram(&a,&b));
    // Same timing, but enter TAB, switch to SBS-half, then explicit2D.
    const unsigned layout[]={0x60,0x80,0};
    for (unsigned i=0;i<3;++i) {
        memset(&next.vsp_infopacket,0,sizeof(next.vsp_infopacket));
        next.vsp_infopacket.valid=true;
        next.vsp_infopacket.hb0=0x81;next.vsp_infopacket.hb1=1;
        next.vsp_infopacket.hb2=i==2?4:6;
        next.vsp_infopacket.sb[1]=3;next.vsp_infopacket.sb[2]=12;
        next.vsp_infopacket.sb[4]=i==2?0:0x40;
        next.vsp_infopacket.sb[5]=layout[i];
        assert(!dc_is_stream_unchanged(&old,&next));
        assert(pipe_need_reprogram(&a,&b));
        old=next;
        assert(dc_is_stream_unchanged(&old,&next));
        assert(!pipe_need_reprogram(&a,&b));
    }
    next.vsp_infopacket.valid=false;
    assert(!dc_is_stream_unchanged(&old,&next));
    assert(pipe_need_reprogram(&a,&b));
    old=next;
    // Disabled payload residue must not force a mode change.
    next.vsp_infopacket.sb[12]=0x52;
    assert(dc_is_stream_unchanged(&old,&next));
    assert(!pipe_need_reprogram(&a,&b));
    assert(!dc_is_stream_unchanged(NULL,&next));
}
''')

    def test_frame_packing_keeps_native_crtc_doubling_with_scaling(self):
        source = self.source('amdgpu_dm/amdgpu_dm.c')
        drm = (Path(os.environ['CB1_KERNEL_SOURCE'])/'drivers/gpu/drm/drm_modes.c').read_text()
        owners = '\n'.join((function(drm, 'drm_mode_set_crtcinfo'),
            function(source, 'copy_crtc_timing_for_drm_display_mode'),
            function(source, 'decide_crtc_timing_for_drm_display_mode')))
        self.run_c(MODES + owners + r'''
int main(void)
{
    struct drm_display_mode base={.clock=74250,.hdisplay=1920,.htotal=2750,
        .hsync_start=2558,.hsync_end=2602,.vdisplay=1080,.vsync_start=1084,
        .vsync_end=1089,.vtotal=1125};
    drm_mode_set_crtcinfo(&base,0);
    for(int scale=0;scale<2;++scale) {
        struct drm_display_mode fp=base;
        fp.flags=DRM_MODE_FLAG_3D_FRAME_PACKING;
        drm_mode_set_crtcinfo(&fp,CRTC_STEREO_DOUBLE);
        decide_crtc_timing_for_drm_display_mode(&fp,&base,scale);
        assert(fp.crtc_clock==148500 && fp.crtc_vdisplay==2205);
        assert(fp.crtc_vtotal==2250 && fp.crtc_vsync_start==2209);
        struct drm_display_mode tab=base;
        tab.flags=DRM_MODE_FLAG_3D_TOP_AND_BOTTOM;
        drm_mode_set_crtcinfo(&tab,CRTC_STEREO_DOUBLE);
        decide_crtc_timing_for_drm_display_mode(&tab,&base,scale);
        assert(tab.crtc_clock==74250 && tab.crtc_vdisplay==1080);
        assert(tab.crtc_vtotal==1125);
    }
    // Ordinary preferred-mode scaling is not changed.
    struct drm_display_mode ordinary=base,native=base;
    native.crtc_hdisplay=3840;
    decide_crtc_timing_for_drm_display_mode(&ordinary,&native,true);
    assert(ordinary.crtc_hdisplay==3840);
}
''')

    def test_freesync_video_cannot_replace_stereo_with_2d_base(self):
        source = self.source('amdgpu_dm/amdgpu_dm.c')
        self.run_c(MODES + r'''
struct amdgpu_dm_connector { struct drm_display_mode *highest; };
static struct drm_display_mode *get_highest_refresh_rate_mode(
    struct amdgpu_dm_connector *c,bool use_preferred)
{ (void)use_preferred; return c->highest; }
''' + function(source, 'is_freesync_video_mode') + r'''
int main(void)
{
    struct drm_display_mode base={.clock=74250,.hdisplay=1920,.vdisplay=1080};
    struct drm_display_mode mode=base;
    struct amdgpu_dm_connector c={&base};
    assert(is_freesync_video_mode(&mode,&c));
    const unsigned layouts[]={1,7,8};
    for(unsigned i=0;i<3;++i) {
        mode.flags=layouts[i]<<14;
        assert(!is_freesync_video_mode(&mode,&c));
    }
    assert(!is_freesync_video_mode(NULL,&c));
}
''')

    def test_freesync_reuse_cannot_hide_changed_stereo_layout(self):
        source = self.source('amdgpu_dm/amdgpu_dm.c')
        self.run_c(MODES + r'''
struct drm_crtc_state { struct drm_display_mode mode; };
''' + function(source, 'is_timing_unchanged_for_freesync') + r'''
int main(void)
{
    struct drm_crtc_state old={.mode={.clock=74250,.vtotal=1125,
        .vsync_start=1084,.vsync_end=1089}},next=old;
    next.mode.vtotal=1200;next.mode.vsync_start=1159;next.mode.vsync_end=1164;
    assert(is_timing_unchanged_for_freesync(&old,&next));
    next.mode.flags=DRM_MODE_FLAG_3D_TOP_AND_BOTTOM;
    assert(!is_timing_unchanged_for_freesync(&old,&next));
    old.mode.flags=DRM_MODE_FLAG_3D_TOP_AND_BOTTOM;
    assert(is_timing_unchanged_for_freesync(&old,&next));
    next.mode.flags=DRM_MODE_FLAG_3D_SIDE_BY_SIDE_HALF;
    assert(!is_timing_unchanged_for_freesync(&old,&next));
}
''')


if __name__ == '__main__':
    unittest.main()
