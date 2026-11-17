"""Run the shipped UHD disc menu code: graphics follow the dynamic range of the video they go with."""
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body

BLURAY = 'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp'
UTILITY = 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRendererUtil.cpp'
TEXTURE = 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRendererGLES.cpp'


def build_and_run(test, program):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        (root / 'probe.cpp').write_text(program)
        built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                str(root / 'probe.cpp'), '-o', str(root / 'probe')],
                               capture_output=True, text=True)
        test.assertEqual(built.returncode, 0, built.stderr[-4000:])
        run = subprocess.run([str(root / 'probe')], capture_output=True, text=True)
        test.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        return run.stdout


def fill(program, values):
    for key, value in values.items():
        program = program.replace(key, value)
    return program


PALETTE_PROGRAM = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <initializer_list>
#define PIXEL_ASHIFT 24
#define PIXEL_RSHIFT 16
#define PIXEL_GSHIFT 8
#define PIXEL_BSHIFT 0
struct BD_PG_PALETTE_ENTRY { uint8_t Y, Cr, Cb, T; };
static uint8_t clamp(double v) CLAMP
static uint32_t build_rgba(const BD_PG_PALETTE_ENTRY &e, bool bt2020) BUILD_RGBA

// The limited-range BT.2020 non-constant luminance encode of full-range R'G'B' code values.
BD_PG_PALETTE_ENTRY encode(double r, double g, double b, uint8_t t)
{
  const double y = 0.2627 * r + 0.6780 * g + 0.0593 * b;
  const auto q = [](double v) { return static_cast<uint8_t>(std::lround(v)); };
  return {q(16 + 219 * y / 255), q(128 + 224 * (r - y) / 1.4746 / 255),
          q(128 + 224 * (b - y) / 1.8814 / 255), t};
}

int channel(uint32_t px, int shift) { return (px >> shift) & 0xff; }

int main()
{
  // HDR graphics decode with BT.2020 to the PQ code values they were authored as, within the
  // 8-bit rounding of the encode, and keep their alpha.
  const double colours[][3] = {{255, 255, 255}, {0, 0, 0}, {157, 157, 157}, {255, 0, 0},
                               {0, 255, 0},     {0, 0, 255}, {200, 120, 40}, {40, 90, 167}};
  int worst = 0;
  for (const auto& c : colours)
  {
    const uint32_t px = build_rgba(encode(c[0], c[1], c[2], 77), true);
    assert(channel(px, PIXEL_ASHIFT) == 77);
    worst = std::max({worst, std::abs(channel(px, PIXEL_RSHIFT) - int(c[0])),
                      std::abs(channel(px, PIXEL_GSHIFT) - int(c[1])),
                      std::abs(channel(px, PIXEL_BSHIFT) - int(c[2]))});
  }
  std::printf("BT.2020 palette round trip worst %d\n", worst);
  assert(worst <= 2);
  // Neutrals are exact: Kodi's limited range white and black.
  assert(build_rgba({235, 128, 128, 255}, true) == 0xffffffffu);
  assert(build_rgba({16, 128, 128, 255}, true) == 0xff000000u);

  // SDR graphics keep Kodi's own decode, coefficient for coefficient.
  for (const BD_PG_PALETTE_ENTRY e : {BD_PG_PALETTE_ENTRY{235, 128, 128, 255},
                                      BD_PG_PALETTE_ENTRY{81, 240, 90, 200},
                                      BD_PG_PALETTE_ENTRY{145, 34, 54, 10}})
  {
    const double r = 1.164 * (e.Y - 16) + 1.596 * (e.Cr - 128);
    const double g = 1.164 * (e.Y - 16) - 0.391 * (e.Cb - 128) - 0.813 * (e.Cr - 128);
    const double b = 1.164 * (e.Y - 16) + 2.018 * (e.Cb - 128);
    const uint32_t legacy = uint32_t(e.T) << 24 | uint32_t(clamp(r)) << 16 |
                            uint32_t(clamp(g)) << 8 | uint32_t(clamp(b));
    assert(build_rgba(e, false) == legacy);
  }
}
'''

DYNAMIC_RANGE_PROGRAM = r'''
#include <cassert>
#include <cstdint>
#include <list>
#include <memory>
#include <vector>
#define BD_OVERLAY_INTERFACE_VERSION 2
enum { LOGDEBUG };
struct CLog { template <class... T> static void Log(T&&...) {} };
enum { BLURAY_DYNAMIC_RANGE_SDR = 0, BLURAY_DYNAMIC_RANGE_HDR10 = 1,
       BLURAY_DYNAMIC_RANGE_DOLBY_VISION = 2 };
struct BLURAY_STREAM_INFO { uint8_t dynamic_range_type; };
struct BLURAY_CLIP_INFO { uint8_t video_stream_count; BLURAY_STREAM_INFO* video_streams; };
struct CDVDOverlayImage
{
  CDVDOverlayImage() = default;
  CDVDOverlayImage(const CDVDOverlayImage& src, int, int, int, int) : CDVDOverlayImage(src) {}
  std::vector<uint32_t> palette, alternatePalette;
  bool m_isHDROverlay = false;
  int x = 0, y = 0, width = 4, height = 4;
};
static bool IsHdrGraphicsClip(const BLURAY_CLIP_INFO& clip) IS_HDR_CLIP
struct CDVDInputStreamBluray
{
  typedef std::shared_ptr<CDVDOverlayImage> SOverlay;
  typedef std::list<SOverlay> SOverlays;
  struct SPlane { SOverlays o, committed; };
  SPlane m_planes[2];
  bool m_hdrGraphics = false;
  BLURAY_CLIP_INFO* m_clip = nullptr;
  int sent = 0;
  void SendMenuOverlays(int64_t) { ++sent; }
  void MatchGraphicsDynamicRange(SOverlays& overlays) const MATCH
  void UpdateGraphicsDynamicRange() UPDATE
};

int main()
{
  BLURAY_STREAM_INFO sdr{BLURAY_DYNAMIC_RANGE_SDR}, hdr10{BLURAY_DYNAMIC_RANGE_HDR10},
      dv{BLURAY_DYNAMIC_RANGE_DOLBY_VISION};
  BLURAY_CLIP_INFO sdrClip{1, &sdr}, hdr10Clip{1, &hdr10}, dvClip{1, &dv}, noVideo{0, nullptr};
  assert(!IsHdrGraphicsClip(sdrClip) && IsHdrGraphicsClip(hdr10Clip) && IsHdrGraphicsClip(dvClip));
  assert(!IsHdrGraphicsClip(noVideo));
  BLURAY_STREAM_INFO reserved{0xff};
  assert(!IsHdrGraphicsClip({1, &reserved}));

  CDVDInputStreamBluray stream;
  // A BD-J page drawn before any play item, already sent, and an HDMV page with its palette.
  auto page = std::make_shared<CDVDOverlayImage>();
  auto hdmv = std::make_shared<CDVDOverlayImage>();
  hdmv->palette = {0xff102040u};
  hdmv->alternatePalette = {0xff12213du};
  stream.m_planes[1].o = stream.m_planes[1].committed = {page, hdmv};

  // No play item: nothing is known, nothing changes.
  stream.UpdateGraphicsDynamicRange();
  assert(!stream.m_hdrGraphics && stream.sent == 0);

  // An HDR play item: the page is sent again as PQ, as a copy. What was sent stays untouched.
  stream.m_clip = &dvClip;
  stream.UpdateGraphicsDynamicRange();
  assert(stream.m_hdrGraphics && stream.sent == 1 && !page->m_isHDROverlay);
  for (const auto* list : {&stream.m_planes[1].o, &stream.m_planes[1].committed})
  {
    assert(list->front() != page && list->front()->m_isHDROverlay);
    assert(list->back() != hdmv && list->back()->m_isHDROverlay && !hdmv->m_isHDROverlay);
    assert(list->back()->palette == hdmv->alternatePalette);
  }

  // The same dynamic range again: no resend.
  stream.m_clip = &hdr10Clip;
  stream.UpdateGraphicsDynamicRange();
  assert(stream.sent == 1);

  // A page the disc draws now is flagged when flushed.
  auto later = std::make_shared<CDVDOverlayImage>();
  CDVDInputStreamBluray::SOverlays drawn{later};
  stream.MatchGraphicsDynamicRange(drawn);
  assert(drawn.front()->m_isHDROverlay && !later->m_isHDROverlay);

  // Back to SDR video, with nothing on screen: the flag follows and nothing is sent.
  stream.m_planes[1] = {};
  stream.m_clip = &sdrClip;
  stream.UpdateGraphicsDynamicRange();
  assert(!stream.m_hdrGraphics && stream.sent == 1);
}
'''

PQ_PIXELS_PROGRAM = r'''
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <random>
#include <vector>
#define PIXEL_ASHIFT 24
#define PIXEL_RSHIFT 16
#define PIXEL_GSHIFT 8
#define PIXEL_BSHIFT 0
namespace OVERLAY {
namespace {
HELPERS
}
void ConvertPQPaletteToSRGB(std::vector<uint32_t>& palette) CONVERT
void PreparePQPixels(std::vector<uint32_t>& pixels, unsigned outputState) PREPARE
}
using namespace OVERLAY;

uint32_t argb(int a, int r, int g, int b) { return uint32_t(a) << 24 | r << 16 | g << 8 | b; }

int main()
{
  // A menu: transparency, the disc's 157/255 text, a translucent panel, and random art.
  std::vector<uint32_t> pixels{0, argb(255, 157, 157, 157), argb(110, 30, 34, 40),
                               argb(255, 157, 157, 157), argb(255, 255, 0, 0)};
  std::mt19937 random(7);
  for (int i = 0; i < 4000; ++i)
    pixels.push_back(random());

  // Kodi's full-range HDR output: the disc's code values go through untouched.
  auto same = pixels;
  PreparePQPixels(same, 0);
  assert(same == pixels);

  // SDR output: every pixel is what ConvertPQPaletteToSRGB makes of it as a palette entry.
  auto srgb = pixels;
  PreparePQPixels(srgb, 1);
  for (size_t i = 0; i < pixels.size(); ++i)
  {
    std::vector<uint32_t> entry{pixels[i]};
    ConvertPQPaletteToSRGB(entry);
    assert(srgb[i] == entry[0]);
  }
  // 157/255 PQ is about 283 nits, above the 203 nit reference white: sRGB white.
  assert(srgb[1] == argb(255, 255, 255, 255));

  // Limited range: straight alpha, so every texel takes the whole offset; alpha is kept.
  auto limited = pixels;
  PreparePQPixels(limited, 2);
  assert(limited[0] == argb(0, 16, 16, 16));
  assert(limited[4] == argb(255, 235, 16, 16));
  for (size_t i = 0; i < pixels.size(); ++i)
    for (int shift : {16, 8, 0})
    {
      const int code = (pixels[i] >> shift) & 0xff;
      assert(int((limited[i] >> shift) & 0xff) == 16 + (code * 219 + 127) / 255);
      assert((limited[i] >> 24) == (pixels[i] >> 24));
    }

  // Both: sRGB first, then the limited-range encode of the sRGB result.
  auto both = pixels;
  PreparePQPixels(both, 3);
  auto expected = srgb;
  PreparePQPixels(expected, 2);
  assert(both == expected);
}
'''


class BlurayMenuHDR(unittest.TestCase):
    def test_hdr_palettes_decode_with_bt2020_and_sdr_ones_as_before(self):
        source = (TREE / BLURAY).read_text()
        build_and_run(self, fill(PALETTE_PROGRAM, {
            'CLAMP': body(source, 'static uint8_t  clamp(double v)'),
            'BUILD_RGBA': body(source, 'static uint32_t build_rgba(const BD_PG_PALETTE_ENTRY &e, bool bt2020)'),
        }))

    def test_graphics_follow_the_play_item_and_a_shown_page_is_sent_again(self):
        source = (TREE / BLURAY).read_text()
        build_and_run(self, fill(DYNAMIC_RANGE_PROGRAM, {
            'IS_HDR_CLIP': body(source, 'static bool IsHdrGraphicsClip(const BLURAY_CLIP_INFO& clip)'),
            'MATCH': body(source, 'void CDVDInputStreamBluray::MatchGraphicsDynamicRange(SOverlays& overlays) const'),
            'UPDATE': body(source, 'void CDVDInputStreamBluray::UpdateGraphicsDynamicRange()'),
        }))

    def test_bdj_pixels_get_the_conversions_of_a_pq_palette(self):
        source = (TREE / UTILITY).read_text()
        helpers = re.search(r'namespace\n\{\n(constexpr float ST2084_m1.*?)\} // namespace', source, re.S)
        self.assertIsNotNone(helpers)
        build_and_run(self, fill(PQ_PIXELS_PROGRAM, {
            'HELPERS': helpers[1],
            'CONVERT': body(source, 'void ConvertPQPaletteToSRGB(std::vector<uint32_t>& palette)'),
            'PREPARE': body(source, 'void PreparePQPixels(std::vector<uint32_t>& pixels, unsigned outputState)'),
        }))

    def test_disc_graphics_carry_the_flag_into_the_pq_bitmap_route(self):
        source = (TREE / BLURAY).read_text()
        bdj = body(source, 'void CDVDInputStreamBluray::OverlayCallbackARGB(')
        flush = body(source, 'void CDVDInputStreamBluray::OverlayFlush(SPlane& updated, int64_t pts)')
        self.assertIn('overlay->m_isHDROverlay = m_hdrGraphics;', bdj)
        self.assertLess(flush.index('MatchGraphicsDynamicRange(updated.o);'),
                        flush.index('updated.committed = updated.o;'))
        playitem = source[source.index('case BD_EVENT_PLAYITEM:'):source.index('case BD_EVENT_CHAPTER:')]
        self.assertLess(playitem.index('m_clip = &m_titleInfo->clips[m_event.param];'),
                        playitem.index('UpdateGraphicsDynamicRange();'))
        # A PQ BD-J page is converted for its destination as a PQ palette is; others load as-is.
        texture = body((TREE / TEXTURE).read_text(),
                       'COverlayTextureGLES::COverlayTextureGLES(const CDVDOverlayImage& o, CRect& rSource)')
        self.assertIn('if (o.palette.empty() && m_isHDROverlay && m_paletteOutputState)', texture)
        self.assertIn('OVERLAY::PreparePQPixels(rgba, m_paletteOutputState);', texture)


if __name__ == '__main__':
    unittest.main()
