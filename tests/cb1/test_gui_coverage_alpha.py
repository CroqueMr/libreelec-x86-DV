"""Real shipped GUI draws retain panel coverage without changing native HDR."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body

ROOT = Path(__file__).resolve().parents[2]


class GUICoverageAlpha(unittest.TestCase):
    def test_font_texture_and_cached_final_composition(self):
        # Reuse the existing real EGL/composite fixture, not a second compositor.
        source = (ROOT / 'CB1/tests/gui_final_hdr10.cpp').read_text().split('int main(')[0]
        window = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        source = source.replace('GUI_COMPOSITE_BODY', body(window, 'void CWinSystemGbmGLESContext::CompositeGui()'))
        source = source.replace('GUI_SHADER_ENABLE_BODY', body(
            (TREE / 'xbmc/rendering/gles/GuiCompositeShaderGLES.cpp').read_text(),
            'bool CGuiCompositeShaderGLES::OnEnabled()'))
        source = source.replace('GUI_HDR_TARGET_BODY', body(
            (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.h').read_text(),
            'bool GetHDR10OutputTarget('))
        source += (ROOT / 'CB1/tests/gui_coverage_alpha.cpp').read_text()
        base = (TREE / 'xbmc/windowing/WinSystem.h').read_text()
        header = (TREE / 'xbmc/windowing/gbm/WinSystemGbmGLESContext.h').read_text()
        signature = 'bool UseGuiCoverageAlpha() const'
        # Pre-fix source has no policy hook: execute its actual drawing bodies
        # unchanged; absence of a new symbol must not be the RED failure.
        native_policy = body(base, signature) if signature in base else '{return !IsHdrComposite();}'
        policy = body(header, signature) if signature in header else '{return CWinSystemBase::UseGuiCoverageAlpha();}'
        for key, value in {
            'NATIVE_POLICY': native_policy, 'CB1_POLICY': policy,
            'FONT_BEGIN': body((TREE / 'xbmc/guilib/GUIFontTTFGLES.cpp').read_text(),
                               'bool CGUIFontTTFGLES::FirstBegin()'),
            'TEXTURE_BEGIN': body((TREE / 'xbmc/guilib/GUITextureGLES.cpp').read_text(),
                                  'void CGUITextureGLES::Begin('),
        }.items():
            source = source.replace('@@' + key + '@@', value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cpp, binary = root / 'check.cpp', root / 'check'
            cpp.write_text(source)
            for disabled in [False, True]:
                command = ['c++', '-std=c++20', '-I' + str(ROOT / 'CB1/src')]
                if disabled:
                    command.append('-DCB1_TEST_DISABLE_DV')
                built = subprocess.run(command + [str(cpp), '-lEGL', '-lGLESv2', '-o', str(binary)],
                                       capture_output=True, text=True)
                self.assertEqual(built.returncode, 0, built.stderr)
                ran = subprocess.run([str(binary), str(TREE / 'system/shaders/GLES/2.0')],
                                     env=dict(os.environ, EGL_PLATFORM='surfaceless', LIBGL_ALWAYS_SOFTWARE='1'),
                                     capture_output=True, text=True)
                print(ran.stdout, end='')
                self.assertEqual(ran.returncode, 0, ran.stdout + ran.stderr)


if __name__ == '__main__':
    unittest.main()
