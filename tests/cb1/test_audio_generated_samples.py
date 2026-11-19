"""Verify the observer against freshly encoded samples, not only hand-built headers."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


@unittest.skipUnless(shutil.which('ffmpeg') and os.environ.get('KODI_NATIVE_SOURCE_TREE')
                     and os.environ.get('FFMPEG_TEST_PREFIX'), 'Requires FFmpeg and native source')
class GeneratedAudioSamples(unittest.TestCase):
    def test_real_ac3_eac3_truehd_frames_are_read_only(self):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        prefix = Path(os.environ.get('FFMPEG_AUDIO_TEST_PREFIX', os.environ['FFMPEG_TEST_PREFIX']))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            samples = []
            for codec in ('ac3', 'eac3', 'truehd'):
                target = root/(codec+'.bin')
                args = ['ffmpeg','-v','error','-f','lavfi','-i','anullsrc=r=48000:cl=stereo',
                        '-t','0.1','-c:a',codec,'-strict','-2']
                if codec != 'truehd':
                    args += ['-dialnorm','-27']
                result = subprocess.run(args+['-f',codec,str(target)], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                samples.append(str(target))
            result = subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(tree/'xbmc'),'-I'+str(prefix/'include'),
                str(tree/'xbmc/cores/AudioEngine/Utils/AEAudioSourceInfo.cpp'),
                str(Path(__file__).with_name('audio_source_information.cpp')),
                '-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lfmt','-o',str(root/'check')],
                capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-5000:])
            result = subprocess.run([str(root/'check'),'generated',*samples],
                env=dict(os.environ, LD_LIBRARY_PATH=str(prefix/'lib')), capture_output=True,text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-5000:])
