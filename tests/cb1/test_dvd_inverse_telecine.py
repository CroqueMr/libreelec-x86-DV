"""Inverse telecine rebuilds the film frames of hard-telecined and 2:2 DVD video.

The shipped FilmCadence graph and buffer source are run in libavfilter on decoded
corpus streams, with decoded timestamps in AV_TIME_BASE units as Kodi feeds them.
Output timing is checked as Kodi reads it; picture quality against the progressive
frames each sample was made from.
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
SECONDS = 4

DRIVER = r'''
#include "FilmCadence.h"
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavfilter/avfilter.h>
#include <libavfilter/buffersink.h>
#include <libavfilter/buffersrc.h>
#include <libavformat/avformat.h>
}
#include <cstdio>
#include <cstdlib>
#include <cstring>
using namespace FILM_CADENCE;

int main(int argc, char** argv)
{
  AVFormatContext* format = nullptr;
  if (avformat_open_input(&format, argv[1], nullptr, nullptr) < 0 ||
      avformat_find_stream_info(format, nullptr) < 0)
    return 2;
  const int index = av_find_best_stream(format, AVMEDIA_TYPE_VIDEO, -1, -1, nullptr, 0);
  AVStream* stream = format->streams[index];
  const AVCodec* codec = avcodec_find_decoder(stream->codecpar->codec_id);
  AVCodecContext* context = avcodec_alloc_context3(codec);
  avcodec_parameters_to_context(context, stream->codecpar);
  context->pkt_timebase = stream->time_base;
  if (avcodec_open2(context, codec, nullptr) < 0)
    return 2;

  AVFilterGraph* graph = nullptr;
  AVFilterContext *in = nullptr, *out = nullptr;
  AVRational rate{0, 1};
  Cadence cadence{};
  AVPacket* packet = av_packet_alloc();
  AVFrame* frame = av_frame_alloc();
  AVFrame* result = av_frame_alloc();

  auto drain = [&]() {
    while (av_buffersink_get_frame(out, result) >= 0)
    {
      const long long film = av_rescale_q(result->pts, av_buffersink_get_time_base(out),
                                          AV_TIME_BASE_Q);
      std::printf("%lld %lld\n", film, (long long)result->best_effort_timestamp);
      av_frame_unref(result);
    }
  };

  bool eof = false;
  while (!eof)
  {
    if (av_read_frame(format, packet) < 0)
    {
      eof = true;
      avcodec_send_packet(context, nullptr);
    }
    else if (packet->stream_index != index)
    {
      av_packet_unref(packet);
      continue;
    }
    else
    {
      avcodec_send_packet(context, packet);
      av_packet_unref(packet);
    }
    while (avcodec_receive_frame(context, frame) >= 0)
    {
      if (!graph)
      {
        rate = context->framerate;
        cadence = InverseTelecineCadence(av_q2d(rate));
        const std::string args = BufferSourceArgs(frame->width, frame->height, frame->format,
            frame->sample_aspect_ratio.num, frame->sample_aspect_ratio.den, rate.num, rate.den);
        graph = avfilter_graph_alloc();
        avfilter_graph_create_filter(&in, avfilter_get_by_name("buffer"), "in", args.c_str(),
                                     nullptr, graph);
        avfilter_graph_create_filter(&out, avfilter_get_by_name("buffersink"), "out", nullptr,
                                     nullptr, graph);
        AVFilterInOut* outputs = avfilter_inout_alloc();
        AVFilterInOut* inputs = avfilter_inout_alloc();
        outputs->name = av_strdup("in"); outputs->filter_ctx = in;
        inputs->name = av_strdup("out"); inputs->filter_ctx = out;
        if (avfilter_graph_parse_ptr(graph, FilterGraph(cadence).c_str(), &inputs, &outputs,
                                     nullptr) < 0 || avfilter_graph_config(graph, nullptr) < 0)
          return 3;
        avfilter_inout_free(&outputs);
        avfilter_inout_free(&inputs);
        std::printf("graph %s\n", FilterGraph(cadence).c_str());
        std::printf("duration %.3f\n", FilmFrameDuration(cadence, 1e6 / av_q2d(rate)));
      }
      // Kodi hands decoded timestamps to its graphs in AV_TIME_BASE units.
      frame->pts = av_rescale_q(frame->best_effort_timestamp, stream->time_base, AV_TIME_BASE_Q);
      frame->best_effort_timestamp = frame->pts;
      av_buffersrc_add_frame(in, frame);
      drain();
    }
  }
  av_buffersrc_add_frame(in, nullptr);
  drain();
  return 0;
}
'''


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('c++') and
                     Path(FFMPEG_INCLUDE, 'libavfilter/avfilter.h').is_file(),
                     'requires ffmpeg, c++ and FFmpeg development headers')
class InverseTelecineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        work = Path(cls.directory.name)
        prefix = 'xbmc/cores/VideoPlayer/DVDCodecs/Video/'
        if not write_patched_files([prefix + 'FilmCadence.h', prefix + 'FilmCadence.cpp'], work):
            raise unittest.SkipTest('FilmCadence is not in the Kodi patch stack')
        work = work / prefix
        (work / 'driver.cpp').write_text(DRIVER)
        cls.driver = work / 'driver'
        subprocess.run(['c++', '-std=c++20', '-O1', '-I', str(work), '-I', FFMPEG_INCLUDE,
                        str(work / 'driver.cpp'), str(work / 'FilmCadence.cpp'),
                        '-lavformat', '-lavfilter', '-lavcodec', '-lavutil', '-o',
                        str(cls.driver)], check=True, capture_output=True)
        cls.samples = Path(cls.directory.name) / 'samples'
        corpus.main([str(cls.samples), '--seconds', str(SECONDS)])

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def run_graph(self, name):
        lines = subprocess.run([str(self.driver), str(self.samples / f'{name}.mpg')],
                               check=True, capture_output=True, text=True).stdout.splitlines()
        graph = lines[0].split(' ', 1)[1]
        duration = float(lines[1].split()[1])
        frames = [tuple(int(v) for v in line.split()) for line in lines[2:]]
        return graph, duration, frames

    def check_film(self, name, film_rate, frame_duration):
        graph, duration, frames = self.run_graph(name)
        self.assertAlmostEqual(duration, frame_duration, places=0)
        self.assertEqual(len(frames), round(film_rate * SECONDS), name)
        steps = [b[0] - a[0] for a, b in zip(frames, frames[1:])]
        self.assertTrue(all(abs(step - frame_duration) <= 1 for step in steps), steps[:10])
        # Kodi restarts the graph when film and source time differ by more than 0.5 s.
        self.assertTrue(all(abs(film - source) <= 500000 for film, source in frames))
        reference = measure.REFERENCE[name]
        _, rebuilt = measure.process(self.samples / f'{name}.mpg', graph, reference, SECONDS)
        _, deinterlaced = measure.process(self.samples / f'{name}.mpg', measure.METHODS['bwdif'],
                                          reference, SECONDS)
        self.assertGreater(rebuilt, 45, name)  # MPEG-2 coding loss only
        self.assertGreater(rebuilt, deinterlaced + 5, name)

    def test_hard_telecine_is_rebuilt_as_evenly_timed_23976_film(self):
        self.check_film('ntsc_hard32', 24000 / 1001, 1e6 * 1001 / 24000)

    def test_pal_22_flagged_interlaced_is_rebuilt_as_25p_film(self):
        self.check_film('pal_22', 25, 40000)


if __name__ == '__main__':
    unittest.main()
