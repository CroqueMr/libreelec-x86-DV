"""A retained HDR10 renderer commits its rendered buffer with its own HDR metadata."""
import unittest

from test_ai_reentry import execute
from test_native_video_source import TREE, body


class NativeHDR10FrameHandoff(unittest.TestCase):
    def test_handoff_reuses_the_last_scanout_until_the_new_frame_is_ready(self):
        gles = (TREE / "xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp").read_text()
        render = body(gles, "void CWinSystemGbmGLESContext::PresentFrame(")
        self.assertLess(render.index("m_hdr10HandoffPicture"), render.rindex("TrySwapBuffers"))
        self.assertLess(render.index("PresentHDR10Handoff("),
                        render.index("CWinSystemGbm::FlipPage(rendered, videoLayer, async)"))

    def test_hdr_blob_is_promoted_only_on_paired_commit(self):
        gbm = (TREE / "xbmc/windowing/gbm/WinSystemGbm.cpp").read_text()
        handoff = body(gbm, "bool CWinSystemGbm::PresentHDR10Handoff(")
        self.assertLess(handoff.index("FlipPageWithHDR10Metadata"),
                        handoff.index("m_hdrBlob = std::move(candidate)"))
        self.assertIn("CompleteTransactionalBuffer(accepted)", handoff)
        drm = (TREE / "xbmc/windowing/gbm/drm/DRMAtomic.cpp").read_text()
        commit = body(drm, "bool CDRMAtomic::FlipPageWithHDR10Metadata(")
        self.assertLess(commit.index("HDR_OUTPUT_METADATA"), commit.index("DrmAtomicCommit("))
        self.assertIn("m_colorRangeTransition = true", commit)
        self.assertIn("DrmAtomicCommit(fb->fb_id, 0", commit)
        atomic = body(drm, "bool CDRMAtomic::DrmAtomicCommit(")
        self.assertIn("(strict || m_req->sdrRestore || m_colorRangeTransition)", atomic)

    def test_repeated_rejection_leaves_teardown_to_the_player(self):
        gles = (TREE / "xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp").read_text()
        render = body(gles, "void CWinSystemGbmGLESContext::PresentFrame(")
        failed = render.split("else if (++m_hdr10HandoffFailures", 1)[1].split("}", 1)[0]
        self.assertIn("PostMsg(TMSG_MEDIA_STOP)", failed)
        self.assertNotIn("SetHDR(", failed)
        self.assertNotIn("m_hdr10HandoffPending = false", failed)

    def test_drm_refusal_keeps_the_previous_frame_and_blob(self):
        drm = (TREE / "xbmc/windowing/gbm/drm/DRMAtomic.cpp").read_text()
        commit = body(drm, "bool CDRMAtomic::FlipPageWithHDR10Metadata(")
        execute(r'''
#include <cassert>
#include <cstdint>
#include <string_view>
struct gbm_bo { int fb; };
struct drm_fb { int fb_id; };
struct DRM {
  int* m_connector{};
  bool m_colorRangeTransition{}, m_lastPageAccepted{};
  bool importOK{true}, propertyOK{true}, commitOK{true};
  int committedFB{10}, pendingFB{};
  uint32_t committedBlob{100}, pendingBlob{};
  drm_fb imported{};
  drm_fb* DrmFbGetFromBo(gbm_bo* bo) {
    imported.fb_id = bo->fb;
    return importOK ? &imported : nullptr;
  }
  bool AddProperty(int*, std::string_view name, uint32_t blob) {
    assert(name == "HDR_OUTPUT_METADATA");
    pendingBlob = blob;
    return propertyOK;
  }
  void FinishRequest(bool) { pendingBlob = 0; m_colorRangeTransition = false; }
  bool DrmAtomicCommit(int fb, int flags, bool rendered, bool videoLayer) {
    assert(m_colorRangeTransition && flags == 0 && rendered && !videoLayer);
    assert(pendingBlob != 0);
    if (commitOK) { committedFB = fb; committedBlob = pendingBlob; }
    FinishRequest(commitOK);
    return commitOK;
  }
  bool Flip(gbm_bo* bo, uint32_t blob) COMMIT
};
int main() {
  DRM drm;
  gbm_bo next{20};
  drm.importOK = false;
  assert(!drm.Flip(&next, 200) && drm.committedFB == 10 && drm.committedBlob == 100);
  drm.importOK = true;
  drm.propertyOK = false;
  assert(!drm.Flip(&next, 200) && drm.pendingBlob == 0 && drm.committedBlob == 100);
  drm.propertyOK = true;
  drm.commitOK = false;
  assert(!drm.Flip(&next, 200) && drm.committedFB == 10 && drm.committedBlob == 100);
  drm.commitOK = true;
  assert(drm.Flip(&next, 200) && drm.committedFB == 20 && drm.committedBlob == 200);
}
'''.replace("COMMIT", commit))

    def test_retention_checks_the_actual_static_pq_output(self):
        source = (TREE / 'xbmc/windowing/gbm/WinSystemGbm.cpp').read_text()
        keep = body(source, 'bool CWinSystemGbm::CanKeepHDR10Signal')
        execute(r'''
#include <cassert>
#include <memory>
#include <string_view>
enum class StreamHdrType { HDR_TYPE_HDR10, HDR_TYPE_HDR10PLUS, HDR_TYPE_HLG };
constexpr int AVCOL_TRC_SMPTE2084=16, QUIRK_NEEDSPRIMARY=1, SETTING_WINSYSTEM_IS_HDR_DISPLAY=2;
struct VideoPicture { StreamHdrType hdrType; int color_transfer=16; };
namespace KODI::UTILS {
enum class Eotf { PQ };
int GetColorimetry(const VideoPicture&) { return 9; }
}
struct Display { int version=-1; int HDR10PlusVersion() const { return version; } };
struct Props {
 bool supported=true;
 bool SupportsProperty(std::string_view key) { assert(key=="HDR10PLUS_METADATA"); return supported; }
 int GetPropertyValue(std::string_view key) const {
   if (key=="ACTIVE") return 1;
   if (key=="Colorspace") return 9;
   return 42;
 }
};
struct DRM { virtual ~DRM()=default; };
struct CDRMAtomic : DRM {
 Props connector,crtc;
 bool activePlus=false;
 bool HasQuirk(int) const { return true; }
 bool IsActive() const { return true; }
 bool IsSelectedModeCommitted() const { return true; }
 bool LastCommitFellBack() const { return false; }
 bool IsSDRRestorePending() const { return false; }
 bool HasPendingRequest() const { return false; }
 bool HasPendingCB1Page() const { return false; }
 bool HasColorRangeTransition() const { return false; }
 bool HDR10PlusActive() const { return activePlus; }
 Props* GetConnector() { return &connector; }
 const Props* GetCrtc() const { return &crtc; }
};
struct Settings {
 bool GetBool(int) const { return true; }
 const Settings* GetSettings() const { return this; }
};
struct CServiceBroker {
 static const Settings* GetSettingsComponent() { static Settings settings; return &settings; }
};
struct Window {
 std::shared_ptr<CDRMAtomic> m_DRM=std::make_shared<CDRMAtomic>();
 Display display;
 const Display* m_info=&display;
 struct { bool IsValid() const { return true; } int Get() const { return 42; } } m_hdrBlob;
 KODI::UTILS::Eotf m_eotf=KODI::UTILS::Eotf::PQ;
 int m_colorimetry=9, m_queuedColorspace=9;
 bool Keep(const VideoPicture& picture) BODY
};
int main() {
 Window w;
 VideoPicture plain{StreamHdrType::HDR_TYPE_HDR10}, plus{StreamHdrType::HDR_TYPE_HDR10PLUS};
 assert(w.Keep(plain) && w.Keep(plus));
 w.display.version=0;
 assert(w.Keep(plain) && !w.Keep(plus));
 w.m_info=nullptr;
 assert(!w.Keep(plus));
 w.m_DRM->connector.supported=false;
 assert(w.Keep(plus));
 w.m_DRM->activePlus=true;
 assert(!w.Keep(plus) && !w.Keep(plain));
 w.m_DRM->activePlus=false;
 assert(!w.Keep({StreamHdrType::HDR_TYPE_HLG}));
 assert(!w.Keep({StreamHdrType::HDR_TYPE_HDR10PLUS,18}));
}
'''.replace('BODY',keep))
