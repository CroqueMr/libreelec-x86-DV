"""Run real BD-J controls with explicitly supplied matched build dependencies."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest


class BdjControls(unittest.TestCase):
    def test_matched_video_and_stream_controls(self):
        jar_dir = os.environ.get('CB1_BDJ_JAR_DIR')
        java_home = os.environ.get('JAVA_HOME')
        if not jar_dir or not java_home:
            self.skipTest('requires the matched libbluray JAR pair and JDK')
        jars = sorted(Path(jar_dir).glob('libbluray*j2se-*.jar'))
        self.assertEqual(len(jars), 2)
        classpath = os.pathsep.join(map(str, jars))
        with tempfile.TemporaryDirectory() as directory:
            built = subprocess.run([str(Path(java_home)/'bin/javac'), '-cp', classpath,
                '-d', directory, str(Path(__file__).with_name('BdjControls.java'))],
                capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(Path(java_home)/'bin/java'), '-cp',
                directory + os.pathsep + classpath, 'BdjControls'], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
