"""Exercise the active HDMI audio configuration against an HDA pin register."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'requires the replayed pinned kernel')
class IntelHDMIPinOut(unittest.TestCase):
    def test_active_route(self):
        path = Path(os.environ['CB1_KERNEL_SOURCE']) / 'sound/hda/codecs/hdmi/hdmi.c'
        source = path.read_text()
        refresh = function(source, 'snd_hda_hdmi_setup_audio_infoframe')
        update = function(source, 'update_eld')
        self.assertLess(update.index('hdmi_pcm_setup_pin('), update.index('if (eld_changed)'))
        self.assertIn('snd_hda_hdmi_setup_audio_infoframe(', function(source, 'hdmi_pcm_setup_pin'))
        prepare = function(source, 'snd_hda_hdmi_generic_pcm_prepare')
        self.assertLess(prepare.index('scoped_guard(mutex, &per_pin->lock)'),
                        prepare.index('adlp_restore_pin_out('))
        self.assertLess(prepare.index('snd_hda_hdmi_setup_audio_infoframe('),
                        prepare.index('adlp_restore_pin_out('))
        reconcile = function(source, 'adlp_restore_pin_out')
        driver = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#define PIN_OUT 0x40
#define AC_VERB_GET_PIN_WIDGET_CONTROL 0xf07
#define AC_VERB_SET_PIN_WIDGET_CONTROL 0x707
#define AC_PAR_DEVLIST_LEN 0x15
#define AC_WCAP_OUT_AMP 1
#define AC_VERB_SET_AMP_GAIN_MUTE 0x300
#define AMP_OUT_UNMUTE 0
typedef unsigned short hda_nid_t;
struct hda_codec;
struct hdac { unsigned vendor_id; };
struct hdmi_eld {
    bool eld_valid, monitor_present;
    int eld_size;
    unsigned char eld_buffer[2];
    struct { int spk_alloc, conn_type, sad_count; } info;
};
struct hdac_chmap { struct { void (*set_channel_count)(struct hdac*, int, int); } ops; };
struct hdmi_spec {
    unsigned long pcm_in_use;
    bool static_pcm_mapping;
    struct hdac_chmap chmap;
    struct { void (*pin_setup_infoframe)(struct hda_codec*, int, int, int, int, int); } ops;
};
struct hdmi_spec_per_pin {
    hda_nid_t cvt_nid, pin_nid;
    int dev_id, pcm_idx, channels;
    bool non_pcm, chmap_set, setup;
    unsigned char chmap[8];
    struct hdmi_eld sink_eld;
};
struct hda_codec { struct hdac core; struct hdmi_spec *spec; };
/* Channel mapping is unchanged and does not touch PIN_WIDGET_CONTROL. */
#define get_wcaps(c,n) 0
#define snd_hdac_channel_allocation(c,s,ch,m,np,map) (0)
#define snd_hdac_get_active_channels(ca) (2)
#define snd_hdac_setup_channel_mapping(...) ((void)0)
static void set_channels(struct hdac *c, int cvt, int ch) { (void)c; (void)cvt; (void)ch; }
static void infoframe(struct hda_codec *c, int p, int d, int ca, int ch, int t) {
    (void)c; (void)p; (void)d; (void)ca; (void)ch; (void)t;
}
static int selected, select_status, regs[2], reads, writes, entries;
static bool latch;
static inline int snd_hdac_read_parm_uncached(struct hdac *c, int pin, int param) {
    (void)c; assert(pin == 7 && param == AC_PAR_DEVLIST_LEN); return entries;
}
static inline int test_bit(int bit, unsigned long *map) { return (*map >> bit) & 1; }
static int snd_hda_set_dev_select(struct hda_codec *c, hda_nid_t pin, int id) {
    (void)c; assert(pin == 7 && (id == 0 || id == 1));
    if (select_status == 0 && latch) selected = id;
    return select_status;
}
static inline int snd_hda_get_dev_select(struct hda_codec *c, hda_nid_t pin) {
    (void)c; assert(pin == 7); return entries == 0 ? -1 : selected;
}
static inline unsigned snd_hda_codec_read(struct hda_codec *c, hda_nid_t pin,
                                           int flags, int verb, int value) {
    (void)c; assert(pin == 7 && !flags && verb == AC_VERB_GET_PIN_WIDGET_CONTROL && !value);
    reads++; return (unsigned)regs[entries == 0 ? 0 : selected];
}
static inline int snd_hda_codec_write(struct hda_codec *c, hda_nid_t pin,
                                      int flags, int verb, int value) {
    (void)c; assert(pin == 7 && !flags && verb == AC_VERB_SET_PIN_WIDGET_CONTROL);
    writes++; regs[entries == 0 ? 0 : selected] = value; return 0;
}
'''
        eld_calls = r'''
struct snd_jack {};
#define snd_parse_eld(...) 0
#define snd_show_eld(...) ((void)0)
#define schedule_delayed_work(...) ((void)0)
#define hdmi_attach_hda_pcm(...) ((void)0)
#define hdmi_detach_hda_pcm(...) ((void)0)
#define hdmi_pcm_reset_pin(...) ((void)0)
#define pin_cvt_fixup(...) ((void)0)
#define snd_jack_report(...) ((void)0)
#define snd_ctl_notify(...) ((void)0)
#define pin_idx_to_pcm_jack(...) NULL
static struct hda_codec *active_codec;
static void hdmi_pcm_setup_pin(struct hdmi_spec *spec, struct hdmi_spec_per_pin *pin) {
    (void)spec;
    snd_hda_hdmi_setup_audio_infoframe(active_codec, pin, false);
}
'''
        cases = r'''
int main(void) {
    struct scenario {
        const char *name; int reg, dev, pcm, active; bool eld;
        unsigned id; int status; bool latch; int reads, writes, entries, conn_type;
    } tests[] = {
        {"single-entry HDMI after modeset", 0, 0, 2, 4, true, 0x8086281c, 0, false, 1, 1, 0, 0},
        {"HBR on the same HDMI route", 3, 0, 2, 4, true, 0x8086281c, 0, false, 1, 1, 0, 0},
        {"invalid hardware length and unconfirmed owner", 0, 0, 2, 4, true, 0x8086281c, 0, false, 0, 0, -1, 0},
        {"nonzero owner on single-entry HDMI", 3, 1, 2, 4, true, 0x8086281c, 0, false, 0, 0, 0, 0},
        {"DP rejects missing selector", 0, 0, 2, 4, true, 0x8086281c, 0, false, 0, 0, 0, 1},
        {"PCM output disabled", 0, 0, 2, 4, true, 0x8086281c, 0, true, 1, 1, 1, 1},
        {"HBR output disabled", 3, 1, 2, 4, true, 0x8086281c, 0, true, 1, 1, 1, 1},
        {"HBR already enabled", 0x43, 1, 2, 4, true, 0x8086281c, 0, true, 1, 0, 1, 1},
        {"no valid ELD", 3, 0, 2, 4, false, 0x8086281c, 0, true, 0, 0, 1, 1},
        {"unassigned PCM", 3, 0, -1, 4, true, 0x8086281c, 0, true, 0, 0, 1, 1},
        {"another PCM open", 3, 0, 2, 2, true, 0x8086281c, 0, true, 0, 0, 1, 1},
        {"different codec", 3, 0, 2, 4, true, 0x8086281d, 0, true, 0, 0, 1, 1},
        {"failed device select", 0, 1, 2, 4, true, 0x8086281c, -1, false, 0, 0, 1, 1},
        {"device select ignored", 0, 1, 2, 4, true, 0x8086281c, 0, false, 0, 0, 1, 1},
        {"pin read failed", -1, 0, 2, 4, true, 0x8086281c, 0, true, 1, 0, 1, 1},
    };
    for (unsigned i = 0; i < sizeof(tests)/sizeof(tests[0]); i++) {
        struct scenario s = tests[i];
        struct hdmi_spec spec = { .pcm_in_use = s.active, .chmap.ops.set_channel_count = set_channels,
                                  .ops.pin_setup_infoframe = infoframe };
        struct hda_codec codec = { .core.vendor_id = s.id, .spec = &spec };
        struct hdmi_spec_per_pin pin = { .pin_nid = 7, .dev_id = s.dev, .pcm_idx = s.pcm,
                                        .channels = 2, .setup = false, .sink_eld = { .eld_valid = s.eld,
                                        .info.conn_type = s.conn_type } };
        entries = s.entries; selected = 1 - s.dev; regs[selected] = 2; regs[s.dev] = s.reg;
        reads = writes = 0; select_status = s.status; latch = s.latch;
        /* A synthetic silent stream can have channels without a prepared route. */
        adlp_restore_pin_out(&codec, &pin);
        assert(!reads && !writes);
        pin.setup = true;
        adlp_restore_pin_out(&codec, &pin);
        if (reads != s.reads || writes != s.writes || regs[1 - s.dev] != 2 ||
            regs[s.dev] != (s.writes ? s.reg | PIN_OUT : s.reg)) {
            fprintf(stderr, "%s: reads=%d writes=%d reg=%d\n", s.name, reads, writes, regs[s.dev]);
            return 1;
        }
        if (s.writes) {
            /* Repeating the same ELD refresh must only write if a modeset reset the pin. */
            adlp_restore_pin_out(&codec, &pin);
            assert(writes == 1);
            regs[s.dev] = s.reg;
            adlp_restore_pin_out(&codec, &pin);
            assert(writes == 2 && regs[s.dev] == (s.reg | PIN_OUT));
        }
    }
    /* ELD refresh first configures the PCM, then replaces the cached ELD.
     * An HDMI-to-DP change cannot reuse HDMI's single-entry exception. */
    struct hdmi_spec spec = { .pcm_in_use = 1, .chmap.ops.set_channel_count = set_channels,
                             .ops.pin_setup_infoframe = infoframe };
    struct hda_codec codec = { .core.vendor_id = 0x8086281c, .spec = &spec };
    struct hdmi_spec_per_pin pin = { .pin_nid = 7, .dev_id = 0, .pcm_idx = 0, .channels = 2,
        .setup = true, .sink_eld = { .eld_valid = true, .eld_size = 1,
                                     .info = { .conn_type = 0, .sad_count = 1 } } };
    struct hdmi_eld next = pin.sink_eld;
    active_codec = &codec;
    entries = select_status = reads = writes = regs[0] = 0;
    latch = false;
    next.info.conn_type = 1;
    next.eld_buffer[0] = 1;
    update_eld(&codec, &pin, &next, 0);
    assert(pin.sink_eld.info.conn_type == 1 && !writes && !reads);
    next.info.conn_type = 0;
    next.eld_buffer[0] = 2;
    update_eld(&codec, &pin, &next, 0);
    assert(pin.sink_eld.info.conn_type == 0 && writes == 1 && regs[0] == PIN_OUT);
    regs[0] = 3;
    update_eld(&codec, &pin, &next, 0);
    assert(writes == 2 && regs[0] == (3 | PIN_OUT));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp) / 'pin.c', Path(tmp) / 'pin'
            source.write_text('\n'.join((driver, reconcile, refresh, eld_calls, update, cases)))
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(source),
                            '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
