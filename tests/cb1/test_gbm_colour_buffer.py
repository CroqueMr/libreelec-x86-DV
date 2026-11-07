"""Keep the actual GBM scanout locked while colour requests are refused."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class GbmColourBuffer(unittest.TestCase):
    def test_repeated_refusals_never_release_the_displayed_buffer(self):
        root=TREE/'xbmc/windowing/gbm'
        window=(root/'WinSystemGbm.cpp').read_text()
        surface=(root/'GBMUtils.cpp').read_text()
        program=Path(__file__).with_name('gbm_colour_buffer.cpp').read_text()
        owners={
            'FLIP':body(window,'void CWinSystemGbm::FlipPage('),
            'LOCK':body(surface,'    LockFrontBuffer()'),
            'PENDING':body(surface,'gbm_bo* CGBMUtils::CGBMDevice::CGBMSurface::LockTransactionalBuffer('),
            'COMPLETE':body(surface,'void CGBMUtils::CGBMDevice::CGBMSurface::CompleteTransactionalBuffer('),
            'END':body(surface,'void CGBMUtils::CGBMDevice::CGBMSurface::EndTransactionalMode('),
        }
        for marker,source in owners.items():
            program=program.replace('@'+marker+'@',source)
        with tempfile.TemporaryDirectory(prefix='gbm-colour-buffer-') as tmp:
            binary=Path(tmp)/'check'
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                                  '-x','c++','-','-o',str(binary)],input=program,
                                 capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
