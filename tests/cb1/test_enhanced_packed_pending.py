"""A pending Enhanced packed picture retains its composition route."""
import pathlib
import re
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

class EnhancedPackedPending(unittest.TestCase):
    def test_pending_keeps_direct_route_until_ready(self):
        code=shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp')
        expression=re.search(r'm_direct = status == DVBRIDGE_DV_READY[^;]*;',code).group()
        program='''#include <cassert>
enum {DVBRIDGE_DV_FAILED, DVBRIDGE_DV_UNSUPPORTED, DVBRIDGE_DV_BUSY,
      DVBRIDGE_DV_PENDING, DVBRIDGE_DV_READY, DVBRIDGE_DV_IDLE};
bool direct(int status) {bool m_direct=false; '''+expression+''' return m_direct;}
int main(){assert(direct(DVBRIDGE_DV_PENDING));assert(direct(DVBRIDGE_DV_READY));
assert(!direct(DVBRIDGE_DV_FAILED));assert(!direct(DVBRIDGE_DV_UNSUPPORTED));}
'''
        with tempfile.TemporaryDirectory() as directory:
            source=pathlib.Path(directory)/'check.cpp';binary=pathlib.Path(directory)/'check'
            source.write_text(program)
            subprocess.run(['c++',str(source),'-o',str(binary)],check=True,capture_output=True)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
