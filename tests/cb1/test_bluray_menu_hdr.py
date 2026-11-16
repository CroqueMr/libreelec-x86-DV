"""Run the shipped disc menu HDR conversion: real GLES shaders and the native routing code."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from shipped_kodi import shipped_code
from test_native_video_source import TREE, body


def build_and_run(test, program, *flags, env=None):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'probe.cpp').write_text(program)
        built = subprocess.run(['c++', '-std=c++20', str(root / 'probe.cpp'), *flags,
                                '-o', str(root / 'probe')], capture_output=True, text=True)
        test.assertEqual(built.returncode, 0, built.stderr[-4000:])
        run = subprocess.run([str(root / 'probe')], capture_output=True, text=True, env=env)
        test.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout


SHADER_PROGRAM = r'''
#include <EGL/egl.h>
#include <GLES3/gl3.h>
#include <algorithm>
#include <array>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <iostream>
#include <string>
#include <vector>

// Shipped GUI composite LUT generators (GuiCompositeShaderGLES.cpp).
constexpr int LUT_SIZE = LUT_SIZE_VALUE;
constexpr float ST2084_m1 = 0.1593017578125f, ST2084_m2 = 78.84375f, ST2084_c1 = 0.8359375f,
                ST2084_c2 = 18.8515625f, ST2084_c3 = 18.6875f;
float ForwardPQ(float L) FORWARD_PQ
float SRGBToLinear(float v) SRGB_TO_LINEAR
std::vector<float> GenerateDegammaLUT() DEGAMMA_LUT
std::vector<float> GeneratePQLUT(float sdrPeak) PQ_LUT

const std::string noblend = R"glsl(NOBLEND_SHADER)glsl";
const std::string composite = R"glsl(COMPOSITE_SHADER)glsl";

// The colours a menu is made of: neutrals, primaries, a skin tone, near black.
const std::vector<std::array<unsigned char, 4>> texels = {
    {255, 255, 255, 255}, {128, 128, 128, 255}, {255, 0, 0, 255},   {0, 255, 0, 255},
    {0, 0, 255, 255},     {230, 150, 60, 255},  {8, 8, 8, 255},     {60, 120, 200, 255},
    // premultiplied, half and quarter coverage
    {115, 75, 30, 128},   {32, 32, 32, 64}};
constexpr int count = 10;

GLuint shader(GLenum kind, const std::string& text)
{
  GLuint value = glCreateShader(kind);
  const char* p = text.c_str();
  glShaderSource(value, 1, &p, nullptr);
  glCompileShader(value);
  GLint ok;
  glGetShaderiv(value, GL_COMPILE_STATUS, &ok);
  if (!ok) { char log[4096]; glGetShaderInfoLog(value, sizeof(log), nullptr, log); std::cerr << log; }
  assert(ok);
  return value;
}

GLuint program(const std::string& vertex, const std::string& fragment)
{
  GLuint value = glCreateProgram();
  glAttachShader(value, shader(GL_VERTEX_SHADER, vertex));
  glAttachShader(value, shader(GL_FRAGMENT_SHADER, fragment));
  glBindAttribLocation(value, 0, "a_pos");
  glLinkProgram(value);
  GLint ok;
  glGetProgramiv(value, GL_LINK_STATUS, &ok);
  assert(ok);
  return value;
}

GLuint texture(GLint format, GLenum layout, GLenum type, int width, const void* data, GLint filter)
{
  GLuint value;
  glGenTextures(1, &value);
  glBindTexture(GL_TEXTURE_2D, value);
  glTexImage2D(GL_TEXTURE_2D, 0, format, width, 1, 0, layout, type, data);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, filter);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, filter);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE);
  glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE);
  return value;
}

std::vector<float> draw(GLuint prog)
{
  glUseProgram(prog);
  const float quad[] = {-1, -1, 1, -1, -1, 1, 1, 1};
  glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 0, quad);
  glEnableVertexAttribArray(0);
  glDisable(GL_BLEND);
  glDrawArrays(GL_TRIANGLE_STRIP, 0, 4);
  std::vector<float> out(count * 4);
  glReadPixels(0, 0, count, 1, GL_RGBA, GL_FLOAT, out.data());
  return out;
}

double decode(double v) { return v <= 0.04045 ? v / 12.92 : std::pow((v + 0.055) / 1.055, 2.4); }
double pq(double l)
{
  const double p = std::pow(std::max(l, 0.0), 0.1593017578125);
  return std::pow((0.8359375 + 18.8515625 * p) / (1 + 18.6875 * p), 78.84375);
}
double inversePQ(double e)
{
  const double p = std::pow(e, 1 / 78.84375);
  return std::pow(std::max(p - 0.8359375, 0.0) / (18.8515625 - 18.6875 * p), 1 / 0.1593017578125);
}

// Independent double precision model: straight sRGB -> linear BT.709 -> saturation -> BT.2020
// -> reference white times gain -> PQ, premultiplied again when the texel was.
std::array<double, 4> expected(const std::array<unsigned char, 4>& t, double gain, double sat,
                               bool limited, bool pma)
{
  const double a = t[3] / 255.0;
  double c[3];
  for (int i = 0; i < 3; ++i)
    c[i] = decode(std::clamp(pma ? (a > 0 ? t[i] / 255.0 / a : 0) : t[i] / 255.0, 0.0, 1.0));
  const double y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  for (double& v : c) v = std::max(y + (v - y) * sat, 0.0);
  const double m[3][3] = {{0.6274, 0.3293, 0.0433}, {0.0691, 0.9195, 0.0114}, {0.0164, 0.0880, 0.8956}};
  std::array<double, 4> r{};
  for (int i = 0; i < 3; ++i)
  {
    double v = 0;
    for (int j = 0; j < 3; ++j) v += m[i][j] * c[j];
    v = pq(std::min(v * 0.0203 * gain, 1.0));
    if (limited) v = v * 219 / 255 + 16.0 / 255;
    r[i] = pma ? v * a : v;
  }
  r[3] = a;
  return r;
}

int main()
{
  EGLDisplay display = eglGetDisplay(EGL_DEFAULT_DISPLAY);
  assert(eglInitialize(display, nullptr, nullptr));
  assert(eglBindAPI(EGL_OPENGL_ES_API));
  EGLint attr[] = {EGL_SURFACE_TYPE, EGL_PBUFFER_BIT, EGL_RENDERABLE_TYPE, EGL_OPENGL_ES3_BIT, EGL_NONE};
  EGLConfig config;
  EGLint found;
  assert(eglChooseConfig(display, attr, &config, 1, &found) && found);
  EGLint size[] = {EGL_WIDTH, count, EGL_HEIGHT, 1, EGL_NONE}, version[] = {EGL_CONTEXT_CLIENT_VERSION, 3, EGL_NONE};
  EGLSurface surface = eglCreatePbufferSurface(display, config, size);
  EGLContext context = eglCreateContext(display, config, EGL_NO_CONTEXT, version);
  assert(eglMakeCurrent(display, surface, surface, context));

  GLuint target = texture(GL_RGBA32F, GL_RGBA, GL_FLOAT, count, nullptr, GL_NEAREST);
  GLuint framebuffer;
  glGenFramebuffers(1, &framebuffer);
  glBindFramebuffer(GL_FRAMEBUFFER, framebuffer);
  glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, target, 0);
  assert(glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE);
  glViewport(0, 0, count, 1);

  std::vector<unsigned char> bytes;
  for (const auto& t : texels) bytes.insert(bytes.end(), t.begin(), t.end());
  glActiveTexture(GL_TEXTURE0);
  texture(GL_RGBA, GL_RGBA, GL_UNSIGNED_BYTE, count, bytes.data(), GL_NEAREST);

  // gles_shader_texture_noblend.frag, as COverlayTextureGLES draws a menu.
  const std::string vertex = "#version 100\nattribute vec2 a_pos;varying vec4 m_cord0;"
      "void main(){gl_Position=vec4(a_pos,0.,1.);m_cord0=vec4(a_pos*.5+.5,0.,0.);}";
  GLuint menu = program(vertex, noblend);
  glUseProgram(menu);
  glUniform1i(glGetUniformLocation(menu, "m_samp0"), 0);
  const GLint menuPQ = glGetUniformLocation(menu, "m_menuPQ"), pmaLoc = glGetUniformLocation(menu, "m_pma");
  assert(menuPQ >= 0 && pmaLoc >= 0);

  // CGLESShader::OnEnabled leaves the conversion off: every other noblend draw is untouched.
  // The shader's own mediump texel (fp16 on llvmpipe) is the only rounding, far below 1/255.
  glUniform4f(menuPQ, 0, 1, 0, 0);
  glUniform1f(pmaLoc, 0);
  auto out = draw(menu);
  for (int i = 0; i < count; ++i)
    for (int c = 0; c < 4; ++c)
      assert(std::abs(out[i * 4 + c] - texels[i][c] / 255.0f) < 0.25f / 255);

  double worst = 0;
  struct Case { double gain, sat; bool limited, pma; };
  for (const Case& k : {Case{1, 1, false, false}, Case{2.5, 1, false, false}, Case{5, 1, false, false},
                        Case{1, 0, false, false}, Case{1, 2, false, false}, Case{3, 1.5, true, false},
                        Case{2, 1, false, true}, Case{0.5, 1, true, true}})
  {
    glUseProgram(menu);
    glUniform4f(menuPQ, float(k.gain), float(k.sat), k.limited ? 1.f : 0.f, 0);
    glUniform1f(pmaLoc, k.pma ? 1.f : 0.f);
    out = draw(menu);
    for (int i = 0; i < count; ++i)
    {
      if (!k.pma && texels[i][3] != 255) continue; // straight alpha cases use opaque texels
      const auto e = expected(texels[i], k.gain, k.sat, k.limited, k.pma);
      for (int c = 0; c < 4; ++c)
      {
        const double d = std::abs(out[i * 4 + c] - e[c]);
        worst = std::max(worst, d);
        if (d > 2e-4)
        {
          std::printf("texel %d channel %d gain %.2f sat %.2f: %f, expected %f\n", i, c, k.gain,
                      k.sat, out[i * 4 + c], e[c]);
          return 1;
        }
      }
    }
    if (k.sat == 0 && !k.limited && !k.pma)
      for (int i = 0; i < count; ++i)
        assert(std::abs(out[i * 4] - out[i * 4 + 1]) < 1e-5 && std::abs(out[i * 4] - out[i * 4 + 2]) < 1e-5);
  }

  // Brightness is a linear-light gain: white at 250% is 2.5 x 203 nits.
  glUseProgram(menu);
  glUniform4f(menuPQ, 2.5f, 1, 0, 0);
  glUniform1f(pmaLoc, 0);
  out = draw(menu);
  assert(std::abs(inversePQ(out[0]) * 10000 - 507.5) < 0.5);

  // At 100% / 100% the converted menu matches what the shipped GUI composite makes of the same
  // texel (PQ path, BT.2408 reference white), within that composite's own 256 entry LUTs.
  glUniform4f(menuPQ, 1, 1, 0, 0);
  const auto converted = draw(menu);
  const std::string compositeVertex = "attribute vec2 a_pos;varying vec2 v_tex;"
      "void main(){gl_Position=vec4(a_pos,0.,1.);v_tex=a_pos*.5+.5;}";
  GLuint gui = program(compositeVertex, composite);
  glActiveTexture(GL_TEXTURE1);
  const auto degamma = GenerateDegammaLUT();
  texture(GL_R16F, GL_RED, GL_FLOAT, LUT_SIZE, degamma.data(), GL_LINEAR);
  glActiveTexture(GL_TEXTURE2);
  const auto transfer = GeneratePQLUT(203.0f / 10000.0f);
  texture(GL_R16F, GL_RED, GL_FLOAT, LUT_SIZE, transfer.data(), GL_LINEAR);
  glActiveTexture(GL_TEXTURE0);
  glUseProgram(gui);
  glUniform1i(glGetUniformLocation(gui, "u_samp"), 0);
  glUniform1i(glGetUniformLocation(gui, "u_lutDegamma"), 1);
  glUniform1i(glGetUniformLocation(gui, "u_lutTF"), 2);
  glUniform1f(glGetUniformLocation(gui, "u_ootfGamma"), 0);
  glUniform2f(glGetUniformLocation(gui, "u_outputRange"), 1, 0);
  const auto reference = draw(gui);
  double compositeWorst = 0, compositeError = 0;
  for (int i = 0; i < count; ++i)
  {
    if (texels[i][3] != 255) continue;
    const auto e = expected(texels[i], 1, 1, false, false);
    for (int c = 0; c < 3; ++c)
    {
      compositeWorst = std::max(compositeWorst, double(std::abs(converted[i * 4 + c] - reference[i * 4 + c])));
      compositeError = std::max(compositeError, std::abs(reference[i * 4 + c] - e[c]));
    }
  }
  std::printf("menu vs exact %.2g, menu vs GUI composite %.2g, GUI composite vs exact %.2g\n",
              worst, compositeWorst, compositeError);
  // Same curve: all that separates them is the composite's own 256 entry LUT interpolation,
  // which is coarsest near black. The menu path is exact to 2e-4 above.
  assert(compositeWorst <= compositeError + 2e-4);
  assert(glGetError() == GL_NO_ERROR);
}
'''

ROUTING_PROGRAM = r'''
#include <algorithm>
#include <cassert>
#include <memory>
#include <optional>
#include <string>
#define HAS_GLES 1
#define HAVE_DVBRIDGE 1
namespace KODI::UTILS { enum class Eotf { TRADITIONAL_SDR, PQ }; }
enum class DVDOverlaySource { SUBTITLE, MENU };
struct CSetting {};
struct CSettings {
  static constexpr auto SETTING_DISC_MENUHDRBRIGHTNESS = "disc.menuhdrbrightness";
  static constexpr auto SETTING_DISC_MENUHDRSATURATION = "disc.menuhdrsaturation";
  int brightness = 100, saturation = 100;
  bool registered = true;
  std::shared_ptr<CSetting> GetSetting(const std::string&) const
  { return registered ? std::make_shared<CSetting>() : nullptr; }
  int GetInt(const std::string& id) const
  { return id == SETTING_DISC_MENUHDRBRIGHTNESS ? brightness : saturation; }
};
struct CSettingsComponent {
  std::shared_ptr<CSettings> settings = std::make_shared<CSettings>();
  std::shared_ptr<CSettings> GetSettings() const { return settings; }
};
struct CWinSystemBase {
  virtual ~CWinSystemBase() = default;
  bool composite = true;
  KODI::UTILS::Eotf eotf = KODI::UTILS::Eotf::PQ;
  bool IsHdrComposite() const { return composite; }
  KODI::UTILS::Eotf GetEotf() const { return eotf; }
};
namespace KODI::WINDOWING::GBM {
struct CWinSystemGbmGLESContext : CWinSystemBase {
  bool cb1 = false, sdrCompositor = false;
  bool HasDVBridgeScreenshot() const { return cb1; }
  bool IsDVBridgeScreenshotSDR() const { return cb1 && sdrCompositor; }
};
}
struct CServiceBroker {
  static inline auto component = std::make_shared<CSettingsComponent>();
  static inline KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
  static std::shared_ptr<CSettingsComponent> GetSettingsComponent() { return component; }
  static CWinSystemBase* GetWinSystem() { return &window; }
};
namespace OVERLAY {
struct COverlay {
  bool m_isHDROverlay{false};
  DVDOverlaySource m_source{DVDOverlaySource::SUBTITLE};
  bool m_isBitmap{false};
};
struct MenuPQAdjustment MENU_ADJUSTMENT;
bool ShouldConvertPQPaletteToSRGB(bool isHDROverlay) SHOULD_CONVERT
std::optional<MenuPQAdjustment> GetMenuPQAdjustment() GET_ADJUSTMENT
namespace { DRAWS_AS_PQ }
}
int main() {
  using namespace OVERLAY;
  auto& settings = *CServiceBroker::component->settings;
  auto& window = CServiceBroker::window;
  // Neutral settings keep every menu in the GUI composite exactly as before.
  assert(!GetMenuPQAdjustment());
  settings.brightness = 250;
  auto adjustment = GetMenuPQAdjustment();
  assert(adjustment && adjustment->gain == 2.5f && adjustment->saturation == 1.0f);
  settings.brightness = 100; settings.saturation = 150;
  assert(GetMenuPQAdjustment() && GetMenuPQAdjustment()->gain == 1.0f &&
         GetMenuPQAdjustment()->saturation == 1.5f);
  settings.brightness = 9000; settings.saturation = -4;
  assert(GetMenuPQAdjustment()->gain == 5.0f && GetMenuPQAdjustment()->saturation == 0.0f);
  // SDR output, and CB1's SDR compositor, take the sRGB menu as they always did.
  window.composite = false; window.eotf = KODI::UTILS::Eotf::TRADITIONAL_SDR;
  assert(!GetMenuPQAdjustment());
  window.composite = true; window.eotf = KODI::UTILS::Eotf::PQ;
  window.cb1 = true; window.sdrCompositor = true;
  assert(!GetMenuPQAdjustment());
  // CB1's Dolby Vision and rendering circuits compose the picture themselves: menus stay put.
  window.sdrCompositor = false;
  assert(!GetMenuPQAdjustment());
  window.cb1 = false;
  assert(GetMenuPQAdjustment());
  settings.registered = false;
  assert(!GetMenuPQAdjustment());

  // Only disc menu bitmaps move; subtitles and DVD SPU menus keep their routes.
  COverlay menu{false, DVDOverlaySource::MENU, true};
  COverlay spuMenu{false, DVDOverlaySource::MENU, false};
  COverlay subtitle{false, DVDOverlaySource::SUBTITLE, true};
  COverlay pqSubtitle{true, DVDOverlaySource::SUBTITLE, true};
  assert(DrawsAsPQ(menu, true) && !DrawsAsPQ(menu, false));
  assert(!DrawsAsPQ(spuMenu, true) && !DrawsAsPQ(subtitle, true));
  assert(DrawsAsPQ(pqSubtitle, false) && DrawsAsPQ(pqSubtitle, true));
}
'''


class BlurayMenuHDR(unittest.TestCase):
    def test_menu_shader_converts_to_pq_and_matches_gui_composite_when_neutral(self):
        shaders = TREE / 'system/shaders/GLES/2.0'
        composite = shipped_code('xbmc/rendering/gles/GuiCompositeShaderGLES.cpp')
        header = shipped_code('xbmc/rendering/gles/GuiCompositeShaderGLES.h')
        lut_size = re.search(r'static constexpr int LUT_SIZE = (\d+);', header)
        self.assertIsNotNone(lut_size)
        program = SHADER_PROGRAM
        for key, value in {
            'LUT_SIZE_VALUE': lut_size[1],
            'FORWARD_PQ': body(composite, 'float ForwardPQ(float L)'),
            'SRGB_TO_LINEAR': body(composite, 'float SRGBToLinear(float v)'),
            'DEGAMMA_LUT': body(composite, 'std::vector<float> CGuiCompositeShaderGLES::GenerateDegammaLUT()'),
            'PQ_LUT': body(composite, 'std::vector<float> CGuiCompositeShaderGLES::GeneratePQLUT(float sdrPeak)'),
            'NOBLEND_SHADER': (shaders / 'gles_shader_texture_noblend.frag').read_text(),
            'COMPOSITE_SHADER': (shaders / 'gles_gui_composite.frag').read_text(),
        }.items():
            program = program.replace(key, value)
        build_and_run(self, program, '-lEGL', '-lGLESv2',
                      env=dict(os.environ, EGL_PLATFORM='surfaceless', LIBGL_ALWAYS_SOFTWARE='1'))

    def test_menu_route_is_neutral_by_default_and_pq_destination_only(self):
        utility = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRendererUtil.cpp').read_text()
        header = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRendererUtil.h').read_text()
        renderer = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRenderer.cpp').read_text()
        draws = 'bool DrawsAsPQ(const COverlay& overlay, bool menuPQ)'
        program = ROUTING_PROGRAM
        for key, value in {
            'MENU_ADJUSTMENT': body(header, 'struct MenuPQAdjustment'),
            'SHOULD_CONVERT': body(utility, 'bool ShouldConvertPQPaletteToSRGB('),
            'GET_ADJUSTMENT': body(utility, 'std::optional<MenuPQAdjustment> GetMenuPQAdjustment()'),
            'DRAWS_AS_PQ': draws + body(renderer, draws),
        }.items():
            program = program.replace(key, value)
        build_and_run(self, program, '-fsanitize=address,undefined')

    def test_menu_settings_default_to_the_unchanged_gui_composite(self):
        settings = ET.parse(TREE / 'system/settings/settings.xml').getroot()
        strings = (TREE / 'addons/resource.language.en_gb/resources/strings.po').read_text()
        discs = settings.find(".//category[@id='discs']")
        self.assertIsNotNone(discs)
        for name, low, high in (('disc.menuhdrbrightness', '50', '500'),
                                ('disc.menuhdrsaturation', '0', '200')):
            with self.subTest(setting=name):
                setting = discs.find(f".//setting[@id='{name}']")
                self.assertIsNotNone(setting)
                self.assertEqual(setting.findtext('requirement'), 'HAVE_DVBRIDGE')
                self.assertEqual(setting.findtext('default'), '100')
                self.assertEqual(setting.findtext('constraints/minimum'), low)
                self.assertEqual(setting.findtext('constraints/maximum'), high)
                self.assertEqual(setting.find('dependencies/dependency').get('name'), 'ishdrdisplay')
                for label in (setting.get('label'), setting.get('help')):
                    self.assertIn(f'msgctxt "#{label}"\nmsgid "', strings)
        self.assertEqual(len(re.findall(r'^msgctxt "#4136[0-2]"$', strings, re.M)), 3)


if __name__ == '__main__':
    unittest.main()
