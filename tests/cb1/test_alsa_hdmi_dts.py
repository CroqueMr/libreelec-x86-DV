# SPDX-License-Identifier: MIT
"""Exercise ALSA enumeration and passthrough admission with HDMI ELD fixtures."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_native_video_source import TREE, body


class AlsaHdmiDts(unittest.TestCase):
    def test_passthrough_uses_complete_hdmi_eld_for_dts_only(self):
        engine = TREE / 'xbmc/cores/AudioEngine'
        alsa = (engine / 'Sinks/AESinkALSA.cpp').read_text()
        header = (engine / 'Sinks/AESinkALSA.h').read_text()
        sink = (engine / 'Engines/ActiveAE/ActiveAESink.cpp').read_text()
        program = r'''
#include "cores/AudioEngine/Utils/AEAudioFormat.h"
#include "cores/AudioEngine/Utils/AEDeviceInfo.h"
#include "cores/AudioEngine/Utils/AEELDParser.h"

#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <sstream>

const uint8_t* eldData;
int eldSize;
bool eldReadable;

// Replace hardware calls while running Kodi's enumeration and format checks.
using snd_pcm_t = int;
using snd_config_t = int;
using snd_pcm_info_t = int;
using snd_pcm_hw_params_t = int;
using snd_pcm_format_t = int;
using snd_ctl_t = int;
using snd_hctl_t = int;
using snd_ctl_elem_id_t = int;
using snd_ctl_elem_info_t = int;
using snd_ctl_elem_value_t = int;
using snd_hctl_elem_t = int;
using snd_pcm_chmap_t = int;
struct snd_pcm_chmap_query_t { snd_pcm_chmap_t map; };

#define ALSA_ALLOC(ptr) *(ptr) = static_cast<int*>(__builtin_alloca(sizeof(int)))
#define snd_pcm_info_alloca(ptr) ALSA_ALLOC(ptr)
#define snd_pcm_hw_params_alloca(ptr) ALSA_ALLOC(ptr)
#define snd_ctl_elem_id_alloca(ptr) ALSA_ALLOC(ptr)
#define snd_ctl_elem_info_alloca(ptr) ALSA_ALLOC(ptr)
#define snd_ctl_elem_value_alloca(ptr) ALSA_ALLOC(ptr)
constexpr int SND_PCM_FORMAT_UNKNOWN = -1, SND_CTL_ELEM_IFACE_PCM = 1;
constexpr int SND_CTL_ELEM_TYPE_BYTES = 1, LOGINFO = 0, LOGDEBUG = 0;
constexpr int ALSA_MAX_CHANNELS = 2;
const AEChannel LegacyALSAChannelMap[] = {AE_CH_FL, AE_CH_FR};
unsigned int ALSASampleRateList[] = {48000, 192000, 0};
size_t snd_pcm_info_sizeof() { return sizeof(int); }
size_t snd_pcm_hw_params_sizeof() { return sizeof(int); }
size_t snd_ctl_elem_id_sizeof() { return sizeof(int); }
size_t snd_ctl_elem_info_sizeof() { return sizeof(int); }
size_t snd_ctl_elem_value_sizeof() { return sizeof(int); }
int snd_pcm_info(snd_pcm_t*, snd_pcm_info_t*) { return 0; }
int snd_pcm_close(snd_pcm_t*) { return 0; }
int snd_pcm_info_get_card(snd_pcm_info_t*) { return 0; }
int snd_pcm_info_get_device(snd_pcm_info_t*) { return 3; }
const char* snd_pcm_info_get_name(snd_pcm_info_t*) { return "Test PCM"; }
int snd_card_get_name(int, char** name) { *name = strdup("Test Card"); return 0; }
int snd_ctl_open_lconf(snd_ctl_t** out, const char*, int, snd_config_t*) { *out = nullptr; return 0; }
int snd_hctl_open_ctl(snd_hctl_t** out, snd_ctl_t*) { *out = nullptr; return 0; }
int snd_hctl_load(snd_hctl_t*) { return 0; }
int snd_hctl_close(snd_hctl_t*) { return 0; }
int snd_ctl_close(snd_ctl_t*) { return 0; }
int snd_pcm_hw_params_any(snd_pcm_t*, snd_pcm_hw_params_t*) { return 0; }
int snd_pcm_hw_params_test_rate(snd_pcm_t*, snd_pcm_hw_params_t*, unsigned int, int) { return 0; }
int snd_pcm_hw_params_test_channels(snd_pcm_t*, snd_pcm_hw_params_t*, int) { return 0; }
int snd_pcm_hw_params_test_format(snd_pcm_t*, snd_pcm_hw_params_t*, snd_pcm_format_t) { return 0; }
snd_pcm_chmap_query_t** snd_pcm_query_chmaps(snd_pcm_t*) { return nullptr; }
void snd_pcm_free_chmaps(snd_pcm_chmap_query_t**) {}
void snd_ctl_elem_id_set_interface(snd_ctl_elem_id_t*, int) {}
void snd_ctl_elem_id_set_name(snd_ctl_elem_id_t*, const char*) {}
void snd_ctl_elem_id_set_device(snd_ctl_elem_id_t*, int device) { assert(device == 3); }
snd_hctl_elem_t* snd_hctl_find_elem(snd_hctl_t*, snd_ctl_elem_id_t*) {
  static snd_hctl_elem_t control;
  return eldReadable ? &control : nullptr;
}
int snd_hctl_elem_info(snd_hctl_elem_t*, snd_ctl_elem_info_t*) { return 0; }
int snd_ctl_elem_info_is_readable(snd_ctl_elem_info_t*) { return 1; }
int snd_ctl_elem_info_get_type(snd_ctl_elem_info_t*) { return SND_CTL_ELEM_TYPE_BYTES; }
int snd_hctl_elem_read(snd_hctl_elem_t*, snd_ctl_elem_value_t*) { return 0; }
int snd_ctl_elem_info_get_count(snd_ctl_elem_info_t*) { return eldSize; }
const void* snd_ctl_elem_value_get_bytes(const snd_ctl_elem_value_t*) { return eldData; }

struct CLog {
  template<class... Args> static void Log(int, const char*, Args&&...) {}
};
struct CAESinkALSA {
  static bool OpenPCMDevice(const std::string&, const std::string&, int, snd_pcm_t** out, snd_config_t*) {
    *out = nullptr;
    return true;
  }
  static snd_pcm_format_t AEFormatToALSAFormat(AEDataFormat fmt) {
    return fmt == AE_FMT_S16NE ? 0 : SND_PCM_FORMAT_UNKNOWN;
  }
  static CAEChannelInfo ALSAchmapToAEChannelMap(snd_pcm_chmap_t*) { return {}; }
  static AEDeviceType AEDeviceTypeFromName(const std::string& name) @DEVICE_TYPE@
  static void EnumerateDevice(AEDeviceInfoList&, const std::string&, const std::string&, snd_config_t*);
  @ELD_DECLARATION@
};
@ENUMERATE@

struct AESinkDevice { std::string driver, name; };
struct CAESinkFactory {
  static AESinkDevice ParseDevice(const std::string& device) { return {"ALSA", device}; }
};
struct Sink { std::string m_sinkName; AEDeviceInfoList m_deviceInfoList; };
struct CActiveAESink {
  std::vector<Sink> m_sinkInfoList;
  bool SupportsFormat(const std::string& device, AEAudioFormat& format) @SUPPORTS_FORMAT@
};

using enum CAEStreamInfo::DataType;

void Check(const uint8_t* data, int size, bool core, bool hd,
           const std::string& device = "hdmi:CARD=PCH,DEV=0", bool hasControl = true)
{
  eldData = data;
  eldSize = size;
  eldReadable = hasControl;
  CActiveAESink sink{{{"ALSA", {}}}};
  auto& devices = sink.m_sinkInfoList.front().m_deviceInfoList;
  CAESinkALSA::EnumerateDevice(devices, device, device, nullptr);
  assert(devices.size() == 1);

  AEAudioFormat format;
  format.m_sampleRate = format.m_streamInfo.m_sampleRate = 48000;
  format.m_dataFormat = AE_FMT_S16NE;
  assert(sink.SupportsFormat(device, format));
  format.m_dataFormat = AE_FMT_RAW;
  for (auto type : {STREAM_TYPE_DTS_512, STREAM_TYPE_DTS_1024, STREAM_TYPE_DTS_2048,
                    STREAM_TYPE_DTSHD_CORE, STREAM_TYPE_DTSHD, STREAM_TYPE_DTSHD_MA})
  {
    format.m_streamInfo.m_type = type;
    const bool isHd = type == STREAM_TYPE_DTSHD || type == STREAM_TYPE_DTSHD_MA;
    assert(sink.SupportsFormat(device, format) == (isHd ? hd : core));
  }
  for (auto type : {STREAM_TYPE_AC3, STREAM_TYPE_EAC3, STREAM_TYPE_TRUEHD})
  {
    format.m_streamInfo.m_type = type;
    assert(sink.SupportsFormat(device, format) ==
           (device.starts_with("hdmi") || (device.starts_with("iec958") && type == STREAM_TYPE_AC3)));
  }
}

int main()
{
  // Baseline ELD reconstructed from the S95C's captured CTA SAD bytes (issue #191).
  alignas(8) uint8_t eld[44] = {
      0x10, 0, 10, 0, 0x66, 0x50, 0, 0x0f, 0, 0, 0, 0, 0, 0, 0, 0,
      0x4c, 0x2d, 0x46, 0x73, 'Q', 'C', 'Q', '9', '5', 'S',
      0x0d, 0x57, 0x07, 0x09, 0x07, 0x07, 0x15, 0x07, 0x50,
      0x57, 0x07, 0x01, 0x67, 0x54, 0x07};
  Check(eld, sizeof(eld), false, false);
  eld[4] = 0x86; // reserved CTA revision with a plausible SAD list
  Check(eld, sizeof(eld), true, true);
  eld[4] = 0x66;
  Check(eld, sizeof(eld), true, false, "iec958:CARD=PCH,DEV=0");
  Check(eld, sizeof(eld), false, false, "@");
  Check(nullptr, 0, true, true);
  Check(nullptr, 0, true, true, "hdmi:CARD=PCH,DEV=0", false);
  const uint8_t shortHeader[] = {0x10};
  Check(shortHeader, sizeof(shortHeader), true, true);
  const std::vector<uint8_t> shortSad(eld, eld + 40);
  Check(shortSad.data(), shortSad.size(), true, true);
  Check(eld, 41, true, true); // incomplete declared baseline
  eld[0] = 0xf8; // Partial or canned ELD
  Check(eld, sizeof(eld), true, true);
  eld[0] = 0x10;
  eld[5] = 0x54; // DisplayPort ELD
  Check(eld, sizeof(eld), true, true);
  eld[5] = 0; // no SAD evidence yet
  Check(eld, sizeof(eld), true, true);
  eld[5] = 0x50;
  eld[26] = 0; // reserved coding type
  Check(eld, sizeof(eld), true, true);
  eld[26] = 0x3d; // DTS core SAD
  Check(eld, sizeof(eld), true, false);
  eld[32] = 0x5f; // DTS-HD SAD
  Check(eld, sizeof(eld), true, true);
  eld[26] = 0x0d;
  Check(eld, sizeof(eld), false, true);
}
'''
        enumerate_start = alsa.index('void CAESinkALSA::EnumerateDevice(')
        enumerate_end = alsa.index('void CAESinkALSA::sndLibErrorHandler(', enumerate_start)
        get_eld_start = header.index('static bool GetELD(')
        get_eld_end = header.index(';', get_eld_start) + 1
        for marker, text in {
            '@DEVICE_TYPE@': body(alsa, 'AEDeviceType CAESinkALSA::AEDeviceTypeFromName('),
            '@ELD_DECLARATION@': header[get_eld_start:get_eld_end],
            '@ENUMERATE@': alsa[enumerate_start:enumerate_end],
            '@SUPPORTS_FORMAT@': body(sink, 'bool CActiveAESink::SupportsFormat('),
        }.items():
            program = program.replace(marker, text)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'check.cpp'
            source.write_text(program)
            includes = ['-I' + str(TREE / 'xbmc')]
            if prefix := os.environ.get('FFMPEG_TEST_PREFIX'):
                includes += ['-I' + str(Path(prefix) / 'include')]
            build = subprocess.run(
                ['c++', '-std=c++20', '-DHAVE_X11', '-DTARGET_POSIX',
                 '-fsanitize=address,undefined', '-fno-sanitize-recover=all', *includes,
                 str(source), str(engine / 'Utils/AEELDParser.cpp'),
                 str(engine / 'Utils/AEChannelInfo.cpp'), '-o', str(root / 'check')],
                capture_output=True, text=True,
            )
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
