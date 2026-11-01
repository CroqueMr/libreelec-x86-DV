// SPDX-License-Identifier: GPL-2.0-or-later
#include "cores/AudioEngine/Utils/AEAudioSourceInfo.h"
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavutil/channel_layout.h>
#include <libavutil/crc.h>
}
#include <array>
#include <cassert>
#include <cstring>
#include <fstream>
#include <iterator>
#include <random>
#include <string>
#include <vector>
using namespace AE;
using Bytes = std::vector<uint8_t>;

static void Bits(Bytes& data, unsigned& position, unsigned count, unsigned value)
{
  assert(position + count <= data.size() * 8);
  for (unsigned n = count; n; --n, ++position)
    data[position / 8] = (data[position / 8] & ~(1u << (7 - position % 8))) |
                        (((value >> (n - 1)) & 1u) << (7 - position % 8));
}

static void CRC(Bytes& data, unsigned start, unsigned count, unsigned at)
{
  const AVCRC* table = av_crc_get_table(AV_CRC_16_ANSI);
  for (unsigned v = 0; v < 65536; ++v)
  {
    data[at] = v >> 8;
    data[at + 1] = v;
    if (av_crc(table, 0, data.data() + start, count) == 0)
      return;
  }
  assert(false);
}

static Bytes AC3(bool enhanced, unsigned dialogue = 27, bool dualMono = false)
{
  Bytes data(128);
  unsigned p = 0;
  Bits(data, p, 16, 0x0b77);
  if (enhanced)
  {
    Bits(data, p, 2, 0); // independent substream
    Bits(data, p, 3, 0);
    Bits(data, p, 11, 63); // 128-byte frame
    Bits(data, p, 2, 0); // 48 kHz
    Bits(data, p, 2, 3); // six blocks
    Bits(data, p, 3, dualMono ? 0 : 7);
    Bits(data, p, 1, 0);
    Bits(data, p, 5, 16);
  }
  else
  {
    Bits(data, p, 16, 0); // CRC1
    Bits(data, p, 2, 0); // 48 kHz
    Bits(data, p, 6, 0); // 32 kb/s, 128-byte frame
    Bits(data, p, 5, 8);
    Bits(data, p, 3, 0);
    Bits(data, p, 3, dualMono ? 0 : 2);
    if (!dualMono)
      Bits(data, p, 2, 0); // stereo surround mode
    Bits(data, p, 1, 0);
  }
  Bits(data, p, 5, dialogue);
  Bits(data, p, 1, 0); // no compression word
  if (!enhanced)
  {
    Bits(data, p, 1, 0); // no language code
    Bits(data, p, 1, 0); // no production info
  }
  if (dualMono)
  {
    Bits(data, p, 5, 31);
    Bits(data, p, 1, 0);
    if (!enhanced)
    {
      Bits(data, p, 1, 0);
      Bits(data, p, 1, 0);
    }
  }
  if (!enhanced)
    CRC(data, 2, 78, 2); // first 5/8 of the frame
  CRC(data, 2, data.size() - 2, data.size() - 2);
  return data;
}

static void SealTrueHD(Bytes& data)
{
  std::array<AVCRC, 1024> table{};
  av_crc_init(table.data(), 0, 16, 0x2d, sizeof(table));
  const unsigned major = 28 + ((data[29] & 1) ? 2 + 2 * (data[30] >> 4) : 0);
  unsigned crc = av_crc(table.data(), 0, data.data() + 4, major - 4);
  // Same little-endian checksum word as native AEStreamInfo::SyncTrueHD.
  crc ^= (data[major + 1] << 8) | data[major];
  data[major + 2] = crc;
  data[major + 3] = crc >> 8;
}

static Bytes EAC3Atmos(bool invalidVersion = false)
{
  auto packet = AC3(true);
  unsigned p = 128;
  Bits(packet, p, 16, 0x5838);
  Bits(packet, p, 16, 16); // 16-byte EMDF container
  Bits(packet, p, 2, 0);
  Bits(packet, p, 3, 0);
  Bits(packet, p, 5, 11); // object audio metadata payload
  Bits(packet, p, 4, 0); // no sample offset, duration, group or codec id
  Bits(packet, p, 1, 1); // discard unknown payloads
  Bits(packet, p, 8, 4); Bits(packet, p, 1, 0); // four payload bytes
  const unsigned end = p + 32;
  Bits(packet, p, 2, invalidVersion ? 1 : 0);
  Bits(packet, p, 5, 15); // 16 presentation elements
  Bits(packet, p, 1, 0); // not object-only
  Bits(packet, p, 4, 5); // bed + declared dynamic objects
  Bits(packet, p, 1, 0); Bits(packet, p, 1, 0);
  Bits(packet, p, 1, 0); Bits(packet, p, 1, 1);
  Bits(packet, p, 10, 15); // six bed channels
  Bits(packet, p, 5, 9); // ten dynamic objects
  p = end;
  Bits(packet, p, 5, 0); // payload list terminator
  CRC(packet, 2, packet.size() - 2, packet.size() - 2);
  return packet;
}

static Bytes TrueHD(bool atmos = true, bool objectOnly = false, bool invalidCount = false)
{
  Bytes data(64);
  data[1] = 32; // 64-byte audio unit
  data[4] = 0xf8; data[5] = 0x72; data[6] = 0x6f; data[7] = 0xba;
  data[11] = 0x1b;
  data[20] = 0x30;
  if (atmos)
  {
    data[21] = 0x80;
    data[29] = 1;
    unsigned p = 240;
    Bits(data, p, 4, 2); // expansion length: three 16-bit words
    Bits(data, p, 5, 27); // source dialogue level -27 LKFS, not gain -4 dB
    Bits(data, p, 6, 0);
    Bits(data, p, 5, invalidCount ? 31 : 15); // 16 elements, never 32
    Bits(data, p, 1, objectOnly ? 1 : 0);
    if (objectOnly)
      Bits(data, p, 1, 1); // LFE-only bed; 15 dynamic objects
    else
    {
      Bits(data, p, 4, 5); // bed and declared dynamic objects
      Bits(data, p, 1, 0);
      Bits(data, p, 1, 0); // one bed
      Bits(data, p, 1, 0); // not LFE-only
      Bits(data, p, 1, 1); // standard bed mask
      Bits(data, p, 10, 15); // weights 2 + 1 + 1 + 2 = 6
      Bits(data, p, 5, 9); // 10 declared dynamic objects
    }
  }
  SealTrueHD(data);
  return data;
}

static AudioSourceInfo Seed(int codec = AV_CODEC_ID_TRUEHD)
{
  AudioSourceInfo result;
  result.valid = true; result.uniqueId = 4; result.demuxerId = 81;
  result.codec = codec; result.channels = 8; result.sampleRate = 48000;
  result.channelMask = AV_CH_LAYOUT_7POINT1;
  return result;
}

int main(int argc, char** argv)
{
  assert(argc == 2 || argc == 5);
  const std::string test = argv[1];
  AudioSourceObserver observer;
  auto source = Seed();
  observer.Reset(source);
  if (test == "generated")
  {
    const int codecs[] = {AV_CODEC_ID_AC3, AV_CODEC_ID_EAC3, AV_CODEC_ID_TRUEHD};
    for (unsigned n = 0; n < 3; ++n)
    {
      std::ifstream file(argv[n + 2], std::ios::binary);
      Bytes data{std::istreambuf_iterator<char>(file), {}};
      assert(!data.empty());
      auto copy = data;
      observer.Reset(Seed(codecs[n]));
      const bool changed = observer.Observe(data);
      const auto& result = observer.Get();
      if (codecs[n] == AV_CODEC_ID_TRUEHD)
        assert(result.profile == AV_PROFILE_UNKNOWN && !result.dialnorm);
      else
        assert(changed && result.dialnorm == -27 && result.objects == -1);
      assert(data == copy);
    }
  }
  else if (test == "labels")
  {
    source.bitsPerSample = 24;
    source.profile = AV_PROFILE_TRUEHD_ATMOS;
    assert(SourceTitle(source) == "TrueHD Atmos");
    assert(SourceFormat(source) == "24-bit / 48 kHz");
    assert(SourceChannels(source) == "7.1");
    source.channelMask = 0;
    assert(SourceChannels(source) == "8 channels");
    source.codec = AV_CODEC_ID_EAC3; source.profile = AV_PROFILE_EAC3_DDP_ATMOS;
    assert(SourceTitle(source) == "Dolby Digital Plus Atmos");
    assert(SourceFormat(source) == "48 kHz"); // no invented lossy PCM precision
    source.codec = AV_CODEC_ID_DTS; source.profile = AV_PROFILE_DTS_HD_MA_X;
    assert(SourceTitle(source) == "DTS-HD MA DTS:X");
    assert(BedObjects(source).empty()); // no inferred height/objects
    source.bedChannels = 0; source.objects = 16;
    assert(BedObjects(source) == "0 / 16");
    assert(BedObjectsLabel(source) == "Bed / objects");
    source.dialnorm = -31;
    assert(Dialnorm(source) == "-31 LKFS");
    source.valid = false;
    assert(SourceTitle(source).empty() && SourceFormat(source).empty());
  }
  else if (test == "ac3")
  {
    for (bool enhanced : {false, true})
      for (bool dual : {false, true})
        for (unsigned dn : {0, 1, 27, 31})
        {
          observer.Reset(Seed(enhanced ? AV_CODEC_ID_EAC3 : AV_CODEC_ID_AC3));
          auto packet = AC3(enhanced, dn, dual); const auto before = packet;
          assert(observer.Observe(packet));
          assert(packet == before);
          const auto& info = observer.Get();
          assert(info.dialnorm == (dn ? -int(dn) : -31));
          assert(info.secondDialnorm == (dual ? std::optional<int>{-31} : std::nullopt));
          assert(info.objects == -1 && info.presentation == -1);
          assert(info.profile != AV_PROFILE_EAC3_DDP_ATMOS);
        }
  }
  else if (test == "eac3")
  {
    observer.Reset(Seed(AV_CODEC_ID_EAC3));
    auto packet = EAC3Atmos(); const auto before = packet;
    assert(observer.Observe(packet) && packet == before);
    assert(observer.Get().profile == AV_PROFILE_EAC3_DDP_ATMOS);
    assert(observer.Get().presentation == 16 && observer.Get().bedChannels == 6);
    assert(observer.Get().objects == 10 && observer.Get().dialnorm == -27);
    observer.Reset(Seed(AV_CODEC_ID_EAC3)); observer.Observe(EAC3Atmos(true));
    assert(observer.Get().profile == AV_PROFILE_UNKNOWN && observer.Get().objects == -1);
    assert(observer.Get().dialnorm == -27);
  }
  else if (test == "truehd")
  {
    auto header = TrueHD();
    observer.Observe(header);
    assert(!observer.UpdateProfile(0));
    assert(SourceTitle(observer.Get()) == "TrueHD Atmos");
    observer.Reset(source);
    auto packet = TrueHD(); const auto before = packet;
    assert(observer.Observe(packet) && packet == before);
    const auto& info = observer.Get();
    assert(info.profile == AV_PROFILE_TRUEHD_ATMOS && info.dialnorm == -27);
    assert(info.bedChannels == 6 && info.objects == 10 && info.presentation == 16);
    assert(BedObjects(info) == "6 / 10");
    assert(!observer.Observe(packet));
    observer.Reset(source); assert(observer.Observe(TrueHD(true, true)));
    assert(observer.Get().bedChannels == 1 && observer.Get().objects == 15);
    observer.Reset(source); observer.Observe(TrueHD(false));
    assert(observer.Get().objects == -1 && !observer.Get().dialnorm);
    observer.Reset(source); observer.Observe(TrueHD(true, false, true));
    assert(observer.Get().presentation == -1 && observer.Get().objects == -1);
  }
  else if (test == "malformed")
  {
    for (auto packet : {TrueHD(), AC3(false), AC3(true)})
    {
      const int codec = packet[0] == 0x0b ? (packet[5] >> 3 == 16 ? AV_CODEC_ID_EAC3 : AV_CODEC_ID_AC3) : AV_CODEC_ID_TRUEHD;
      for (size_t size = 0; size < packet.size(); ++size)
      {
        observer.Reset(Seed(codec)); observer.Observe(std::span<const uint8_t>(packet).first(size));
        assert(observer.Get().objects == -1 && !observer.Get().dialnorm);
      }
      packet[10] ^= 1; observer.Reset(Seed(codec)); observer.Observe(packet);
      assert(!observer.Get().dialnorm && observer.Get().objects == -1);
    }
  }
  else if (test == "bounded")
  {
    for (int n = 0; n < 600; ++n) observer.Observe(Bytes(1));
    assert(!observer.Observe(TrueHD()) && observer.Get().objects == -1);
    source.uniqueId = 5; observer.Reset(source);
    assert(observer.Get().objects == -1 && observer.Get().uniqueId == 5);
    assert(observer.Observe(TrueHD()) && observer.Get().objects == 10);
    observer.Reset({}); assert(!observer.Observe(TrueHD()) && !observer.Get().valid);
  }
  else if (test == "fuzz")
  {
    std::mt19937 random(913);
    for (unsigned size = 0; size < 600; ++size)
    {
      Bytes packet(size); for (auto& value : packet) value = random();
      const auto before = packet;
      for (int codec : {AV_CODEC_ID_TRUEHD, AV_CODEC_ID_AC3, AV_CODEC_ID_EAC3})
      { observer.Reset(Seed(codec)); observer.Observe(packet); assert(packet == before); }
    }
  }
  else assert(false);
}
