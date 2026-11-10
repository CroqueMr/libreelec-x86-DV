"""Film detection selects the reconstruction that fits each DVD cadence.

The shipped FieldAnalysis and FilmCadence code runs the FFmpeg idet analysis on
decoded corpus streams. The selected graph is then measured against the progressive
frames each sample was made from and the other methods.
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
import measure  # noqa: E402

FFMPEG_INCLUDE = os.environ.get('FFMPEG_DEV_INCLUDE', '/usr/include/ffmpeg')
SECONDS = 6

# Only the Kodi logger is replaced; it has no effect on the analysis.
LOG_STUB = '''#pragma once
enum { LOGDEBUG, LOGINFO, LOGWARNING, LOGERROR };
struct CLog
{
  template<class... A> static void Log(A&&...) {}
  template<class... A> static void LogF(A&&...) {}
};
'''

DRIVER = r'''
#include "FieldAnalysis.h"
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
}
#include <cstdio>
using namespace FILM_CADENCE;

int main(int argc, char** argv)
{
  AVFormatContext* format = nullptr;
  if (avformat_open_input(&format, argv[1], nullptr, nullptr) < 0 ||
      avformat_find_stream_info(format, nullptr) < 0)
    return 2;
  const int index = av_find_best_stream(format, AVMEDIA_TYPE_VIDEO, -1, -1, nullptr, 0);
  const AVCodec* codec = avcodec_find_decoder(format->streams[index]->codecpar->codec_id);
  AVCodecContext* context = avcodec_alloc_context3(codec);
  avcodec_parameters_to_context(context, format->streams[index]->codecpar);
  if (avcodec_open2(context, codec, nullptr) < 0)
    return 2;
  CFieldAnalysis analysis;
  AVPacket* packet = av_packet_alloc();
  AVFrame* frame = av_frame_alloc();
  bool eof = false;
  while (!eof)
  {
    if (av_read_frame(format, packet) < 0)
    {
      eof = true;
      avcodec_send_packet(context, nullptr);
    }
    else
    {
      if (packet->stream_index == index)
        avcodec_send_packet(context, packet);
      av_packet_unref(packet);
    }
    while (avcodec_receive_frame(context, frame) >= 0)
    {
      analysis.Analyse(frame);
      const auto cadence = analysis.Confirmed();
      std::printf("%s|%s\n", cadence ? Name(*cadence) : "-",
                  cadence ? FilterGraph(*cadence).c_str() : "");
    }
  }
  return 0;
}
'''


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('c++') and
                     Path(FFMPEG_INCLUDE, 'libavfilter/avfilter.h').is_file(),
                     'requires ffmpeg, c++ and FFmpeg development headers')
class FilmDetectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        work = Path(cls.directory.name)
        prefix = 'xbmc/cores/VideoPlayer/DVDCodecs/Video/'
        names = ('FilmCadence.h', 'FilmCadence.cpp', 'FieldAnalysis.h', 'FieldAnalysis.cpp')
        if not write_patched_files([prefix + name for name in names], work):
            raise unittest.SkipTest('film detection is not in the Kodi patch stack')
        work = work / prefix
        (work / 'utils').mkdir()
        (work / 'utils/log.h').write_text(LOG_STUB)
        (work / 'driver.cpp').write_text(DRIVER)
        cls.driver = work / 'driver'
        subprocess.run(['c++', '-std=c++20', '-O1', '-I', str(work), '-I', FFMPEG_INCLUDE,
                        str(work / 'driver.cpp'), str(work / 'FieldAnalysis.cpp'),
                        str(work / 'FilmCadence.cpp'), '-lavformat', '-lavfilter',
                        '-lavcodec', '-lavutil', '-o', str(cls.driver)],
                       check=True, capture_output=True)
        cls.samples = Path(cls.directory.name) / 'samples'
        corpus.main([str(cls.samples), '--seconds', str(SECONDS)])

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def detect(self, name):
        out = subprocess.run([str(self.driver), str(self.samples / f'{name}.mpg')], check=True,
                             capture_output=True, text=True).stdout.splitlines()
        return [tuple(line.split('|', 1)) for line in out]

    def test_each_cadence_is_detected_within_a_second(self):
        expected = {'ntsc_hard32': 'inverse telecine', 'pal_22': 'field matching',
                    'ntsc_video': 'video deinterlacing', 'pal_video': 'video deinterlacing'}
        for name, cadence in expected.items():
            decisions = [c for c, _ in self.detect(name)]
            first = next(i for i, c in enumerate(decisions) if c != '-')
            self.assertLessEqual(first, 30, name)
            self.assertEqual(set(decisions[first:]), {cadence}, name)

    def test_progressive_coding_is_left_to_the_decoder(self):
        for name in ('ntsc_soft32', 'pal_22_progressive'):
            self.assertEqual({c for c, _ in self.detect(name)}, {'-'}, name)

    def test_mixed_film_and_video_switches_once_after_the_change(self):
        decisions = [c for c, _ in self.detect('ntsc_mixed')]
        changes = [(i, c) for i, (p, c) in enumerate(zip(decisions, decisions[1:]), 1) if c != p]
        self.assertEqual([c for _, c in changes], ['inverse telecine', 'video deinterlacing'])
        middle = len(decisions) // 2
        self.assertTrue(middle <= changes[1][0] <= middle + 75, changes)

    def test_the_selected_graph_is_the_best_measured_method(self):
        for name in ('ntsc_hard32', 'ntsc_video', 'pal_22', 'pal_video'):
            graph = self.detect(name)[-1][1]
            path = self.samples / f'{name}.mpg'
            reference = measure.REFERENCE[name]
            _, selected = measure.process(path, graph, reference, SECONDS)
            best = max(measure.process(path, g, reference, SECONDS)[1]
                       for g in measure.METHODS.values())
            self.assertGreaterEqual(selected, best - 0.1, name)


if __name__ == '__main__':
    unittest.main()
