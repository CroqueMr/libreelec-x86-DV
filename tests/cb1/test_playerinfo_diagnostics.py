"""Keep Player Info timing opt-in and on the existing playback paths."""

import os
from pathlib import Path
import unittest


@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'matched Kodi source required')
class PlayerInfoDiagnosticsTests(unittest.TestCase):
    def test_trace_has_both_debug_gates_and_separate_stage_boundaries(self):
        kodi = Path(os.environ['KODI_NATIVE_SOURCE_TREE']) / 'xbmc'
        trace_file = kodi / 'utils/DVBridgeOverlayTrace.h'
        self.assertTrue(trace_file.is_file(), 'missing overlay trace')
        trace = trace_file.read_text()
        self.assertIn('DetailedDiagnosticsEnabled()', trace)
        self.assertIn('IsLogLevelLogged(LOGDEBUG)', trace)
        self.assertIn('DiagnosticInterval', trace)
        self.assertIn('LOGDEBUG', trace)

        dialog = (kodi / 'dialogs/GUIDialogPlayerProcessInfo.cpp').read_text()
        self.assertIn('CB1 Player Info open', dialog)
        self.assertIn('CB1 Player Info close', dialog)
        self.assertIn('OverlayStage::Refresh', dialog)

        app = (kodi / 'application/Application.cpp').read_text()
        for stage in ('Draw', 'Composite', 'Present'):
            self.assertIn(f'OverlayStage::{stage}', app)
        drm = (kodi / 'windowing/gbm/drm/DRMAtomic.cpp').read_text()
        self.assertIn('OverlayStage::Commit', drm)
        self.assertIn('OverlayStage::FenceWait', drm)

        video = (kodi / 'cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        self.assertIn('CB1 render buffer timeout', video)
        self.assertIn('DiagnosticInterval', video)
        self.assertIn('GetSkippedFrames()', video)
