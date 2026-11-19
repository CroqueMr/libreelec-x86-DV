/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "cores/VideoPlayer/DVDDemuxers/BlurayDovi.h"

#include <cassert>
#include <string_view>

extern "C"
{
#include <libavformat/avformat.h>
AVPacket* __real_av_packet_clone(const AVPacket*);
}

static bool failClone{};
extern "C" AVPacket* __wrap_av_packet_clone(const AVPacket* packet)
{
  return failClone ? nullptr : __real_av_packet_clone(packet);
}

enum { LOGINFO, LOGWARNING, LOGERROR };
struct CLog
{
  template<class... T> static void Log(int, const char*, T...) {}
};

struct Reader
{
  CBlurayDovi layers;
  CBlurayDovi* m_blurayDovi{&layers};
  AVStream base{};
  AVStream* streams[1]{&base};
  AVFormatContext format{};
  AVFormatContext* m_pFormatContext{&format};
  const int m_blurayBase{0}, m_blurayEnhancement{1};
  bool m_blurayAwaitBase{};
  int inputResult{AVERROR_EOF};
  struct
  {
    int64_t basePts, enhancementPts;
    uint64_t epoch;
    int num, den;
    bool valid, presentable;
  } m_blurayTiming{};

  Reader() { format.streams = streams; base.time_base = {1, 24}; }
  int av_read_frame(AVFormatContext*, AVPacket*) { return inputResult; }
  int Read(AVPacket* packet)
#include "read-bluray-dovi.inc"

  void Push(int pts, bool enhancement, bool rpu = false)
  {
    const uint8_t data[] = {0, 0, 1, 0x02, 1, uint8_t(pts), 0, 0, 1, 0x7c, 1, uint8_t(pts)};
    AVPacket* packet = av_packet_alloc();
    assert(packet && av_new_packet(packet, rpu ? sizeof(data) : 6) == 0);
    memcpy(packet->data, data, packet->size);
    packet->pts = packet->dts = pts;
    assert(layers.Push(packet, enhancement));
    av_packet_free(&packet);
  }
};

int main(int argc, char** argv)
{
  assert(argc == 2);
  Reader r;
  AVPacket* packet = av_packet_alloc();
  assert(packet);
  if (std::string_view(argv[1]) == "gap")
  {
    for (int pts = 0; pts <= 2; ++pts)
      r.Push(pts, false);
    // All EL video units exist, but there is no RPU for the middle BL.
    for (int pts = 0; pts <= 2; ++pts)
      r.Push(pts, true, pts != 1);
    for (int pts = 0; pts <= 2; ++pts)
    {
      if (pts == 1)
      {
        r.inputResult = AVERROR(EAGAIN);
        assert(r.Read(packet) == AVERROR(EAGAIN)); // Further input can still supply this RPU.
        r.inputResult = AVERROR_EOF;
      }
      assert(r.Read(packet) == 0 && "An unpresentable BL must not truncate the tail");
      assert(r.m_blurayTiming.basePts == pts && r.m_blurayTiming.enhancementPts == pts);
      assert(r.m_blurayTiming.presentable == (pts != 1));
      assert(packet->data[5] == pts && packet->data[packet->size-1] == pts);
      av_packet_unref(packet);
    }
    assert(r.Read(packet) == AVERROR_EOF && !r.layers.Pending());
  }
  else
  {
    // The last BL has its own RPU. Without a queued EL a normal take waits.
    r.Push(2, false, true);
    failClone = true;
    assert(r.Read(packet) == AVERROR(ENOMEM) && "Terminal allocation failure is a demux error");
    failClone = false;
    assert(r.Read(packet) == 0 && r.m_blurayTiming.basePts == 2 && r.m_blurayTiming.presentable);
    av_packet_unref(packet);
    assert(r.Read(packet) == AVERROR_EOF);
  }
  av_packet_free(&packet);
}
