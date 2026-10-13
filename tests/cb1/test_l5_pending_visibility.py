# SPDX-License-Identifier: MIT
"""Run the shipped pending-admission guards across L5 visibility edges."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class PendingVisibility(unittest.TestCase):
    def test_rgb_visibility_edges_reprepare_but_gui_redraw_reuses(self):
        source=os.environ.get('CB1_L5_KODI_SOURCE')
        if source:
            code=Path(source).read_text()
        else:
            patch=(ROOT/'projects/Generic/patches/kodi/kodi-9999-zzz-l5-overlay-visibility.patch').read_text()
            code='\n'.join(line[1:] for line in patch.splitlines()
                          if line.startswith((' ','+')) and not line.startswith('+++'))
        guards=re.findall(r'if \(base.binding == m_pendingBinding &&\s*(?:revision|prediction.id.revision).*?\)\s*return PollReady\(\)',code,re.S)
        self.assertEqual(len(guards),2)
        functions=[]
        for i,guard in enumerate(guards):
            condition=guard.rsplit('return PollReady()',1)[0]
            functions.append('''bool admits%d(bool direct, bool contentChange, bool visibilityChange, bool pendingVisible=false) {
  struct {int binding;} base{1}; int m_pendingBinding=1,revision=1;
  struct {struct {int revision;} id;} prediction{{1}};
  struct {int revision;} m_pendingIdentity{1};
  struct Preferences {int revision; bool SameValues(const Preferences&) const {return true;}} preferences{1},m_requested{1};
  struct {int mode;} policy{0}; int m_effectiveMode=0;
  bool m_direct=direct,allowPacked=true,sameGeometry=true;
  int m_pendingOverlayRevision=1,m_nativeOverlayRevision=contentChange||visibilityChange ? 2 : 1;
  bool m_pendingOverlayVisible=pendingVisible,m_overlayVisible=visibilityChange ? !pendingVisible : pendingVisible;
''' % i + condition+'return true; return false;}')
        checks=[]
        for i in range(2):
            checks.append('''
  assert(!admits%d(false,false,true));
  assert(!admits%d(false,false,true,true));
  assert(admits%d(false,true,false,true));
  assert(admits%d(false,false,false));
  assert(!admits%d(true,true,false,true));
  assert(!admits%d(true,false,true));
  assert(admits%d(true,false,false));
''' % ((i,)*7))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'check.cpp').write_text('#include <cassert>\n'+'\n'.join(functions)+'\nint main(){'+'\n'.join(checks)+'}')
            subprocess.run(['c++','-std=c++20',str(root/'check.cpp'),'-o',str(root/'check')],check=True,capture_output=True)
            result=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__': unittest.main()
