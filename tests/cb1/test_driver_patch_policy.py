"""Standard Debug builds retain LE patches but exclude our graphics additions."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class DriverPatchPolicy(unittest.TestCase):
    def test_standard_applies_only_the_native_patch(self):
        source = (ROOT/'scripts/unpack').read_text()
        start = source.index('      if [ -f "${i}" ]; then')
        stop = source.index('\n    done', start)
        fragment = source[start:stop]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'build').mkdir()
            ordinary = 'packages/linux/patches/default/9901-pm-disable-async-suspend-resume-by-default.patch'
            graphics = 'projects/Generic/patches/linux/linux-9910-common-dv-policy.patch'
            for path, old, new in ((ordinary, 'base', 'native'), (graphics, 'native', 'modified')):
                target = root/path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f'--- a/value\n+++ b/value\n@@ -1 +1 @@\n-{old}\n+{new}\n')
            (root/'config').mkdir()
            (root/'config/cb1-driver-patches.list').write_text(graphics+'\n')
            script = '''set -eu
ROOT=$1; PKG_BUILD=$ROOT/build; PROJECT=Generic; CB1_DEBUG=$2; CB1_DRIVER_PROFILE=$3
VERBOSE_OUT=1; PKG_NAME=linux; PATCH_DESC=test
build_msg(){ :; }; print_color(){ :; }
for i in "$ROOT/'''+ordinary+'" "$ROOT/'+graphics+'"; do\n'+fragment+'\ndone\n'
            for debug, profile, expected in [('yes', 'standard', 'native'),
                                              ('yes', 'modified', 'modified'),
                                              ('no', 'standard', 'modified')]:
                (root/'build/value').write_text('base\n')
                result = subprocess.run(['bash', '-c', script, 'test', str(root), debug, profile],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout+result.stderr)
                self.assertEqual((root/'build/value').read_text(), expected+'\n')
