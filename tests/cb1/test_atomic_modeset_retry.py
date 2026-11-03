"""A rejected native modeset must be retried, not mistaken for configured output."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


class AtomicModesetRetry(unittest.TestCase):
    def test_pending_modeset_survives_rejection(self):
        tree = os.environ.get('KODI_NATIVE_SOURCE_TREE')
        if not tree:
            self.skipTest('requires the fully prepared native Kodi tree')
        source = (Path(tree) / 'xbmc/windowing/gbm/drm/DRMAtomic.cpp').read_text()
        body = re.search(r'void CDRMAtomic::FlipPage\(.*?^}', source, re.S | re.M)
        self.assertIsNotNone(body)
        program = r'''
#include <cassert>
#include <cstdint>
#include <optional>
#include <vector>
constexpr int LOGERROR=1,LOGDEBUG=2;
constexpr unsigned DRM_MODE_ATOMIC_NONBLOCK=1,DRM_MODE_ATOMIC_ALLOW_MODESET=2;
struct CLog {template<class... T> static void LogF(T...) {}};
struct gbm_bo {bool usable=true;};
struct drm_fb {int fb_id=12;};
struct CDRMUtils {static drm_fb* DrmFbGetFromBo(gbm_bo* bo) {
 static drm_fb fb;return bo && bo->usable ? &fb : nullptr;}};
struct CDRMAtomic {
 bool m_need_modeset=true,m_lastPageAccepted=false,configured=false;
 bool permanent=false,rejectNext=true,fallbackNext=false;
 std::optional<int> m_hdr10plusPacket;
 std::vector<unsigned> attempts;
 void ResetCB1PresentationTime() {}
 bool DrmAtomicCommit(int,unsigned flags,bool,bool) {
  attempts.push_back(flags);
  if(permanent || rejectNext) {rejectNext=false;return false;}
  if(fallbackNext) {fallbackNext=false;return true;}
  if(!configured && !(flags & DRM_MODE_ATOMIC_ALLOW_MODESET)) return false;
  configured=true;return true;
 }
 void FlipPage(gbm_bo*,bool,bool,bool);
 bool IsSelectedModeCommitted() const {return configured;}
};
BODY
int main() {
 gbm_bo buffer;
 CDRMAtomic retry;
 retry.FlipPage(&buffer,true,false,true);
 assert(retry.m_need_modeset && !retry.m_lastPageAccepted);
 retry.FlipPage(&buffer,true,false,true);
 assert(retry.m_lastPageAccepted && !retry.m_need_modeset);
 assert(retry.attempts.size()==2 &&
  (retry.attempts[1] & DRM_MODE_ATOMIC_ALLOW_MODESET) &&
  !(retry.attempts[1] & DRM_MODE_ATOMIC_NONBLOCK));
 retry.FlipPage(&buffer,true,false,true);
 assert(retry.m_lastPageAccepted &&
  (retry.attempts.back() & DRM_MODE_ATOMIC_NONBLOCK) &&
  !(retry.attempts.back() & DRM_MODE_ATOMIC_ALLOW_MODESET));
 CDRMAtomic permanent;
 permanent.permanent=true;
 permanent.FlipPage(&buffer,true,false,true);
 permanent.FlipPage(&buffer,true,false,true);
 assert(permanent.m_need_modeset && !permanent.m_lastPageAccepted);
 CDRMAtomic fallback;
 fallback.rejectNext=false;fallback.fallbackNext=true;
 fallback.FlipPage(&buffer,true,false,true);
 assert(fallback.m_lastPageAccepted && fallback.m_need_modeset && !fallback.configured);
 fallback.FlipPage(&buffer,true,false,true);
 assert(fallback.configured && !fallback.m_need_modeset &&
  (fallback.attempts.back() & DRM_MODE_ATOMIC_ALLOW_MODESET));
 CDRMAtomic missing;
 buffer.usable=false;
 missing.FlipPage(&buffer,true,false,true);
 assert(missing.m_need_modeset && missing.attempts.empty());
}
'''.replace('BODY', body.group())
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / 'check'
            built = subprocess.run(['c++', '-std=c++20', '-x', 'c++', '-', '-o', str(binary)],
                                   input=program, capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
