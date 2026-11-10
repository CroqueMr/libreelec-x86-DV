"""The title scan decides the cadence and display rate of a title before playback.

The shipped TitleScan, FieldAnalysis and FilmCadence code reads corpus files through a
plain file reader, the only part replaced; Kodi reads files and DVD titles the same way.
"""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

from kodi_patch_files import write_patched_files

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/dvd-cadence'))
import corpus  # noqa: E402

FFMPEG_INCLUDE = os.environ.get('FFMPEG_DEV_INCLUDE', '/usr/include/ffmpeg')
SECONDS = 6
SEGMENTS = 8
SEGMENT_SECONDS = 2

LOG_STUB = '''#pragma once
enum { LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR };
struct CLog
{
  template<class... A> static void Log(A&&...) {}
  template<class... A> static void LogF(A&&...) {}
};
'''

DRIVER = r'''
#include "TitleScan.h"
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>
extern "C" {
#include <libavutil/log.h>
}
using namespace FILM_CADENCE;

class CFileData : public ITitleData
{
public:
  CFileData(const char* path, int delayMs) : m_file(std::fopen(path, "rb")), m_delayMs(delayMs) {}
  ~CFileData() override { std::fclose(m_file); }
  int Read(uint8_t* buffer, int size) override
  {
    // slow media: every read waits
    std::this_thread::sleep_for(std::chrono::milliseconds(m_delayMs));
    return static_cast<int>(std::fread(buffer, 1, size, m_file));
  }
  int64_t Seek(int64_t position) override
  {
    return fseeko(m_file, position, SEEK_SET) == 0 ? position : -1;
  }
  int64_t Size() override
  {
    const off_t position = ftello(m_file);
    fseeko(m_file, 0, SEEK_END);
    const off_t size = ftello(m_file);
    fseeko(m_file, position, SEEK_SET);
    return size;
  }

private:
  FILE* m_file;
  const int m_delayMs;
};

int main(int argc, char** argv)
{
  av_log_set_level(AV_LOG_QUIET);
  CFileData data(argv[1], argc > 2 ? std::atoi(argv[2]) : 0);
  const ScanResult result = ScanTitle(data, ScanLimits{});
  const char* cadence = !result.plan ? "-"
                        : result.plan->softTelecine ? "soft telecine"
                                                    : Name(result.plan->cadence);
  std::printf("%s|%.3f|%d|%d|%d\n", cadence, result.plan ? DisplayRate(*result.plan) : 0.0,
              result.frames, result.segments, result.elapsedMs);
  return 0;
}
'''


def concat(out, parts, extra):
    """Encode lavfi sources one after another as one stream."""
    inputs = ''.join(f'{graph},setpts=PTS-STARTPTS[v{i}];' for i, graph in enumerate(parts))
    labels = ''.join(f'[v{i}]' for i in range(len(parts)))
    corpus.encode(f'{inputs}{labels}concat=n={len(parts)}:v=1:a=0,fps=30000/1001', out, extra)


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('c++') and
                     Path(FFMPEG_INCLUDE, 'libavfilter/avfilter.h').is_file(),
                     'requires ffmpeg, c++ and FFmpeg development headers')
class TitleScanTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        work = Path(cls.directory.name)
        prefix = 'xbmc/cores/VideoPlayer/DVDCodecs/Video/'
        names = ('FilmCadence.h', 'FilmCadence.cpp', 'FieldAnalysis.h', 'FieldAnalysis.cpp',
                 'TitleScan.h', 'TitleScan.cpp')
        if not write_patched_files([prefix + name for name in names], work):
            raise unittest.SkipTest('the title scan is not in the Kodi patch stack')
        work = work / prefix
        (work / 'utils').mkdir()
        (work / 'utils/log.h').write_text(LOG_STUB)
        (work / 'driver.cpp').write_text(DRIVER)
        cls.driver = work / 'driver'
        subprocess.run(['c++', '-std=c++20', '-O2', '-I', str(work), '-I', FFMPEG_INCLUDE,
                        str(work / 'driver.cpp'), str(work / 'TitleScan.cpp'),
                        str(work / 'FieldAnalysis.cpp'), str(work / 'FilmCadence.cpp'),
                        '-lavformat', '-lavfilter', '-lavcodec', '-lavutil', '-o',
                        str(cls.driver)], check=True, capture_output=True)
        cls.samples = Path(cls.directory.name) / 'samples'
        corpus.main([str(cls.samples), '--seconds', str(SECONDS)])
        ntsc = corpus.NTSC
        # Animation drawn on twos: every frame shown twice, a period of two frames.
        corpus.encode(corpus.source(ntsc, '15000/1001', SECONDS) + ',fps=30000/1001',
                      cls.samples / 'ntsc_twos.mpg')
        # A long title: static titles, then 25 fps film with a repeated frame in six.
        concat(cls.samples / 'title_repeat.mpg',
               [f'color=c=gray:size=720x480:rate=30000/1001:duration=24,format=yuv420p',
                corpus.source(ntsc, corpus.REPEAT_FILM, 40) + ',fps=30000/1001'], ())
        # A long title, half hard-telecined film and half interlaced video.
        concat(cls.samples / 'title_mixed.mpg',
               [corpus.source(ntsc, corpus.FILM, 32) + ',telecine=first_field=top:pattern=23',
                corpus.source(ntsc, '60000/1001', 32) + ',interlace=scan=tff'],
               corpus.INTERLACED)

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def scan(self, name, read_delay_ms=0):
        out = subprocess.run([str(self.driver), str(self.samples / name), str(read_delay_ms)],
                             check=True, capture_output=True, text=True).stdout.strip()
        cadence, rate, frames, segments, elapsed = out.split('|')
        return cadence, float(rate), int(frames), int(segments), int(elapsed)

    def test_each_cadence_gives_its_plan_and_display_rate(self):
        expected = {
            'ntsc_soft32.mpg': ('soft telecine', 23.976),
            'ntsc_hard32.mpg': ('inverse telecine', 23.976),
            'ntsc_video.mpg': ('video deinterlacing', 59.94),
            'ntsc_repeat.mpg': ('frame repeat removal', 25.0),
            'ntsc_progressive.mpg': ('progressive', 29.97),
            'ntsc_twos.mpg': ('progressive', 29.97),
            'pal_22.mpg': ('field matching', 25.0),
            'pal_22_progressive.mpg': ('progressive', 25.0),
            'pal_video.mpg': ('video deinterlacing', 50.0),
        }
        if (self.samples / 'ntsc_soft32_h264.mkv').is_file():
            expected['ntsc_soft32_h264.mkv'] = ('soft telecine', 23.976)
        for name, (cadence, rate) in expected.items():
            result = self.scan(name)
            self.assertEqual(result[0], cadence, name)
            self.assertAlmostEqual(result[1], rate, places=2, msg=name)

    def test_a_static_start_does_not_delay_the_decision(self):
        cadence, rate, frames, segments, _ = self.scan('title_repeat.mpg')
        self.assertEqual((cadence, rate), ('frame repeat removal', 25.0))
        # sample points spread over the title, not a decode from its start
        self.assertEqual(segments, SEGMENTS)
        self.assertLessEqual(frames, SEGMENTS * int(SEGMENT_SECONDS * 30000 / 1001))

    def test_slow_media_stop_at_the_budget_with_spread_sample_points(self):
        cadence, rate, _, segments, elapsed = self.scan('title_repeat.mpg', read_delay_ms=25)
        self.assertLess(elapsed, 1500 + 200)  # the default budget, and one read
        self.assertTrue(1 < segments < SEGMENTS, segments)
        # the points decoded before the deadline reach past the static start
        self.assertEqual((cadence, rate), ('frame repeat removal', 25.0))

    def test_a_title_without_a_majority_cadence_has_no_plan(self):
        self.assertEqual(self.scan('title_mixed.mpg')[0], '-')


if __name__ == '__main__':
    unittest.main()
