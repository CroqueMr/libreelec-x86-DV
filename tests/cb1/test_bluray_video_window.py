"""Presentation follows source PTS, independently of decode order and Kodi offsets."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class BlurayVideoWindow(unittest.TestCase):
    def test_source_clock_window_is_inclusive_and_reordered_references_are_decode_only(self):
        prefix = os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:
            self.skipTest('Matched FFmpeg required')
        prefix=Path(prefix)
        source=(TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/BlurayDovi.h').read_text()
        signature='bool DecodeOnly(int64_t pts, AVRational clock) const'
        native=body(source,signature) if signature in source else '{return false;}'
        program=r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
extern "C" {
#include <libavutil/avutil.h>
#include <libavutil/mathematics.h>
}
struct Window {bool active=false;int64_t first=0,last=0;
 bool DecodeOnly(int64_t pts,AVRational clock)const BODY
};
int main() {
 Window window{true,655338900,655695506};
 assert(window.DecodeOnly(655327638,{1,90000})&&"Pre-IN IDR must decode without presentation");
 // Actual order in the problematic transport: DTS order must not become presentation order.
 for(int64_t pts:{655357668,655342653,655335146,655331392,655338900})
  assert(window.DecodeOnly(pts,{1,90000})==(pts<window.first));
 assert(!window.DecodeOnly(window.first,{1,90000}));
 assert(!window.DecodeOnly(window.last,{1,90000}));
 assert(window.DecodeOnly(window.last+1,{1,90000}));
 assert(!window.DecodeOnly(window.first/2,{1,45000}));
 assert(window.DecodeOnly(window.first/2-1,{1,45000}));
 assert(window.DecodeOnly(AV_NOPTS_VALUE,{1,90000}));
 assert(window.DecodeOnly(window.first,{0,90000}));
 assert(window.DecodeOnly(window.first,{1,0}));
 window={true,(INT64_C(1)<<32)+100,(INT64_C(1)<<32)+200};
 assert(!window.DecodeOnly(window.first,{1,90000}));
 assert(window.DecodeOnly(window.first-1,{1,90000}));
 window={true,(INT64_C(1)<<33)-90000,(INT64_C(1)<<33)-45000};
 assert(!window.DecodeOnly(-90000,{1,90000}));
 assert(!window.DecodeOnly(-45000,{1,90000}));
 assert(window.DecodeOnly(-90001,{1,90000}));
 assert(window.DecodeOnly(-44999,{1,90000}));
 assert(!window.DecodeOnly(-45000,{1,45000}));
 assert(window.DecodeOnly(AV_NOPTS_VALUE,{1,90000}));
 window.active=false;
 for(int64_t pts:{AV_NOPTS_VALUE,INT64_C(-1),INT64_C(0),INT64_MAX})
  assert(!window.DecodeOnly(pts,{1,90000}));
}
'''.replace('BODY',native)
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary);(folder/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(prefix/'include'),str(folder/'test.cpp'),'-L'+str(prefix/'lib'),
                '-lavutil','-lm','-o',str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(folder/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__=='__main__':
    unittest.main()
