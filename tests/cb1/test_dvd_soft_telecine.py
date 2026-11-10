"""Soft-telecined film is presented as evenly spaced 23.976 frames.

The shipped FilmTiming code is compiled with a driver that decodes the corpus samples
with FFmpeg and passes the frame flags, timestamps and frame rates as Kodi does: the
container rate as CDVDDemuxFFmpeg chooses it and the rate coded in the video stream.
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
DVD_TIME_BASE = 1000000
CODED = DVD_TIME_BASE * 1001 / 30000  # NTSC frame
FILM = DVD_TIME_BASE * 1001 / 24000
CONTAINER_TOOLS = ('mkvpropedit', 'dvdauthor', 'xorriso')

DRIVER = r'''
#include "FilmTiming.h"
#include <cstdio>
#include <cstring>
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
}
using namespace FILM_TIMING;
constexpr double TIME_BASE = 1000000;

// VideoPlayerVideo::PresentFilmFrame for one decoded picture; prints "active pts".
struct Presenter
{
  CSoftTelecineDetector detector;
  CFilmRetimer retimer;
  double containerRate = 0, predicted = 0;
  void Present(bool interlaced, double repeat, double pts, double codedRate)
  {
    if (pts < 0)
      pts = predicted; // VideoPlayerVideo predicts the time of a picture without one
    detector.Add(interlaced, repeat);
    if (!detector.Active() || interlaced)
    {
      retimer.Reset();
      predicted = pts + TIME_BASE / containerRate * (1 + repeat);
      std::printf("0 0\n");
      return;
    }
    const double duration =
        PulldownFilmFrameDuration(CodedFrameDuration(TIME_BASE, codedRate, containerRate));
    const auto out = retimer.Retime(pts, duration);
    predicted = *out + duration;
    std::printf("1 %.3f\n", *out);
  }
};

int main(int argc, char** argv)
{
  Presenter presenter;
  if (argc < 2) // frames on stdin: interlaced repeat pts, from a 29.97 container
  {
    presenter.containerRate = 30000.0 / 1001;
    int interlaced;
    double repeat, pts;
    while (std::scanf("%d %lf %lf", &interlaced, &repeat, &pts) == 3)
      presenter.Present(interlaced, repeat, pts, 0);
    return 0;
  }
  AVFormatContext* format = nullptr;
  if (avformat_open_input(&format, argv[1], nullptr, nullptr) < 0 ||
      avformat_find_stream_info(format, nullptr) < 0)
    return 2;
  const AVCodec* codec = nullptr;
  const int index = av_find_best_stream(format, AVMEDIA_TYPE_VIDEO, -1, -1, &codec, 0);
  AVStream* stream = format->streams[index];
  // CDVDDemuxFFmpeg: av_guess_frame_rate, the average rate for Matroska
  AVRational rate = av_guess_frame_rate(format, stream, nullptr);
  if (std::strstr(format->iformat->name, "matroska") && stream->avg_frame_rate.num > 0)
    rate = stream->avg_frame_rate;
  presenter.containerRate = av_q2d(rate);
  std::printf("container %.3f\n", presenter.containerRate);
  AVCodecContext* context = avcodec_alloc_context3(codec);
  avcodec_parameters_to_context(context, stream->codecpar);
  context->pkt_timebase = stream->time_base;
  if (avcodec_open2(context, codec, nullptr) < 0)
    return 2;
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
      const double pts = frame->best_effort_timestamp == AV_NOPTS_VALUE ? -1 :
          frame->best_effort_timestamp * av_q2d(stream->time_base) * TIME_BASE;
      // CDVDVideoCodecFFmpeg::GetPictureCommon
      const double coded = context->framerate.num > 0 && context->framerate.den > 0
                               ? av_q2d(context->framerate) : 0;
      presenter.Present(frame->flags & AV_FRAME_FLAG_INTERLACED, 0.5 * frame->repeat_pict,
                        pts, coded);
    }
  }
  return 0;
}
'''


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('c++') and
                     Path(FFMPEG_INCLUDE, 'libavformat/avformat.h').is_file(),
                     'requires ffmpeg, c++ and FFmpeg development headers')
class SoftTelecineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        work = Path(cls.directory.name)
        sources = ['xbmc/cores/VideoPlayer/FilmTiming.h', 'xbmc/cores/VideoPlayer/FilmTiming.cpp']
        if not write_patched_files(sources, work):
            raise unittest.SkipTest('FilmTiming is not in the Kodi patch stack')
        work = work / 'xbmc/cores/VideoPlayer'
        (work / 'driver.cpp').write_text(DRIVER)
        cls.driver = work / 'driver'
        subprocess.run(['c++', '-std=c++20', '-O1', '-I', str(work), '-I', FFMPEG_INCLUDE,
                        str(work / 'driver.cpp'), str(work / 'FilmTiming.cpp'), '-lavformat',
                        '-lavcodec', '-lavutil', '-o', str(cls.driver)], check=True,
                       capture_output=True)
        cls.samples = Path(cls.directory.name) / 'samples'
        cls.containers = all(shutil.which(tool) for tool in CONTAINER_TOOLS)
        corpus.main([str(cls.samples), '--seconds', '4'] +
                    (['--containers'] if cls.containers else []))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    @staticmethod
    def parse(lines):
        return [(line.split()[0] == '1', float(line.split()[1])) for line in lines if line]

    def play(self, path):
        """(container rate, [(film presentation active, presentation time)])"""
        out = subprocess.run([str(self.driver), str(path)], capture_output=True, text=True,
                             check=True).stdout.splitlines()
        return float(out[0].split()[1]), self.parse(out[1:])

    def present(self, frames):
        """frames: (interlaced, repeat_pict, pts seconds or None), from a 29.97 container"""
        lines = ''.join(f'{int(i)} {0.5 * repeat} {-1 if pts is None else pts * DVD_TIME_BASE}\n'
                        for i, repeat, pts in frames)
        out = subprocess.run([str(self.driver)], input=lines, capture_output=True, text=True,
                             check=True).stdout
        return self.parse(out.splitlines())

    def assert_film_rate(self, shown, name, tolerance=1000):
        self.assertEqual(len(shown), 96, name)
        first = next(i for i, (active, _) in enumerate(shown) if active)
        self.assertLessEqual(first, 12, name)  # decided within half a second
        self.assertTrue(all(active for active, _ in shown[first:]), name)
        times = [pts for _, pts in shown[first:]]
        steps = [b - a for a, b in zip(times, times[1:])]
        self.assertTrue(all(abs(step - FILM) < tolerance for step in steps), (name, steps[:10]))

    def test_h264_soft_telecine_is_shown_at_the_film_rate(self):
        path = self.samples / 'ntsc_soft32_h264.mkv'
        if not path.is_file():
            self.skipTest('requires x264')
        rate, shown = self.play(path)
        self.assertAlmostEqual(rate, 23.976, places=3)
        # x264 orders the pic_struct pattern so that timestamps deviate from the even
        # film time by up to one field; the retimer follows 1/16 of the deviation.
        self.assert_film_rate(shown, 'h264', tolerance=1500)

    def test_soft_telecine_film_frames_are_evenly_spaced_at_the_film_rate(self):
        rate, shown = self.play(self.samples / 'ntsc_soft32.mpg')
        self.assertAlmostEqual(rate, 29.97, places=2)
        self.assert_film_rate(shown, 'mpg')

    def test_matroska_stating_the_film_rate_keeps_the_film_rate(self):
        if not self.containers:
            self.skipTest('requires ' + ', '.join(CONTAINER_TOOLS))
        rate, shown = self.play(self.samples / 'ntsc_soft32.mkv')
        self.assertAlmostEqual(rate, 23.976, places=3)
        self.assert_film_rate(shown, 'mkv')

    def test_the_title_of_an_iso_image_is_shown_at_the_film_rate(self):
        if not self.containers:
            self.skipTest('requires ' + ', '.join(CONTAINER_TOOLS))
        vob = corpus.disc_title(self.samples / 'ntsc_soft32.iso', self.samples)
        self.assert_film_rate(self.play(vob)[1], 'iso')

    def test_hard_telecine_video_and_pal_are_not_taken_for_soft_telecine(self):
        for name in ('ntsc_hard32', 'ntsc_video', 'pal_22', 'pal_22_progressive', 'pal_video'):
            shown = self.play(self.samples / f'{name}.mpg')[1]
            self.assertFalse(any(active for active, _ in shown), name)

    def test_an_interlaced_picture_ends_film_presentation_at_once(self):
        film = [(False, 1 - n % 2, n * CODED * 1.25 / DVD_TIME_BASE) for n in range(48)]
        video = [(True, 0, None)] * 4
        shown = self.present(film + video + film[:8])
        self.assertTrue(shown[47][0])
        self.assertFalse(any(active for active, _ in shown[48:52]))


if __name__ == '__main__':
    unittest.main()
