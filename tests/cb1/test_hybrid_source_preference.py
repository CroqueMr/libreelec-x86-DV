"""Regression cases for the Dolby Vision / HDR10+ default input choice."""

import unittest
import xml.etree.ElementTree as ET

from test_native_video_source import TREE, body
from test_process_info_metadata import run


class HybridSourcePreference(unittest.TestCase):
    def test_source_preference_is_a_normal_two_choice_setting(self):
        settings = ET.parse(TREE / 'system/settings/settings.xml')
        setting = settings.find('.//setting[@id="dvbridge.hybridsource"]')
        self.assertIsNotNone(setting)
        self.assertEqual(setting.findtext('default'), '0')
        self.assertEqual(setting.find('control').get('type'), 'list')
        self.assertEqual([opt.text for opt in setting.findall('constraints/options/option')], ['0', '1'])

    def test_overlapping_formats_choose_the_hdr_base_only_for_valid_opt_in(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        hints = (TREE / 'xbmc/cores/VideoPlayer/DVDStreamInfo.cpp').read_text()
        probe = body(hints, 'bool CDVDStreamInfo::HasHDR10PlusCompatibleDolbyVisionBase() const')
        probe_frame = body(source, 'bool HybridProbePicture(')
        capture = body(source,'void CDVDVideoCodecFFmpeg::CaptureSourceSideData(')
        decision = capture[capture.index('  if (presentable)\n  {\n    m_hints.preferHybridHDR10Plus'):capture.rindex('}')]
        program = r'''
#include <cassert>
#include <cstdint>
#include <initializer_list>
enum AVCodecID { AV_CODEC_ID_HEVC, AV_CODEC_ID_AV1 };
enum AVColorTransferCharacteristic { AVCOL_TRC_SMPTE2084, AVCOL_TRC_ARIB_STD_B67 };
enum AVColorPrimaries { AVCOL_PRI_BT2020, AVCOL_PRI_BT709 };
enum class StreamHdrType { HDR_TYPE_HDR10, HDR_TYPE_DOLBYVISION, HDR_TYPE_HDR10PLUS };
struct Configuration { int dv_profile, dv_bl_signal_compatibility_id; bool bl_present_flag,
                      rpu_present_flag, el_present_flag; };
struct CDVDStreamInfo
{
  AVCodecID codec;
  Configuration dovi;
  bool HasHDR10PlusCompatibleDolbyVisionBase() const;
};
bool CDVDStreamInfo::HasHDR10PlusCompatibleDolbyVisionBase() const PROBE
enum { AV_FRAME_FLAG_CORRUPT = 1, AV_FRAME_FLAG_DISCARD = 2, DVD_CODEC_CTRL_DROP = 4 };
constexpr int64_t AV_NOPTS_VALUE = -1;
struct AVFrame { int64_t best_effort_timestamp{AV_NOPTS_VALUE}; int decode_error_flags{}, flags{}; };
static bool HybridProbePicture(const AVFrame* frame, int codecFlags) FRAME_PROBE
struct CLog { template <class... Args> static void Log(Args...) {} };
constexpr int LOGINFO = 1;
struct SideData { bool primary; bool HDR10PlusIsPrimary() const { return primary; } };
struct Picture { SideData* sourceSideData; };
struct Hints { bool preferHybridHDR10Plus; StreamHdrType hdrType; };

void Decide(Hints& m_hints, const AVFrame& decoded, int codecFlags, const Picture* pVideoPicture)
{
  const bool presentable = m_hints.preferHybridHDR10Plus && HybridProbePicture(&decoded, codecFlags);
  DECISION
}

int main()
{
  using Type = StreamHdrType;
  CDVDStreamInfo hints{AV_CODEC_ID_HEVC, {8, 1, true, true, false}};
  assert(hints.HasHDR10PlusCompatibleDolbyVisionBase());
  for (auto unsupported : {5, 7, 10})
  {
    hints.dovi.dv_profile=unsupported;
    assert(!hints.HasHDR10PlusCompatibleDolbyVisionBase());
  }
  hints.dovi.dv_profile=8;
  for (auto incompatible : {0, 2, 4})
  {
    hints.dovi.dv_bl_signal_compatibility_id=incompatible;
    assert(!hints.HasHDR10PlusCompatibleDolbyVisionBase());
  }
  hints.dovi.dv_bl_signal_compatibility_id=1;
  hints.dovi.rpu_present_flag=false;
  assert(!hints.HasHDR10PlusCompatibleDolbyVisionBase());
  hints.dovi.rpu_present_flag=true;
  hints.dovi.el_present_flag=true;
  assert(!hints.HasHDR10PlusCompatibleDolbyVisionBase());
  hints.dovi.el_present_flag=false;
  hints.codec=AV_CODEC_ID_AV1;
  assert(!hints.HasHDR10PlusCompatibleDolbyVisionBase());

  Hints selected{true, Type::HDR_TYPE_DOLBYVISION};
  AVFrame decoded;
  SideData yes{true};
  SideData no{false};
  Picture hybrid{&yes};
  Picture noHDR10Plus{&no};
  Decide(selected, decoded, 0, &noHDR10Plus);
  decoded.best_effort_timestamp=100;
  decoded.flags=AV_FRAME_FLAG_DISCARD;
  Decide(selected, decoded, 0, &noHDR10Plus);
  decoded.flags=0;
  Decide(selected, decoded, DVD_CODEC_CTRL_DROP, &noHDR10Plus);
  assert(selected.preferHybridHDR10Plus && selected.hdrType == Type::HDR_TYPE_DOLBYVISION);
  Decide(selected, decoded, 0, &hybrid);
  assert(!selected.preferHybridHDR10Plus && selected.hdrType == Type::HDR_TYPE_HDR10PLUS);
  Decide(selected, decoded, 0, &noHDR10Plus);
  assert(selected.hdrType == Type::HDR_TYPE_HDR10PLUS);

  Hints single{true, Type::HDR_TYPE_DOLBYVISION};
  Decide(single, decoded, 0, &noHDR10Plus);
  Decide(single, decoded, 0, &hybrid);
  assert(!single.preferHybridHDR10Plus && single.hdrType == Type::HDR_TYPE_DOLBYVISION);
  Hints unmodified{false, Type::HDR_TYPE_DOLBYVISION};
  Decide(unmodified, decoded, 0, &hybrid);
  assert(unmodified.hdrType == Type::HDR_TYPE_DOLBYVISION);
}
'''
        run(self, {'test.cpp': program.replace('FRAME_PROBE', probe_frame)
                                      .replace('DECISION', decision)
                                      .replace('PROBE', probe)})
