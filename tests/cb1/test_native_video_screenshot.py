"""Exercise the native video screenshot tap with a packed carrier and a logical readback."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class NativeVideoScreenshot(unittest.TestCase):
    def test_unscaled_logical_capture(self):
        xbmc = TREE / 'xbmc'
        blit = (xbmc / 'rendering/capture/CaptureBlit.cpp').read_text()
        renderer = (xbmc / 'cores/VideoPlayer/VideoRenderers/RenderManager.cpp').read_text()
        loop = body(renderer, 'void CRenderManager::ServiceVideoCaptures()')
        loop = loop[loop.rindex('for (const auto& request : requests)'):-1]
        bridge = (xbmc / 'cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        window = (xbmc / 'windowing/gbm/WinSystemGbmGLESContext.cpp').read_text()
        prepare = body(window, 'bool CWinSystemGbmGLESContext::RenderDVBridge(')
        refresh = prepare[prepare.index('  if (masterCapture)'):prepare.index('  const bool guiAvailable')]
        parts = [r'''
#include "rendering/capture/CaptureReadback.h"
#include "rendering/capture/CapturePixels.h"
#include "dvbridge_metadata_bounds.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
extern "C" {
#include <libavutil/imgutils.h>
#include <libavutil/mem.h>
}
#include <algorithm>
#include <cassert>
#include <cmath>
#include <memory>
#include <vector>
using namespace KODI::RENDERING::CAPTURE;
struct CRect { float x1,y1,x2,y2; float Width() const{return x2-x1;} float Height() const{return y2-y1;} };
struct CGraphicContext { int GetWidth() const{return 5;} int GetHeight() const{return 4;} };
struct Window { CGraphicContext gfx; CGraphicContext& GetGfxContext(){return gfx;} };
struct CServiceBroker { static Window* GetWinSystem(){static Window w; return &w;} };
namespace MathUtils { int round_int(float v){return std::lround(v);} }
enum class CaptureCadence { ONESHOT, CONTINUOUS };
enum class CaptureFormat { NATIVE, BGRA8 }; enum class CaptureContent { VIDEO, COMPOSITE, BOTH };
struct CaptureSpec { unsigned width=0,height=0; CaptureFormat format=CaptureFormat::NATIVE; CaptureCadence cadence=CaptureCadence::ONESHOT; CaptureContent content=CaptureContent::VIDEO; };
struct CaptureResult {
  std::shared_ptr<ICapturePixels> pixels; unsigned width=0,height=0; int stride=0;
  AVPixelFormat format=AV_PIX_FMT_NONE; int color=0, displayMetadata=0, lightMetadata=0;
  bool hasDisplayMetadata=false, hasLightMetadata=false; CaptureContent content=CaptureContent::VIDEO;
};
int GetOutputColorMetadata(Window&){return 1;}
enum dvbridge_mode { DVBRIDGE_MODE_MASTER_REFERENCE, HDR10, SDR, PLAYER_LED, ENHANCED };
static dvbridge_mode mode=DVBRIDGE_MODE_MASTER_REFERENCE;
static bool logical=true, masterIPT=false, valid=true, bottom=true;
static CDVMetadataBuffer metadata;
struct CDVBridgeGLES {
  unsigned invalidations=0;
  void InvalidateScreenshot() { ++invalidations; }
  static bool UsesMasterSourceCarrier(dvbridge_mode mode,bool masterIPT,const CDVMetadataBuffer& metadata) CARRIER
};
static unsigned bufferWidth=5; static int pitch=48;
static unsigned decodeReads=0, ordinaryReads=0;
namespace KODI::WINDOWING::GBM {
bool HasMasterVideoScreenshot(Window&){return logical && CDVBridgeGLES::UsesMasterSourceCarrier(mode,masterIPT,metadata);}
bool ReadDVBridgeScreenshot(Window&, ReadbackBuffer& b, bool videoOnly=false){
  assert(videoOnly);
  ++decodeReads;
  if(!valid)return false;
  b.width=bufferWidth; b.height=4; b.stride=bottom?-pitch:pitch; b.format=AV_PIX_FMT_RGBA64LE;
  b.pixels=std::make_unique<uint8_t[]>(192);
  for(int y=0;y<4;++y) for(int x=0;x<5;++x) b.pixels[(bottom?3-y:y)*48+x*8]=10*y+x;
  return true;
}
}
class CCaptureBlit {
public:
  bool Capture(const CRect&,const CaptureSpec&,CaptureResult&);
  bool Blit(const CRect&,unsigned,unsigned,CaptureFormat){++ordinaryReads;return true;}
  bool Read(CaptureResult& out){out.format=AV_PIX_FMT_RGBA;return true;}
};
struct Request {CaptureSpec spec;};
static bool fresh(const CaptureSpec& spec) {
  Request item{spec};
  struct {
    Request* r;
    std::vector<Request*> TakeActive(CaptureContent c) const {
      return r->spec.content==c || r->spec.content==CaptureContent::BOTH ?
          std::vector<Request*>{r} : std::vector<Request*>{};
    }
  } registry{&item};
  auto* capture=&registry;
  CDVBridgeGLES renderer; auto* m_dvBridge=&renderer;
  struct {struct {dvbridge_mode mode;} policy;} m_dvSelection{{mode}};
  struct { bool masterIPT; } preferences{masterIPT};
  const bool masterCapture=mode==DVBRIDGE_MODE_MASTER_REFERENCE && !capture->TakeActive(CaptureContent::COMPOSITE).empty();
  REFRESH
  return renderer.invalidations!=0;
}
struct Service {
  bool success=false, failed=false; CaptureResult last;
  void Complete(Request*,CaptureResult r){success=true;last=std::move(r);}
  void Fail(Request*){failed=true;}
};
'''.replace('CARRIER',body(bridge,'bool CDVBridgeGLES::UsesMasterSourceCarrier(')).replace('REFRESH',refresh)]
        fill = blit.index('void FillResult(')
        parts += [blit[blit.index('bool ClampToOutput('):fill],
                  blit[fill:blit.index('} // namespace', fill)],
                  'bool CCaptureBlit::Capture(const CRect& visible, const CaptureSpec& spec,'
                  ' CaptureResult& result)' + body(blit, 'bool CCaptureBlit::Capture(')]
        parts += [r'''
static Service run(CaptureSpec spec, CRect visible) {
  CCaptureBlit blit; auto* m_captureBlit=&blit; Service service;auto* captureService=&service;
  Request item{spec}; std::vector<Request*> requests{&item}; CaptureResult m_picture;
''', loop, r'''
  return service;
}
int main() {
  CRect crop{0.6f,0.6f,3.4f,2.7f};
  for(bool flip : {false,true}) {
    bottom=flip;
    auto r=run({},crop);
    assert(r.success && r.last.format==AV_PIX_FMT_RGBA64LE && !ordinaryReads);
    assert(r.last.width==2 && r.last.height==2 && r.last.stride==(bottom?-48:48));
    auto row=CaptureSrcRow0(r.last.pixels->Lock(),r.last.stride,r.last.height);
    assert(row[0]==11 && row[8]==12 && row[r.last.stride]==21 && row[r.last.stride+8]==22);
  }
  auto full=run({},{-2,-2,7,7}); assert(full.success && full.last.width==5 && full.last.height==4);
  assert(!run({},{2,1,2,3}).success && !ordinaryReads);
  valid=false; assert(run({},crop).failed && !ordinaryReads);
  CaptureSpec both; both.content=CaptureContent::BOTH;
  auto partial=run(both,crop);
  assert(!partial.success && !partial.failed); // The composite tap can still serve this request.
  valid=true; bufferWidth=4; assert(!run({},crop).success && !ordinaryReads); bufferWidth=5;
  pitch=8; assert(!run({},crop).success && !ordinaryReads); pitch=48;
  unsigned earlier=decodeReads;
  assert(run({2,3,CaptureFormat::NATIVE},crop).last.format==AV_PIX_FMT_RGBA);
  assert(run({0,0,CaptureFormat::BGRA8},crop).last.format==AV_PIX_FMT_RGBA);
  assert(run({0,0,CaptureFormat::NATIVE,CaptureCadence::CONTINUOUS},crop).last.format==AV_PIX_FMT_RGBA);
  assert(fresh({}) && !fresh({2,3,CaptureFormat::NATIVE}) &&
         !fresh({0,0,CaptureFormat::BGRA8}) && !fresh({0,0,CaptureFormat::NATIVE,CaptureCadence::CONTINUOUS}));
  for (auto other : {HDR10,SDR,PLAYER_LED,ENHANCED}) {
    mode=other; assert(!fresh({}) && run({},crop).last.format==AV_PIX_FMT_RGBA);
  }
  mode=DVBRIDGE_MODE_MASTER_REFERENCE; masterIPT=true;
  size_t size=0; auto* source=av_dovi_metadata_alloc(&size); assert(source);
  auto* color=av_dovi_get_color(source);
  color->signal_color_space=0; // YCC was converted to a different IPT carrier.
  assert(metadata.Assign(reinterpret_cast<const uint8_t*>(source),size));
  assert(!fresh({}) && run({},crop).last.format==AV_PIX_FMT_RGBA);
  color->signal_color_space=2; // An authored P5 IPT carrier stays in its source encoding.
  assert(metadata.Assign(reinterpret_cast<const uint8_t*>(source),size));
  assert(fresh({}) && run({},crop).last.format==AV_PIX_FMT_RGBA64LE);
  ++earlier; av_free(source);
  logical=false; assert(run({},crop).last.format==AV_PIX_FMT_RGBA);
  assert(decodeReads==earlier && ordinaryReads==9);
}
''']
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        with tempfile.TemporaryDirectory() as tmp:
            program = Path(tmp) / 'capture.cpp'
            program.write_text('\n'.join(parts))
            binary = Path(tmp) / 'capture'
            subprocess.run(['c++', '-std=c++20', '-DHAVE_DVBRIDGE', '-I'+str(xbmc),
                            '-I'+str(prefix/'include'), '-I'+str(Path(__file__).resolve().parents[2]/'CB1/src'), str(program), '-L'+str(prefix/'lib'),
                            '-lavutil', '-o', str(binary)], check=True)
            subprocess.run([str(binary)], check=True,
                           env=dict(os.environ, LD_LIBRARY_PATH=str(prefix/'lib')))
