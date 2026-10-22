"""Execute native pending/submitted FEL facts and accepted diagnostic reporting."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class FELFactsTests(unittest.TestCase):
    def test_filter_facts_are_captured_not_recomputed_from_later_preferences(self):
        cpp=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        header=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h').read_text()
        capture=body(cpp,'void CDVBridgeGLES::CaptureMetadata(')
        submission=body(header,'struct Submission')
        getter=body(header,'Submission CaptureSubmission()')
        start=cpp.index('  const int felKey=submission.felBackend')
        accepted=cpp[start:cpp.index('#ifdef CB1_HAS_HDR10_AI',start)]
        prepare=body(cpp,'bool CDVBridgeGLES::Prepare(')
        native=body(prepare,'if (m_prepared)')
        ai=body(cpp,'CDVBridgeGLES::FrameStatus CDVBridgeGLES::PrepareHDR10AIFrame(')
        ai_reset=next(line for line in ai.splitlines() if 'm_pendingInfo = ' in line)
        program=r'''
#include <cassert>
#include <cstdint>
#include <memory>
#include <array>
#include <optional>
#include <string>
struct VideoSourceSideData;
using pl_tex=void*;
struct dvbridge_identity {uint64_t stream{},picture{},revision{};};
struct Binding {uint64_t stream{},picture{},revision{};bool operator==(const Binding&) const=default;};
struct AVDOVIDmData {int level;struct {int min_pq,avg_pq,max_pq;} l1;};
struct AVDOVIMetadata {int num_ext_blocks{};AVDOVIDmData blocks[2]{};};
const AVDOVIDmData* av_dovi_get_ext(const AVDOVIMetadata* m,int i) {return &m->blocks[i];}
const AVDOVIDmData* av_dovi_find_level(const AVDOVIMetadata*,int) {return nullptr;}
struct CDVMetadataBuffer {AVDOVIMetadata value{};const void* Data() const {return &value;}size_t Size() const {return sizeof(value);}};
struct dvbridge_color {struct {bool nlq_active{true};} dovi;};
bool dvbridge_map_color(dvbridge_color*,const void*,size_t,bool) {return true;}
struct CDVPlaybackInfo {enum : unsigned {HDMI=1,FEL=2,CM4=4,HDR10=8};};
constexpr int LOGINFO=0;
constexpr int DVBRIDGE_MODE_MASTER_REFERENCE=5;
constexpr int DVBRIDGE_MODE_HDR10PLUS=6,CB1_HDR10PLUS_VSIF_BYTES=31,CB1_HDR10PLUS_OK=0;
struct AVDynamicHDRPlus {};
int cb1_hdr10plus_vsif(uint8_t*,const AVDynamicHDRPlus*,bool,bool){assert(false);return 1;}
namespace DVBRIDGE {
struct StreamTelemetry {template<class... T> static void Metadata(T&&...) {}};
int reports{};bool admitted=true,applicable{};std::string request,executed,backend;
bool DiagnosticLog(int,const char*,bool applies,const char* asked,const char* ran,const char* used) {
 if(!admitted)return false;
 ++reports;applicable=applies;request=asked;executed=ran;backend=used;return true;
}
}
class CDVBridgeGLES {
public:
 struct Submission SUBMISSION;
 Submission m_submission{};
 int m_effectiveMode=1;
 struct {uint64_t informationGeneration{9};} m_pendingSourceInfo;
 struct {int felUpscaling{};} m_requested;
 CDVMetadataBuffer m_pendingMetadata;
 Binding m_hardwareBinding{1,2,3},m_pendingBinding{1,2,3};
 bool m_hardwareFELVpp{},m_hdr10{};unsigned m_pendingInfo{};
 bool m_prepared{},m_guiComposed{},m_overlayVisible{};
 std::optional<AVDynamicHDRPlus> m_hdr10plusMetadata;
 bool m_live{true},m_asyncEligible{};unsigned m_pendingHDR10Fallback{},m_outputBits{12};
 int m_hardwareFELFilter{},m_pendingFELFilter{-1},m_pendingFELBackend{},m_reportedFELKey{-1};
 uint64_t m_reportedFELStream{};
 void CaptureMetadata(const CDVMetadataBuffer& metadata,bool fel) CAPTURE
 Submission CaptureSubmission() const GETTER
 void Accepted(const Submission& submission) {ACCEPTED}
 void NativePrepared(const CDVMetadataBuffer& metadata,bool enhancement) {const bool hdr10plus=false;NATIVE}
 void AIState() {AI_RESET}
};
int main() {
 CDVBridgeGLES r;CDVMetadataBuffer metadata;r.m_submission.identity={7,4,3};
 r.m_hardwareFELVpp=true;r.CaptureMetadata(metadata,true);
 auto vpp=r.CaptureSubmission();assert(vpp.felFilter==0 && vpp.felBackend==2);
 r.Accepted(vpp);assert(DVBRIDGE::reports==1 && DVBRIDGE::backend=="vaapi-vpp" && DVBRIDGE::executed=="vaapi");
 r.Accepted(vpp);assert(DVBRIDGE::reports==1);
 r.m_requested.felUpscaling=1;r.m_hardwareFELVpp=false;r.CaptureMetadata(metadata,true);
 auto nearest=r.CaptureSubmission();assert(nearest.felFilter==1 && nearest.felBackend==1);
 assert(vpp.felFilter==0 && vpp.felBackend==2);
 DVBRIDGE::admitted=false;r.Accepted(nearest);assert(DVBRIDGE::reports==1);
 DVBRIDGE::admitted=true;r.Accepted(nearest);assert(DVBRIDGE::reports==2 && DVBRIDGE::executed=="nearest");
 r.m_hardwareFELVpp=true;r.m_hardwareBinding.picture++;r.CaptureMetadata(metadata,true);
 assert(r.CaptureSubmission().felBackend==1);
 r.CaptureMetadata(metadata,false);auto ordinary=r.CaptureSubmission();
 assert(ordinary.felFilter==-1 && ordinary.felBackend==0);
 r.Accepted(ordinary);assert(!DVBRIDGE::applicable && DVBRIDGE::executed=="not-applicable");
 nearest.identity.stream++;r.Accepted(nearest);assert(DVBRIDGE::reports==4);
 // Native Standard and Basic use Prepare(), not the advanced metadata helper.
 r.m_requested.felUpscaling=1;r.m_hardwareFELVpp=false;
 for(bool hdr : {false,true}) {
  r.m_hdr10=hdr;r.NativePrepared(metadata,true);
  auto native=r.CaptureSubmission();assert(native.felFilter==1 && native.felBackend==1);
 }
 r.AIState();auto ai=r.CaptureSubmission();assert(ai.felFilter==-1 && ai.felBackend==0);
 r.m_requested.felUpscaling=0;r.m_hardwareFELVpp=false;r.CaptureMetadata(metadata,true);
 auto fallback=r.CaptureSubmission();r.Accepted(fallback);
 assert(DVBRIDGE::request=="vaapi" && DVBRIDGE::executed=="nearest" && DVBRIDGE::backend=="shader");
 r.m_effectiveMode=DVBRIDGE_MODE_MASTER_REFERENCE;
 auto master=r.CaptureSubmission();assert(master.felBackend==3 && master.felFilter==0);
 r.Accepted(master);assert(DVBRIDGE::executed=="reference" && DVBRIDGE::backend=="reference-gpu");
 r.m_effectiveMode=1;assert(r.CaptureSubmission().felBackend==1);
}
'''.replace('SUBMISSION',submission).replace('CAPTURE',capture).replace('GETTER',getter).replace('ACCEPTED',accepted).replace('NATIVE',native).replace('AI_RESET',ai_reset)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror','-fsanitize=address,undefined',
                str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__':unittest.main()
