"""Run the registered current SDR pixel fixture against matched production ABIs."""
from pathlib import Path
import os
import re
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class SDRRenderTests(unittest.TestCase):
    def test_current_staged_and_direct_pixels(self):
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        self.assertTrue((prefix/'lib/pkgconfig/libavutil.pc').is_file())
        env = dict(os.environ)
        env['PKG_CONFIG_PATH'] = str(prefix/'lib/pkgconfig')+':'+env.get('PKG_CONFIG_PATH','')
        def pkg(*args):
            return subprocess.check_output(['pkg-config',*args],env=env,text=True).strip()
        self.assertTrue(pkg('--modversion','libplacebo').startswith('7.372.'))
        self.assertTrue(pkg('--modversion','libavutil').startswith('61.'))
        placebo = Path(pkg('--variable=libdir','libplacebo'))
        avutil = Path(pkg('--variable=libdir','libavutil'))
        self.assertEqual(avutil.resolve(), (prefix/'lib').resolve())
        env['LD_LIBRARY_PATH'] = str(placebo)+':'+str(avutil)+':'+env.get('LD_LIBRARY_PATH','')
        env.update(EGL_PLATFORM='surfaceless',LIBGL_ALWAYS_SOFTWARE='1')
        flags = shlex.split(pkg('--cflags','--libs','libplacebo','libavutil','libavcodec','glesv2','egl','libdrm','libva'))
        with tempfile.TemporaryDirectory() as temporary:
            build = Path(temporary)
            for cmd in (
                ['cmake','-S',str(ROOT/'CB1/src'),'-B',str(build),'-DCMAKE_BUILD_TYPE=RelWithDebInfo'],
                ['cmake','--build',str(build),'--target','dvbridge_core','-j2'],
                ['cc','-std=gnu11','-UNDEBUG','-I'+str(ROOT/'CB1/src'),'-I'+str(build),
                 str(ROOT/'CB1/tests/sdr_render.c'),str(build/'libdvbridge_core.a'),*flags,'-lm','-ldl','-o',str(build/'sdr_render')]):
                result = subprocess.run(cmd,env=env,capture_output=True,text=True)
                self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            linkage = subprocess.check_output(['ldd',str(build/'sdr_render')],env=env,text=True)
            self.assertIn(str(placebo/'libplacebo.so.372'),linkage)
            self.assertIn(str(avutil/'libavutil.so.61'),linkage)
            result = subprocess.run([str(build/'sdr_render')],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            self.assertEqual(len(re.findall(r'^PAIR \d+ max=',result.stdout,re.M)),555)
            self.assertIn('COMPLETE 555 staged/direct SDR comparisons',result.stdout)
            self.assertNotIn('UNAVAILABLE',result.stdout)


if __name__ == '__main__':
    unittest.main()
