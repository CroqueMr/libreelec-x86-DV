"""Exercise the pinned Intel HDMI route fixup with HDA register state."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'requires the replayed pinned kernel')
class IntelHDMIPinOut(unittest.TestCase):
    def test_active_route(self):
        path = Path(os.environ['CB1_KERNEL_SOURCE']) / 'sound/hda/codecs/hdmi/intelhdmi.c'
        fixup = function(path.read_text(), 'i915_pin_cvt_fixup')
        driver = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#define PIN_OUT 0x40
#define AC_VERB_GET_PIN_WIDGET_CONTROL 0xf07
#define AC_VERB_SET_PIN_WIDGET_CONTROL 0x707
typedef unsigned short hda_nid_t;
struct hdmi_spec { unsigned long pcm_in_use; };
struct hdmi_spec_per_pin {
    hda_nid_t cvt_nid, pin_nid;
    int dev_id, pcm_idx, mux_idx;
    struct { bool eld_valid; } sink_eld;
};
struct hda_codec { struct { unsigned vendor_id; } core; struct hdmi_spec *spec; };
/* Unrelated routing helpers in the native callback. */
#define haswell_verify_D0(...) ((void)0)
#define intel_verify_pin_cvt_connect(...) ((void)0)
#define intel_not_share_assigned_cvt(...) ((void)0)
#define intel_not_share_assigned_cvt_nid(c, p, d, n) ((void)(n))
static int selected, select_status, regs[2], reads, writes;
static bool latch;
static inline int test_bit(int bit, unsigned long *map) { return (*map >> bit) & 1; }
static int snd_hda_set_dev_select(struct hda_codec *c, hda_nid_t pin, int id) {
    (void)c; assert(pin == 7 && (id == 0 || id == 1));
    if (select_status == 0 && latch) selected = id;
    return select_status;
}
static inline int snd_hda_get_dev_select(struct hda_codec *c, hda_nid_t pin) {
    (void)c; assert(pin == 7); return selected;
}
static inline unsigned snd_hda_codec_read(struct hda_codec *c, hda_nid_t pin,
                                           int flags, int verb, int value) {
    (void)c; assert(pin == 7 && !flags && verb == AC_VERB_GET_PIN_WIDGET_CONTROL && !value);
    reads++; return (unsigned)regs[selected];
}
static inline int snd_hda_codec_write(struct hda_codec *c, hda_nid_t pin,
                                      int flags, int verb, int value) {
    (void)c; assert(pin == 7 && !flags && verb == AC_VERB_SET_PIN_WIDGET_CONTROL);
    writes++; regs[selected] = value; return 0;
}
'''
        cases = r'''
int main(void) {
    struct scenario {
        const char *name; int reg, dev, pcm, active; bool eld;
        unsigned id; int status; bool latch; int reads, writes;
    } tests[] = {
        {"PCM output disabled", 0, 0, 2, 4, true, 0x8086281c, 0, true, 1, 1},
        {"HBR output disabled", 3, 1, 2, 4, true, 0x8086281c, 0, true, 1, 1},
        {"HBR already enabled", 0x43, 1, 2, 4, true, 0x8086281c, 0, true, 1, 0},
        {"no valid ELD", 3, 0, 2, 4, false, 0x8086281c, 0, true, 0, 0},
        {"unassigned PCM", 3, 0, -1, 4, true, 0x8086281c, 0, true, 0, 0},
        {"another PCM open", 3, 0, 2, 2, true, 0x8086281c, 0, true, 0, 0},
        {"different codec", 3, 0, 2, 4, true, 0x8086281d, 0, true, 0, 0},
        {"failed device select", 0, 1, 2, 4, true, 0x8086281c, -1, false, 0, 0},
        {"device select ignored", 0, 1, 2, 4, true, 0x8086281c, 0, false, 0, 0},
        {"pin read failed", -1, 0, 2, 4, true, 0x8086281c, 0, true, 1, 0},
    };
    for (unsigned i = 0; i < sizeof(tests)/sizeof(tests[0]); i++) {
        struct scenario s = tests[i];
        struct hdmi_spec spec = { .pcm_in_use = s.active };
        struct hda_codec codec = { .core.vendor_id = s.id, .spec = &spec };
        struct hdmi_spec_per_pin pin = { .pin_nid = 7, .dev_id = s.dev, .pcm_idx = s.pcm,
                                        .sink_eld.eld_valid = s.eld };
        selected = 1 - s.dev; regs[selected] = 2; regs[s.dev] = s.reg;
        reads = writes = 0; select_status = s.status; latch = s.latch;
        i915_pin_cvt_fixup(&codec, NULL, 2);
        i915_pin_cvt_fixup(&codec, &pin, 0);
        if (reads != s.reads || writes != s.writes || regs[1 - s.dev] != 2 ||
            regs[s.dev] != (s.writes ? s.reg | PIN_OUT : s.reg)) {
            fprintf(stderr, "%s: reads=%d writes=%d reg=%d\n", s.name, reads, writes, regs[s.dev]);
            return 1;
        }
    }
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            source, binary = Path(tmp) / 'pin.c', Path(tmp) / 'pin'
            source.write_text('\n'.join((driver, fixup, cases)))
            subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror', str(source),
                            '-o', str(binary)], check=True)
            result = subprocess.run([str(binary)], text=True, capture_output=True)
            self.assertEqual(0, result.returncode, result.stderr)
