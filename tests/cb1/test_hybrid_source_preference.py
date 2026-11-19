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
        validity = capture[capture.index('  bool presentable ='):capture.index('  auto hybrid =')]
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
struct AVFrame { int64_t best_effort_timestamp{AV_NOPTS_VALUE}; int decode_error_flags{}, flags{};
                 void* opaque{}; };
#define HAVE_DVBRIDGE
char decodeOnlyDVPacket, presentableDVPacket;
static bool HybridProbePicture(const AVFrame* frame, int codecFlags) FRAME_PROBE
struct CLog { template <class... Args> static void Log(Args...) {} };
constexpr int LOGINFO = 1;
struct SideData { bool primary; bool HDR10PlusIsPrimary() const { return primary; } };
struct Picture { SideData* sourceSideData; };
struct Hints { bool preferHybridHDR10Plus; StreamHdrType hdrType; };

void Decide(Hints& m_hints, const AVFrame& decoded, int m_codecControlFlags,
            const Picture* pVideoPicture, bool m_dvVideoWindow=false)
{
  const auto* m_pFrame = &decoded;
  VALIDITY
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
  hints.dovi={7,6,true,true,true};
  assert(hints.HasHDR10PlusCompatibleDolbyVisionBase());
  hints.dovi.dv_bl_signal_compatibility_id=0;
  assert(!hints.HasHDR10PlusCompatibleDolbyVisionBase());
  hints.dovi={7,6,false,true,true};
  assert(!hints.HasHDR10PlusCompatibleDolbyVisionBase());
  hints.dovi={7,6,true,true,false};
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
  decoded.opaque=&decodeOnlyDVPacket;
  Decide(selected, decoded, 0, &noHDR10Plus);
  decoded.opaque=nullptr;
  Decide(selected, decoded, 0, &hybrid, true);
  assert(selected.preferHybridHDR10Plus && selected.hdrType == Type::HDR_TYPE_DOLBYVISION);
  decoded.opaque=&presentableDVPacket;
  Decide(selected, decoded, 0, &hybrid, true);
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
                                      .replace('VALIDITY', validity)
                                      .replace('DECISION', decision)
                                      .replace('PROBE', probe)})

    def test_fel_owner_retires_at_the_confirmed_picture_and_consumes_terminal_units(self):
        codec = TREE / 'xbmc/cores/VideoPlayer/DVDCodecs/Video'
        source = (codec / 'DVDVideoCodecFFmpeg.cpp').read_text()
        header = (codec / 'DVDVideoCodecFFmpeg.h').read_text()
        reopen = body(header, 'bool NeedsDVEnhancement() const')
        terminal = source[source.index('  const bool terminalEnhancement ='):
                          source.index('    return true; // A terminal enhancement')]
        picture = source.split('VCReturn result = GetBasePicture(base.get());', 1)[1].split(
            '      if (m_pCodecContext->hw_frames_ctx)', 1)[0]
        program = r'''
#include <cassert>
#include <memory>
#include <vector>
enum class StreamHdrType { HDR_TYPE_DOLBYVISION, HDR_TYPE_HDR10PLUS };
enum { VC_PICTURE=1, VC_BUFFER=2, VC_FATAL=3 };
constexpr int AV_NOPTS_VALUE = -1;
struct Timing { bool valid; int basePts, enhancementPts; };
bool consumeTail(bool m_dvFel, const Timing& layer) {
  TERMINAL
    return true;
  return false;
}
struct Picture {
  StreamHdrType hdrType;
  int pts;
  struct Proof { bool HDR10PlusIsPrimary() const { return true; } };
  static inline Proof data;
  const Proof* sourceSideData=&data;
  void CopyRef(const Picture& other) { *this=other; }
};
struct Codec {
  const bool m_dvNativeOutput{true};
  struct { struct { int dv_profile{7}; bool el_present_flag{true}; } dovi;
           StreamHdrType hdrType{StreamHdrType::HDR_TYPE_DOLBYVISION}; bool preferHybridHDR10Plus{true}; } m_hints;
  std::unique_ptr<int> m_dvFel=std::make_unique<int>(1);
  std::vector<int> m_dvPending{10};
  bool NeedsDVEnhancement() const REOPEN
  int next(int result, const Picture* base, Picture* pVideoPicture) {
    RELEASE
    return VC_BUFFER;
  }
};
int main() {
  using T=StreamHdrType;
  assert(consumeTail(false, {true,-1,99}));
  assert(!consumeTail(true, {true,-1,99})); // the native FEL owner still consumes this layer
  assert(!consumeTail(false,{true,-1,-1}) && !consumeTail(false,{false,-1,99}));
  assert(!consumeTail(false,{true,99,-1}));
  Codec c;
  Picture dv{T::HDR_TYPE_DOLBYVISION,15}, hdr{T::HDR_TYPE_HDR10PLUS,17}, shown{T::HDR_TYPE_DOLBYVISION,0};
  assert(c.NeedsDVEnhancement());
  assert(c.next(VC_PICTURE,&dv,&shown)==VC_BUFFER && c.m_dvFel && c.m_dvPending.size()==1);
  assert(c.next(VC_BUFFER,&hdr,&shown)==VC_BUFFER && c.m_dvFel);
  assert(c.next(VC_PICTURE,&hdr,&shown)==VC_PICTURE && shown.pts==17 && shown.hdrType==hdr.hdrType);
  assert(!c.m_dvFel && c.m_dvPending.empty());
  c.m_hints.hdrType=T::HDR_TYPE_HDR10PLUS;
  assert(!c.NeedsDVEnhancement());
}
'''
        run(self, {'test.cpp': program.replace('TERMINAL', terminal)
                                      .replace('REOPEN', reopen)
                                      .replace('RELEASE', picture)})

    def test_secondary_failure_waits_for_real_bl_verdict_and_survives_seek(self):
        source = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        actual = body(source, 'CDVDVideoCodec::VCReturn CDVDVideoCodecFFmpeg::GetPicture(')
        start = actual.index('      auto emit =')
        end = actual.index('      VCReturn paired = emit();', start)
        emit = actual[start:end]
        finish = emit[emit.index('          if (m_hints.preferHybridHDR10Plus)'):
                      emit.index('          ReportDVStartup(8,')]
        actual = actual[:start] + '      auto emit = [] { return VC_NONE; };\n' + actual[end:]
        program = r'''
#define HAVE_DVBRIDGE
#include <cassert>
#include <deque>
#include <memory>
#include <vector>
enum class StreamHdrType { HDR_TYPE_DOLBYVISION, HDR_TYPE_HDR10PLUS };
enum VCReturn {VC_PICTURE,VC_BUFFER,VC_NONE,VC_FATAL,VC_EOF};
enum { LOGERROR };
struct CLog { template<class... Args> static void Log(Args...) {} };
enum { DVD_CODEC_CTRL_POLL=1, DVD_CODEC_CTRL_DRAIN=2, DVEnhancementPendingPictures=16 };
constexpr int CODEC_BLURAY_NAVIGATION=4;
struct AVHWFramesContext { void* device_ref{}; };
struct HWBuffer { void* data{}; };
struct Context { HWBuffer* hw_frames_ctx{}; };
struct Fel { bool deviceOK=false, failed=false; };
bool dvbridge_fel_device(Fel* f, void*) { return f->deviceOK; }
bool dvbridge_fel_failed(Fel* f) { return f->failed; }
bool dvbridge_fel_has_enhancement(Fel*) { return true; }
bool dvbridge_fel_drain(Fel*,const char**) { return true; }
struct VideoPicture {
  StreamHdrType hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;
  int pts=0;
  struct Proof { bool HDR10PlusIsPrimary() const { return true; } };
  static inline Proof data;
  const Proof* sourceSideData=&data;
  void Reset() { pts=0; }
  void CopyRef(const VideoPicture& other) { *this=other; }
};
struct Input { VCReturn result; bool eligible=false, hdr=false; };
struct Manager {
  bool m_dvNativeOutput=true, m_dvFailed=false, required=true;
  Context ctx; Context* m_pCodecContext=&ctx;
  struct { bool preferHybridHDR10Plus=true; int codecOptions{}; } m_hints;
  bool hdr=false;
  bool NeedsDVEnhancement() const { return required && !hdr; }
  std::unique_ptr<Fel> m_dvFel=std::make_unique<Fel>();
  std::deque<std::shared_ptr<VideoPicture>> m_dvPending;
  uint64_t m_dvLayerEpoch{};
  int m_codecControlFlags=0, reads=0;
  std::vector<Input> sequence;
  VCReturn GetBasePicture(VideoPicture* pic) {
    assert(reads < int(sequence.size()));
    const auto& frame=sequence[reads++];
    if (frame.result==VC_PICTURE) {
      pic->pts=reads;
      if (m_hints.preferHybridHDR10Plus && frame.eligible) {
        m_hints.preferHybridHDR10Plus=false;
        hdr=frame.hdr;
      }
      pic->hdrType=hdr ? StreamHdrType::HDR_TYPE_HDR10PLUS : StreamHdrType::HDR_TYPE_DOLBYVISION;
    }
    return frame.result;
  }
  void ReportDVStartup(int,const char*) {}
  int finishPaired(VideoPicture* pVideoPicture) {
    while (!m_dvPending.empty()) {
      auto base=m_dvPending.front();
      FINISH
      return VC_PICTURE;
    }
    return VC_NONE;
  }
  VCReturn Picture(VideoPicture* pVideoPicture) ACTUAL
};
int main() {
  AVHWFramesContext pool; HWBuffer hw{&pool};
  for (bool fromOpen : {true,false}) for (bool chooseHDR : {true,false}) {
    Manager c;
    if (fromOpen) c.m_dvFel.reset();
    c.ctx.hw_frames_ctx=&hw;
    if (!fromOpen) c.sequence.push_back({VC_BUFFER}); // EL device fails while first BL is EAGAIN
    c.sequence.push_back({VC_BUFFER});
    c.sequence.push_back({VC_PICTURE,false,false}); // corrupt/preroll after the seek
    c.sequence.push_back({VC_PICTURE,true,chooseHDR});
    c.sequence.push_back({VC_EOF});
    VideoPicture out;
    assert(c.Picture(&out)==VC_BUFFER && !c.m_dvFel);
    c.m_dvFailed=false; // seek resets transient errors, cannot recreate a missing EL
    auto answer=c.Picture(&out);
    assert(answer==(chooseHDR?VC_PICTURE:VC_FATAL));
    assert(out.pts==c.reads && out.pts==(fromOpen?3:4));
    if (chooseHDR) assert(out.hdrType==StreamHdrType::HDR_TYPE_HDR10PLUS && c.Picture(&out)==VC_EOF);
  }
  Manager ordinary;
  ordinary.m_hints.preferHybridHDR10Plus=false;
  ordinary.m_dvFailed=true;
  VideoPicture out;
  assert(ordinary.Picture(&out)==VC_FATAL && ordinary.reads==0);
  Manager paired;
  paired.m_dvPending.push_back(std::make_shared<VideoPicture>());
  out.pts=81;
  assert(paired.finishPaired(&out)==VC_NONE && out.pts==81 && paired.m_dvPending.empty());
  paired.m_hints.preferHybridHDR10Plus=false;
  paired.m_dvPending.push_back(std::make_shared<VideoPicture>());
  assert(paired.finishPaired(&out)==VC_PICTURE && out.pts==0);
  for (bool hdr : {true,false}) {
    Manager direct; // P8 or non-native P7: a valid Dolby decision does not require an EL.
    direct.required=false;
    direct.m_dvFel.reset();
    direct.sequence={{VC_PICTURE,false,false},{VC_PICTURE,true,hdr},{VC_EOF}};
    assert(direct.Picture(&out)==VC_PICTURE && out.pts==2);
    assert(out.hdrType==(hdr?StreamHdrType::HDR_TYPE_HDR10PLUS:StreamHdrType::HDR_TYPE_DOLBYVISION));
    assert(direct.Picture(&out)==VC_EOF);
  }
  Manager blFails;
  blFails.sequence={{VC_FATAL}};
  assert(blFails.Picture(&out)==VC_FATAL && blFails.reads==1);
}
'''
        run(self, {'test.cpp': program.replace('ACTUAL', actual).replace('FINISH', finish)})
