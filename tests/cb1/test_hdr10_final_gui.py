"""Real GLES shader and shipped composition: direct HDR film survives GUI redraws."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from shipped_kodi import shipped_code
from test_native_video_source import body

ROOT = Path(__file__).resolve().parents[2]


class HDR10FinalGUI(unittest.TestCase):
    def test_hdr_gui_keeps_direct_film_unless_capturing(self):
        source = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        argument = re.search(r'return m_dvBridge->PrepareHardwareFrame\(layer, enhancement, enhancementBinding,\s*'
                             r'metadata, geometry, preferences,\s*(.*?), &policy, allowAsync\);', source, re.S)
        self.assertIsNotNone(argument)
        program = ('#include <cassert>\n'
                   'bool direct(bool overlayFree,bool nativeSubtitles,bool m_hdrConversion,bool capturing,bool optimized=true)'
                   '{struct{bool optimizedGUI;}preferences{optimized};return ' + argument[1] + ';}\n'
                   'int main(){assert(direct(false,false,true,false));'
                   'assert(!direct(false,false,true,true));assert(!direct(false,false,true,false,false));'
                   'assert(!direct(false,false,false,false));'
                   'assert(direct(true,false,false,false));assert(direct(false,true,false,false));}\n')
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary)
            (path / 'check.cpp').write_text(program)
            subprocess.run(['c++', str(path / 'check.cpp'), '-o', str(path / 'check')], check=True)
            run = subprocess.run([str(path / 'check')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_direct_target_range_orientation_and_transparent_compute(self):
        tree = os.environ.get('KODI_NATIVE_SOURCE_TREE')
        self.assertTrue(tree, 'set KODI_NATIVE_SOURCE_TREE to the tested native tree')
        native = shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        composite = body(native, 'void CWinSystemGbmGLESContext::CompositeGui()')
        source = (ROOT / 'CB1/tests/gui_final_hdr10.cpp').read_text()
        source = source.replace('GUI_COMPOSITE_BODY', composite)
        shader = shipped_code('xbmc/rendering/gles/GuiCompositeShaderGLES.cpp')
        source = source.replace('GUI_SHADER_ENABLE_BODY',
                                body(shader, 'bool CGuiCompositeShaderGLES::OnEnabled()'))
        bridge = shipped_code('xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h')
        source = source.replace('GUI_HDR_TARGET_BODY', body(bridge, 'bool GetHDR10OutputTarget('))
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            cpp, binary = directory / 'check.cpp', directory / 'check'
            cpp.write_text(source)
            build = subprocess.run(['c++', '-std=c++20', '-I', str(ROOT / 'CB1/src'),
                                    str(cpp), '-lEGL', '-lGLESv2', '-o', str(binary)],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(binary), str(Path(tree) /
                                 'system/shaders/GLES/2.0/gles_gui_composite.frag')],
                                 capture_output=True, text=True,
                                 env=dict(os.environ, EGL_PLATFORM='surfaceless',
                                          LIBGL_ALWAYS_SOFTWARE='1'))
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)


if __name__ == '__main__':
    unittest.main()
