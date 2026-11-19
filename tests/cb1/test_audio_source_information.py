"""Exercise the real read-only source observer, not the GUI mockup."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE') and os.environ.get('FFMPEG_TEST_PREFIX'),
                     'Set patched Kodi and FFmpeg test prefix')
class AudioSourceInformation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.binary = Path(cls.temporary.name) / 'audio-source'

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    def run_case(self, case):
        tree = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        prefix = Path(os.environ.get('FFMPEG_AUDIO_TEST_PREFIX', os.environ['FFMPEG_TEST_PREFIX']))
        if not self.binary.exists():
            result = subprocess.run(['c++', '-std=c++20', '-O1', '-g', '-fsanitize=address,undefined',
                '-I'+str(tree/'xbmc'), '-I'+str(prefix/'include'),
                str(tree/'xbmc/cores/AudioEngine/Utils/AEAudioSourceInfo.cpp'),
                str(Path(__file__).with_name('audio_source_information.cpp')),
                '-L'+str(prefix/'lib'), '-lavcodec', '-lavutil', '-lfmt', '-o', str(self.binary)],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr[-6000:])
        env = dict(os.environ, LD_LIBRARY_PATH=str(prefix/'lib'))
        result = subprocess.run([str(self.binary), case], capture_output=True, text=True, env=env)
        self.assertEqual(result.returncode, 0, result.stderr[-5000:])

    def test_source_precision_and_layout_are_not_decoder_or_transport_values(self):
        self.run_case('labels')

    def test_ac3_dialogue_level_and_dual_mono_follow_source_bits(self):
        self.run_case('ac3')

    def test_truehd_atmos_program_fields_are_validated_and_immutable(self):
        self.run_case('truehd')

    def test_eac3_oamd_is_not_invented_from_a_codec_name(self):
        self.run_case('eac3')

    def test_truncated_or_corrupt_headers_cannot_publish_details(self):
        self.run_case('malformed')

    def test_scan_budget_and_track_reset_bound_the_observer(self):
        self.run_case('bounded')

    def test_random_short_inputs_do_not_escape_bounds_or_modify_packets(self):
        self.run_case('fuzz')
