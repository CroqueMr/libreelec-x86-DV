"""The DVD cadence corpus has the coding that the cadence tests rely on."""
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'tools/dvd-cadence'))
import corpus  # noqa: E402
import measure  # noqa: E402


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'requires ffmpeg')
class DvdCadenceCorpusTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.containers = all(shutil.which(t) for t in ('mkvpropedit', 'dvdauthor', 'xorriso'))
        corpus.main([cls.directory.name, '--seconds', '2'] +
                    (['--containers'] if cls.containers else []))

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def frames(self, name):
        return measure.frames(Path(self.directory.name) / f'{name}.mpg')

    def test_soft_telecine_is_progressive_film_with_alternating_field_repeats(self):
        frames = self.frames('ntsc_soft32')
        self.assertEqual(measure.probe(Path(self.directory.name) / 'ntsc_soft32.mpg')
                         ['avg_frame_rate'], '30000/1001')
        self.assertEqual(len(frames), 48)  # 2 s of 23.976 film
        self.assertFalse(any(interlaced for interlaced, _, _ in frames))
        self.assertEqual([repeat for _, repeat, _ in frames[:8]], [1, 0, 1, 0, 1, 0, 1, 0])

    def test_soft_telecine_timestamps_follow_the_displayed_fields(self):
        field = 1001 / 60000
        for name in ('ntsc_soft32.mpg', 'ntsc_soft32.mkv')[:2 if self.containers else 1]:
            times = [pts for _, _, pts in measure.frames(Path(self.directory.name) / name)]
            steps = [round((b - a) / field, 1) for a, b in zip(times, times[1:])]
            self.assertEqual(steps[:6], [3, 2, 3, 2, 3, 2], name)
            self.assertEqual(len(times), 48, name)

    def test_matroska_states_the_film_rate_of_a_stream_coded_at_29_97(self):
        if not self.containers:
            self.skipTest('requires mkvpropedit, dvdauthor and xorriso')
        path = Path(self.directory.name) / 'ntsc_soft32.mkv'
        self.assertEqual(measure.probe(path)['avg_frame_rate'], '24000/1001')
        self.assertEqual(corpus.coded_frame_rate(path), 4)  # MPEG-2 code of 30000/1001
        self.assertEqual([r for _, r, _ in measure.frames(path)[:4]], [1, 0, 1, 0])

    def test_the_iso_image_holds_the_soft_telecine_title(self):
        if not self.containers:
            self.skipTest('requires mkvpropedit, dvdauthor and xorriso')
        directory = Path(self.directory.name)
        self.assertTrue((directory / 'ntsc_soft32_dvd/VIDEO_TS/VIDEO_TS.IFO').is_file())
        vob = corpus.disc_title(directory / 'ntsc_soft32.iso', directory)
        self.assertEqual(measure.frames(vob), measure.frames(directory / 'ntsc_soft32.mpg'))

    def test_hard_telecine_and_video_are_interlaced_at_the_ntsc_frame_rate(self):
        for name in ('ntsc_hard32', 'ntsc_video', 'ntsc_mixed'):
            frames = self.frames(name)
            self.assertEqual(len(frames), 60, name)
            self.assertTrue(all(interlaced for interlaced, _, _ in frames), name)
            self.assertFalse(any(repeat for _, repeat, _ in frames), name)

    def test_pal_film_is_flagged_interlaced_or_progressive(self):
        self.assertTrue(all(i for i, _, _ in self.frames('pal_22')))
        self.assertFalse(any(i for i, _, _ in self.frames('pal_22_progressive')))


if __name__ == '__main__':
    unittest.main()
