"""Exercise shipped Kodi pending-picture admission with GUI-only changes."""
import pathlib
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

ROOT = pathlib.Path(__file__).resolve().parents[2]

class PendingRGB(unittest.TestCase):
    def test_gui_changes_keep_rgb_work_but_invalidate_fused_output(self):
        expressions = []
        code = shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        for match in re.finditer(r'if \((?:base.binding == m_pendingBinding &&\s*(?:revision|prediction.id.revision)|sameTransaction &&\s*m_pendingOverlayVisible|sameAITransaction && \(!m_direct).*?\)\s*return PollReady\(\)', code, re.S):
            expressions.append(match.group(0).rsplit('return PollReady()', 1)[0])
        ai_transaction=re.search(r'const bool sameAITransaction = .*?;',code,re.S)
        ai_transaction=ai_transaction.group(0) if ai_transaction else ''
        self.assertEqual(len(expressions),2)
        functions = []
        for index, expression in enumerate(expressions):
            functions.append('''bool admits%d(bool direct, bool guiChanged, bool pictureChanged=false, bool revisionChanged=false) {
  struct {int binding;} base{pictureChanged ? 2 : 1}; int m_pendingBinding=1;
  int revision=revisionChanged ? 2 : 1;
  struct {struct {int revision;} id;} prediction{{revision}};
  struct {int revision;} m_pendingIdentity{1};
  struct Preferences { int revision; bool SameValues(const Preferences&) const {return true;} } preferences{1},m_requested{1};
  struct {int mode;} policy{0}; int m_effectiveMode=0;
  bool m_direct=direct,allowPacked=true,sameGeometry=true;
  const bool sameTransaction=base.binding==m_pendingBinding && revision==m_pendingIdentity.revision && policy.mode==m_effectiveMode && (allowPacked || !m_direct);
  int m_pendingOverlayRevision=1,m_nativeOverlayRevision=guiChanged ? 2 : 1;
  bool m_pendingOverlayVisible=true,m_overlayVisible=true;
''' % index + ai_transaction+expression + 'return true; return false;}')
        assertions = '\n'.join('''
  assert(admits%d(false,true));
  assert(admits%d(false,false));
  assert(admits%d(true,false));
  assert(!admits%d(true,true));
  assert(!admits%d(false,true,true));
  assert(!admits%d(false,true,false,true));
''' % ((index,) * 6) for index in range(2))
        program = '#include <cassert>\n' + '\n'.join(functions) + '\nint main(){' + assertions + '}\n'
        with tempfile.TemporaryDirectory() as directory:
            source, binary = pathlib.Path(directory)/'check.cpp', pathlib.Path(directory)/'check'
            source.write_text(program)
            subprocess.run(['c++', '-std=c++20', str(source), '-o', str(binary)], check=True, capture_output=True)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
