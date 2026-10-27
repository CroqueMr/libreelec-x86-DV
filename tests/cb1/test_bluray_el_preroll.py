"""A common IRAP can retire an earlier EL decode prefix, never its references."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class BlurayEnhancementPreroll(unittest.TestCase):
    def test_common_irap_recovery_and_unproven_prefix_refusal(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"
#include <cassert>

AVPacket* packet(bool el, int64_t pts, int64_t dts, int marker, int type) {
  AVPacket* p = av_packet_alloc();
  assert(p && av_new_packet(p, el ? 13 : 6) == 0);
  const uint8_t base[] = {0,0,1,uint8_t(type << 1),1,uint8_t(marker)};
  const uint8_t layer[] = {0,0,0,1,uint8_t(type << 1),1,uint8_t(marker),
                          0,0,1,0x7c,1,uint8_t(pts)};
  memcpy(p->data, el ? layer : base, p->size);
  p->pts = pts;
  p->dts = dts;
  return p;
}
void push(CBlurayDovi& join, bool el, int64_t pts, int64_t dts, int marker, int type=1) {
  AVPacket* p = packet(el, pts, dts, marker, type);
  assert(join.Push(p, el));
  av_packet_free(&p);
}

int main() {
  CBlurayDovi join;
  AVPacket* out = av_packet_alloc();
  assert(out);
  // Reordered presentation times, monotone decode times. Both layers have a
  // CRA at decode index 3. The BL seek starts there; EL starts three AUs earlier.
  const int pts[] = {30,10,20,60,40,50};
  join.Reset(true);
  for (int i=3; i<6; ++i)
    push(join, false, pts[i], i, 10+i, i==3 ? 21 : 1);
  for (int i=0; i<6; ++i) {
    push(join, true, pts[i], i, 100+i, i==3 ? 21 : 1);
    if (i<3) {
      assert(join.Take(out)==AVERROR(EAGAIN));
      continue;
    }
    assert(join.Take(out)==0);
    assert(out->pts==pts[i] && out->dts==i);
    assert(out->size==22 && out->data[5]==10+i);
    assert(out->data[14]==100+i && "EL must start at the common CRA, not the orphan prefix");
    assert(out->data[out->size-1]==pts[i]);
    av_packet_unref(out);
  }
  assert(join.TakePrerollCount()==3 && !join.Pending());

  // A timestamp match is insufficient: retain references without both IRAPs,
  // exact decode clocks, and proof that each retired RPU is orphaned.
  for (int refusal=0; refusal<5; ++refusal) {
    join.Reset(true);
    push(join, false, 100, 90, 1, refusal==0 ? 1 : 21);
    if (refusal==4)
      push(join, false, 80, 91, 2); // This leading BL picture still needs RPU80.
    push(join, true, 70, 70, 3);
    push(join, true, 80, refusal==2 ? AV_NOPTS_VALUE : 80, 4);
    push(join, true, 100, refusal==3 ? 91 : 90, 5, refusal==1 ? 1 : 21);
    assert(join.Take(out)==AVERROR(EAGAIN));
    assert(join.Pending());
    assert(join.TakePrerollCount()==0);
  }
  join.Reset(true);
  AVPacket* unknown = packet(true, AV_NOPTS_VALUE, AV_NOPTS_VALUE, 1, 21);
  assert(!join.Push(unknown, true) && !strcmp(join.LastError(), "packet"));
  av_packet_free(&unknown);
  av_packet_free(&out);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'test.cpp').write_text(program)
            built = subprocess.run([
                'c++', '-std=c++20', '-fsanitize=address,undefined',
                '-I'+str(TREE/'xbmc'), '-I'+str(prefix/'include'), str(root/'test.cpp'),
                '-L'+str(prefix/'lib'), '-lavcodec', '-lavutil', '-lm', '-o', str(root/'test'),
            ], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
