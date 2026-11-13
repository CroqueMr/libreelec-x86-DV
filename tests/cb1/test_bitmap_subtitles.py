"""Run the shipped native bitmap math with real Kodi geometry and source identity."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

from test_native_video_source import TREE, body


class BitmapSubtitles(unittest.TestCase):
    def test_pq_palette_destination_changes_rebuild_retained_native_cache(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRenderer.cpp').read_text()
        utility = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRendererUtil.cpp').read_text()
        header = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRenderer.h').read_text()
        program = r'''
#include <cassert>
#include <map>
#include <memory>
#include "cores/VideoPlayer/DVDSubtitles/BitmapSubtitles.h"
#include "cores/VideoPlayer/DVDCodecs/Overlay/DVDOverlayImage.h"
typedef struct ass_image ASS_Image;
struct CDVDOverlaySpu : CDVDOverlay { CDVDOverlaySpu():CDVDOverlay(DVDOVERLAY_TYPE_SPU) {} };
struct CDVDOverlayLibass : CDVDOverlay {
 CDVDOverlayLibass():CDVDOverlay(DVDOVERLAY_TYPE_SSA) {}
 void* GetLibassHandler() {return nullptr;}
};
namespace KODI::UTILS {enum class Eotf {TRADITIONAL_SDR,PQ};}
struct CWinSystemBase {
 virtual ~CWinSystemBase()=default;
 bool composite=true,limited=false,cb1=false;
 KODI::UTILS::Eotf eotf=KODI::UTILS::Eotf::PQ;
 bool IsHdrComposite() const {return composite;}
 bool UseLimitedColor() const {return limited;}
 auto GetEotf() const {return eotf;}
};
namespace KODI::WINDOWING::GBM {
 struct CWinSystemGbmGLESContext : CWinSystemBase {
  bool sdr=false;
  bool HasDVBridgeScreenshot() const {return cb1;}
  bool IsDVBridgeScreenshotSDR() const {return cb1 && sdr;}
 };
}
struct CServiceBroker {
 static inline KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
 static CWinSystemBase* GetWinSystem() {return &window;}
};
namespace OVERLAY {
struct SRenderState {float x,y,width,height;};
class COverlay OVERLAY_CLASS;
COverlay::COverlay() CONSTRUCTOR
COverlay::~COverlay()=default;
bool ShouldConvertPQPaletteToSRGB(bool isHDROverlay) SHOULD_CONVERT
OUTPUT_STATE_HELPER
struct Texture : COverlay {
 unsigned loadedState;
 Texture(const CDVDOverlayImage& image) {
  m_isHDROverlay=image.m_isHDROverlay;
  auto& window=CServiceBroker::window;
  loadedState=(ShouldConvertPQPaletteToSRGB(true)?1u:0u)|
              ((window.composite && window.limited && !window.cb1)?2u:0u);
  SET_CACHED_STATE
 }
 void Render(SRenderState&) override {}
};
std::shared_ptr<COverlay> COverlay::Create(const CDVDOverlayImage& image,CRect&) {
 return std::make_shared<Texture>(image);
}
std::shared_ptr<COverlay> COverlay::Create(const CDVDOverlaySpu&) {return nullptr;}
struct CRenderer {
 struct SElement {std::shared_ptr<CDVDOverlay> overlay_dvd;};
 std::map<unsigned,std::shared_ptr<COverlay>> m_textureCache;
 unsigned m_textureid=1;
 CRect m_rs;
 int m_subtitlePosition{},m_subtitlePosResInfo{};
 std::shared_ptr<COverlay> ConvertLibass(SElement&) {assert(false);return nullptr;}
 void Reset() RESET
 std::shared_ptr<COverlay> Convert(SElement& e) CONVERT
};
}
int main() {
 using namespace OVERLAY;
 CRenderer renderer;
 auto image=std::make_shared<CDVDOverlayImage>(); image->m_isHDROverlay=true;
 CRenderer::SElement entry{image};
 auto first=std::dynamic_pointer_cast<Texture>(renderer.Convert(entry));
 assert(first->loadedState==0);
 assert(renderer.Convert(entry)==first && "unchanged output reuses the native texture");
 // Configure calls Reset, not Flush. Retain the decoded subtitle and its texture id.
 CServiceBroker::window.composite=false;
 CServiceBroker::window.eotf=KODI::UTILS::Eotf::TRADITIONAL_SDR;
 renderer.Reset();
 auto sdr=std::dynamic_pointer_cast<Texture>(renderer.Convert(entry));
 assert(sdr->loadedState==1 && sdr!=first && "retained PQ palette needs SDR conversion");
 assert(renderer.Convert(entry)==sdr);
 CServiceBroker::window.composite=true;
 CServiceBroker::window.eotf=KODI::UTILS::Eotf::PQ;
 CServiceBroker::window.limited=true;
 renderer.Reset();
 auto limited=std::dynamic_pointer_cast<Texture>(renderer.Convert(entry));
 assert(limited->loadedState==2 && limited!=sdr);
 CServiceBroker::window.cb1=true;
 auto cb1=std::dynamic_pointer_cast<Texture>(renderer.Convert(entry));
 assert(cb1->loadedState==0 && cb1!=limited && "CB1 composition must not reuse pre-encoded limited PQ");
 assert(renderer.Convert(entry)==cb1);
 CServiceBroker::window.sdr=true;
 auto cb1SDR=std::dynamic_pointer_cast<Texture>(renderer.Convert(entry));
 assert(cb1SDR->loadedState==1 && cb1SDR!=cb1 && "CB1 SDR composite consumes an sRGB palette");
 assert(renderer.Convert(entry)==cb1SDR);
}
'''
        helper = ''
        if 'unsigned BitmapPaletteOutputState()' in utility:
            helper = 'unsigned BitmapPaletteOutputState()' + body(utility, 'unsigned BitmapPaletteOutputState()')
        replacements = {
            'OVERLAY_CLASS': body(header, 'class COverlay\n'),
            'CONSTRUCTOR': body(source, 'COverlay::COverlay()'),
            'SHOULD_CONVERT': body(utility, 'bool ShouldConvertPQPaletteToSRGB('),
            'OUTPUT_STATE_HELPER': helper,
            'SET_CACHED_STATE': 'm_paletteOutputState=loadedState;' if helper else '',
            'RESET': body(source, 'void CRenderer::Reset()'),
            'CONVERT': body(source, 'std::shared_ptr<COverlay> CRenderer::Convert(SElement& e)'),
        }
        for key, value in replacements.items():
            program = program.replace(key, value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'PlatformDefs.h').write_text('')
            (root / 'probe.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-DHAVE_DVBRIDGE=1', '-DHAS_GLES=3',
                                    '-fsanitize=address,undefined', '-I' + str(root),
                                    '-I' + str(TREE / 'xbmc'), str(root / 'probe.cpp'),
                                    '-o', str(root / 'probe')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root / 'probe')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_live_bitmap_cache_and_selected_picture_mvc_depth(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRenderer.cpp').read_text()
        header = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRenderer.h').read_text()
        if 'm_bitmapSettingsChanged.exchange(false)' not in source:
            self.fail('Native renderer does not consume live bitmap settings yet')
        program = r'''
#include <cassert>
#include <atomic>
#include <map>
#include <memory>
#include <optional>
#include "cores/VideoPlayer/DVDSubtitles/BitmapSubtitles.h"
using namespace KODI;
using namespace KODI::SUBTITLES;
typedef struct ass_image ASS_Image;
class CDVDOverlaySpu;
class CDVDOverlayImage;
enum class RenderStereoView {OFF,LEFT,RIGHT};
struct Resolution { int iSubtitles=1000; struct {int top=0;} Overscan; };
using RESOLUTION_INFO = Resolution;
struct Graphics {
 RenderStereoView view=RenderStereoView::LEFT;
 Resolution GetResInfo() {return {};}
 RenderStereoView GetStereoView() {return view;}
};
struct Window { Graphics gfx; Graphics& GetGfxContext() {return gfx;} };
struct SubtitleSettings { BitmapOptions options; BitmapOptions GetBitmapOptions() {return options;} };
struct SettingsComponent { SubtitleSettings subs; SubtitleSettings* GetSubtitlesSettings() {return &subs;} };
struct CServiceBroker {
 static inline Window window;
 static inline SettingsComponent settings;
 static Window* GetWinSystem() {return &window;}
 static SettingsComponent* GetSettingsComponent() {return &settings;}
};
namespace OVERLAY {
struct SRenderState {float x,y,width,height;};
class COverlay OVERLAY_CLASS;
COverlay::COverlay() OVERLAY_CONSTRUCTOR
COverlay::~COverlay() = default;
static unsigned dirty;
void MarkDirty() {++dirty;}
CRect BitmapOverlayRect(const COverlay* overlay, const SRenderState& state) RECT
struct CRenderer {
 CRect m_rs{0,0,1920,800},m_rd{0,140,1920,940},m_rv{0,0,1920,1080};
 CRect m_bitmapBounds{100,740,300,790};
 BitmapOptions m_bitmapOptions;
 std::atomic<bool> m_bitmapSettingsChanged{false};
 std::map<unsigned,std::shared_ptr<COverlay>> m_textureCache;
 std::optional<int> m_subtitlePlaneOffset{10};
 float SubtitleDepth() const DEPTH
 SRenderState ComputeBaseState(const COverlay* o) const BASE
 void Render(COverlay* o) RENDER
 void Update() {if (m_bitmapSettingsChanged.exchange(false)) UPDATE}
};
struct Recorded : COverlay {
 SRenderState drawn{};
 Recorded() {m_x=100;m_y=600;m_width=200;m_height=50;m_pos=POSITION_ABSOLUTE;m_align=ALIGN_VIDEO;}
 void Render(SRenderState& state) override {drawn=state;}
};
}
int main() {
 using namespace OVERLAY;
 CRenderer renderer;
 auto bitmap=std::make_shared<Recorded>(); bitmap->m_isBitmap=true;
 auto menu=std::make_shared<Recorded>(); menu->m_isBitmap=true;menu->m_source=DVDOverlaySource::MENU;
 auto text=std::make_shared<Recorded>();
 renderer.m_textureCache={{1,bitmap},{2,menu},{3,text}};
 renderer.Render(bitmap.get());
 assert(bitmap->drawn.x==110 && bitmap->drawn.y==740 && bitmap->drawn.width==200);
 CServiceBroker::settings.subs.options.zoom=200;
 CServiceBroker::settings.subs.options.placement=2;
 renderer.m_bitmapSettingsChanged=true;renderer.Update();
 assert(dirty==1 && renderer.m_textureCache.size()==3 && "geometry needs no GPU texture rebuild");
 renderer.Render(bitmap.get());
 assert(bitmap->drawn.x==10 && bitmap->drawn.y==148 && bitmap->drawn.width==400);
 CServiceBroker::window.gfx.view=RenderStereoView::RIGHT;
 renderer.Render(bitmap.get());
 assert(bitmap->drawn.x==-10 && "retain selected-picture MVC depth after bitmap geometry");
 renderer.Render(menu.get()); renderer.Render(text.get());
 assert(menu->drawn.x==90 && menu->drawn.y==740 && menu->drawn.width==200);
 assert(text->drawn.x==90 && text->drawn.y==740 && text->drawn.width==200);
 CServiceBroker::settings.subs.options.sdrBrightness=50;
 renderer.m_bitmapSettingsChanged=true;renderer.Update();
 assert(dirty==2 && renderer.m_textureCache.size()==2 && !renderer.m_textureCache.contains(1));
 assert(renderer.m_textureCache.at(2)==menu && renderer.m_textureCache.at(3)==text);
 CServiceBroker::settings.subs.options.authoring=2;
 renderer.m_bitmapSettingsChanged=true;renderer.Update();
 assert(dirty==2 && "authoring is decoder-latched, never falsely reinterpret cached RGB");
 renderer.Update(); assert(dirty==2);
}
'''
        replacements = {
            'OVERLAY_CLASS': body(header, 'class COverlay\n'),
            'OVERLAY_CONSTRUCTOR': body(source, 'COverlay::COverlay()'),
            'RECT': body(source, 'CRect BitmapOverlayRect('),
            'DEPTH': body(source, 'float CRenderer::SubtitleDepth() const'),
            'BASE': body(source, 'SRenderState CRenderer::ComputeBaseState('),
            'RENDER': body(source, 'void CRenderer::Render(COverlay* o)'),
            'UPDATE': body(source, 'if (m_bitmapSettingsChanged.exchange(false))'),
        }
        # GetStereoscopicDepth is the unchanged fallback when no per-picture offset exists.
        program = program.replace('namespace OVERLAY {', 'namespace OVERLAY {\nint GetStereoscopicDepth() {return 0;}', 1)
        for key, value in replacements.items():
            program = program.replace(key, value)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'probe.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    '-I' + str(TREE / 'xbmc'), str(root / 'probe.cpp'),
                                    '-o', str(root / 'probe')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root / 'probe')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_real_pgs_decoder_explicit_matrix_preserves_native_auto(self):
        prefix = os.environ.get('FFMPEG_PGS_TEST_PREFIX')
        if not prefix:
            self.skipTest('Set FFMPEG_PGS_TEST_PREFIX to the native PGS-enabled FFmpeg build')
        program = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include <libavcodec/avcodec.h>
#include <libavutil/dict.h>
static uint8_t packet[256];
static unsigned length;
static void segment(unsigned type, const uint8_t* bytes, unsigned size) {
  packet[length++]=type; packet[length++]=size>>8; packet[length++]=size;
  if(size) memcpy(packet+length,bytes,size);
  length+=size;
}
static uint32_t decode(const char* matrix) {
  const AVCodec* codec=avcodec_find_decoder(AV_CODEC_ID_HDMV_PGS_SUBTITLE);
  assert(codec);
  AVCodecContext* context=avcodec_alloc_context3(codec);
  assert(context);
  AVDictionary* options=NULL;
  if(matrix) av_dict_set(&options,"pgs_matrix",matrix,0);
  assert(avcodec_open2(context,codec,&options)==0);
  assert(av_dict_count(options)==0 && "explicit authoring requires an implemented decoder matrix option");
  av_dict_free(&options);
  AVPacket* input=av_packet_alloc();
  assert(input && av_new_packet(input,length)==0);
  memcpy(input->data,packet,length);
  AVSubtitle subtitle={0}; int got=0;
  assert(avcodec_decode_subtitle2(context,&subtitle,&got,input)>=0 && got);
  assert(subtitle.num_rects==1 && subtitle.rects[0]->nb_colors==256);
  uint32_t color=((uint32_t*)subtitle.rects[0]->data[1])[1];
  assert(subtitle.rects[0]->data[0][0]==1);
  avsubtitle_free(&subtitle); av_packet_free(&input); avcodec_free_context(&context);
  return color;
}
int main() {
  // A complete unencrypted PGS display set, not a mocked palette converter.
  const uint8_t presentation[]={0x07,0x80,0x04,0x38,0x10,0,0,0x80,0,0,1,0,0,0,0,0,0,0,0};
  const uint8_t palette[]={0,0,1,81,240,90,255};
  const uint8_t object[]={0,0,0,0xc0,0,0,12,0,2,0,2,1,1,0,0,1,1,0,0};
  segment(0x16,presentation,sizeof(presentation));
  segment(0x14,palette,sizeof(palette));
  segment(0x15,object,sizeof(object)); segment(0x80,NULL,0);
  // Hand-computed limited-range YCbCr matrix reference for Y=81, Cr=240, Cb=90.
  assert(decode(NULL)==0xffff1800u);
  assert(decode("auto")==0xffff1800u);
  assert(decode("bt709")==0xffff1800u);
  assert(decode("bt2020")==0xffff0a00u);
  packet[5]=0x02;packet[6]=0x40; // Native 576-line BT.601 heuristic remains unchanged.
  assert(decode(NULL)==0xfffe0000u);
  assert(decode("auto")==0xfffe0000u);
  assert(decode("bt709")==0xffff1800u);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'probe.c').write_text(program)
            built = subprocess.run(['cc', '-fsanitize=address,undefined', '-I' + prefix + '/include',
                                    str(root / 'probe.c'), '-L' + prefix + '/lib', '-lavcodec', '-lavutil',
                                    '-Wl,-rpath,' + prefix + '/lib', '-o', str(root / 'probe')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            environment = dict(os.environ, LD_LIBRARY_PATH=prefix + '/lib')
            run = subprocess.run([str(root / 'probe')], env=environment, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)

    def test_native_geometry_palette_and_menu_isolation(self):
        settings = ET.parse(TREE / 'system/settings/settings.xml').getroot()
        fields = {
            'authoring': 'bitmapauthoring', 'placement': 'bitmapplacement',
            'offset': 'bitmapoffset', 'zoom': 'bitmapzoom',
            'sdrBrightness': 'bitmapsdrbrightness', 'sdrSaturation': 'bitmapsdrsaturation',
            'hdrBrightness': 'bitmaphdrbrightness', 'hdrSaturation': 'bitmaphdrsaturation',
        }
        defaults = []
        for field, setting in fields.items():
            node = settings.find(".//setting[@id='subtitles." + setting + "']/default")
            self.assertIsNotNone(node, 'Native setting must exist: ' + setting)
            defaults.append('options.' + field + '=' + str(int(node.text)) + ';')
        utility = (TREE / 'xbmc/cores/VideoPlayer/VideoRenderers/OverlayRendererUtil.cpp').read_text()
        program = r'''
#include <cassert>
#include <vector>
#include "cores/VideoPlayer/DVDSubtitles/BitmapSubtitles.h"
#include "cores/VideoPlayer/DVDCodecs/Overlay/DVDOverlayImage.h"
#define PIXEL_ASHIFT 24
#define PIXEL_RSHIFT 16
#define PIXEL_GSHIFT 8
#define PIXEL_BSHIFT 0
using namespace KODI::SUBTITLES;
static uint32_t build_rgba(int a,int r,int g,int b,bool mergealpha) BUILD_RGBA
void convert_rgba(const CDVDOverlayImage& o,bool mergealpha,std::vector<uint32_t>& rgba,
                  const std::vector<uint32_t>* paletteOverride) CONVERT_RGBA
int main() {
  BitmapOptions options;
  XML_DEFAULTS
  CRect screen(0,0,1920,1080), video(0,140,1920,940), block(700,800,1220,900);
  const CRect line(700,800,1220,840);
  assert(BitmapRect(line,block,video,screen,options,DVDOverlaySource::SUBTITLE)==line);
  std::vector<uint32_t> palette;
  for (unsigned a=0;a<256;++a) palette.push_back((a<<24)|0x4080c0);
  auto original=palette;
  AdjustBitmapPalette(palette,false,options,DVDOverlaySource::SUBTITLE);
  assert(palette==original);
  AdjustBitmapPalette(palette,true,options,DVDOverlaySource::SUBTITLE);
  assert(palette==original && "neutral PQ must not round-trip or clamp authored peaks");
  options.zoom=200; options.placement=2; options.offset=0;
  auto top=BitmapRect(line,block,video,screen,options,DVDOverlaySource::SUBTITLE);
  assert(top.Width()==1040 && top.Height()==80 && top.y1==148);
  options.placement=3;
  auto bottom=BitmapRect(CRect(700,860,1220,900),block,video,screen,options,DVDOverlaySource::SUBTITLE);
  assert(bottom.y2==1072);
  options.offset=60;
  auto shifted=BitmapRect(line,block,video,screen,options,DVDOverlaySource::SUBTITLE);
  assert(shifted.y1>=0 && shifted.y2<=1080);
  assert(BitmapRect(line,block,video,screen,options,DVDOverlaySource::MENU)==line);
  options.sdrBrightness=0; options.hdrBrightness=0;
  AdjustBitmapPalette(palette,false,options,DVDOverlaySource::MENU);
  assert(palette==original);
  AdjustBitmapPalette(palette,false,options,DVDOverlaySource::SUBTITLE);
  for(unsigned a=0;a<256;++a) assert(palette[a]==a<<24);
  palette=original;
  AdjustBitmapPalette(palette,true,options,DVDOverlaySource::SUBTITLE);
  for(unsigned a=0;a<256;++a) assert(palette[a]==a<<24);
  options.sdrBrightness=100; options.hdrBrightness=100;
  options.sdrSaturation=0; options.hdrSaturation=0;
  for(bool pq:{false,true}) {
    palette=original;
    AdjustBitmapPalette(palette,pq,options,DVDOverlaySource::SUBTITLE);
    for(unsigned a=0;a<256;++a) {
      auto p=palette[a];
      assert((p>>24)==a);
      assert(((p>>16)&255)==((p>>8)&255) && ((p>>8)&255)==(p&255));
    }
  }
  // The shipped native upload expansion premultiplies only after customisation.
  CDVDOverlayImage image;
  image.width=2;image.height=1;image.linesize=2;image.pixels={0,1};
  image.palette={0x8000ff00u,0x004080c0u};
  std::vector<uint32_t> rgba(2);
  convert_rgba(image,true,rgba,nullptr);
  assert(rgba[0]==0x80008000u && rgba[1]==0 && "no alpha-zero RGB may leak into movie pixels");
  options.sdrBrightness=0;
  AdjustBitmapPalette(image.palette,false,options,DVDOverlaySource::SUBTITLE);
  convert_rgba(image,true,rgba,nullptr);
  assert(rgba[0]==0x80000000u && rgba[1]==0);
}
'''
        program = program.replace('XML_DEFAULTS', '\n'.join(defaults))
        program = program.replace('BUILD_RGBA', body(utility, 'static uint32_t build_rgba(int a,'))
        program = program.replace('CONVERT_RGBA', body(utility, 'void convert_rgba(const CDVDOverlayImage& o,'))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'PlatformDefs.h').write_text('')
            (root / 'probe.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    '-I' + str(root), '-I' + str(TREE / 'xbmc'), str(root / 'probe.cpp'),
                                    '-o', str(root / 'probe')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(root / 'probe')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)


if __name__ == '__main__':
    unittest.main()
