"""Reference must use the exact compact bounds path, not the legacy reduction."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class ReferenceBoundsTests(unittest.TestCase):
    def test_reference_and_adaptive_activate_exact_compact_bounds(self):
        source = (Path(os.environ['KODI_NATIVE_SOURCE_TREE']) /
            'xbmc/cores/VideoPlayer/VideoRenderers/HDR10AISource.cpp').read_text()
        section = source.split('  cb1_hdr10_ai_reset(m_context,binding.stream,m_revision);', 1)[1].split('\n}', 1)[0]
        program = r'''
#include <cassert>
enum class Source {Native,ReferenceDV,EnhancedDV};
namespace DVBRIDGE {using HDR10SourceMode=Source;}
enum Status {CB1_AI_READY,CB1_AI_INVALID};
bool enabled,allow=true;
bool cb1_hdr10_ai_set_coalesced_bounds(void*,bool value) {enabled=value;return allow;}
Status configure(Source mode) {
 void* m_context=nullptr;
 struct {Source hdr10Source;} preferences{mode};
 auto RecordStatus=[](const char*,Status s) {return s;};
 SECTION
}
int main() {
 assert(configure(Source::ReferenceDV)==CB1_AI_READY&&enabled);
 assert(configure(Source::EnhancedDV)==CB1_AI_READY&&enabled);
 allow=false;assert(configure(Source::ReferenceDV)==CB1_AI_INVALID);
}
'''.replace('SECTION', section)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', str(root/'test.cpp'), '-o', str(root/'test')],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root/'test')], capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stderr)


if __name__ == '__main__':
    unittest.main()
