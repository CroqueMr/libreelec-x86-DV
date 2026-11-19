"""Run the Print Screen writer and its color converter using the matched FFmpeg."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_native_video_source import TREE, body


class PrintScreen(unittest.TestCase):
    def test_composite_png_uses_display_srgb_for_verified_hdr(self):
        prefix = os.environ.get("FFMPEG_TEST_PREFIX")
        if not prefix:
            self.skipTest("Matched FFmpeg required")
        source = (TREE / "xbmc/utils/Screenshot.cpp").read_text()
        program = r'''
#include "rendering/capture/CaptureConvert.h"
#include "rendering/capture/CaptureTypes.h"
#include <cassert>
#include <cmath>
#include <cstring>
#include <memory>
#include <string>
extern "C" {
#include <libavutil/csp.h>
}
using namespace KODI::RENDERING::CAPTURE;
enum { XB_FMT_UNKNOWN, XB_FMT_A8R8G8B8, XB_FMT_RGBA8, XB_FMT_RGBA16, XB_FMT_X2BGR10 };
constexpr unsigned XB_FMT_OPAQUE=0x100;
constexpr int LOGERROR=1;
struct CURL {static const std::string& GetRedacted(const std::string& v){return v;}};
struct CLog {template<class... Args> static void Log(Args...) {}};
struct CPicture {
  static inline int calls=0;
  static inline int transfer=-1, primaries=-1, range=-1;
  static inline unsigned format=0;
  static inline uint16_t top[6]{}, bottom[6]{};
  static inline uint16_t colorPatch[3]{};
  static bool CreateThumbnailFromSurface(const uint8_t* data, unsigned width, unsigned height,
                                        unsigned pitch, const std::string&, unsigned coding,
                                        const ImageColorMetadata& color) {
    assert(width==16 && height==8 && (coding & XB_FMT_OPAQUE));
    ++calls; transfer=color.transfer; primaries=color.primaries; range=color.range;
    format=coding & ~XB_FMT_OPAQUE;
    const auto* end=data+static_cast<int>(pitch)*static_cast<int>(height-1);
    for (unsigned i=0;i<6;++i) {
      if (format==XB_FMT_RGBA16) {
        std::memcpy(&top[i],data+8*i+2,2);
        std::memcpy(&bottom[i],end+8*i+2,2);
      } else {
        top[i]=257*data[4*i+1];
        bottom[i]=257*end[4*i+1];
      }
    }
    for (unsigned c=0;c<3;++c) {
      if (format==XB_FMT_RGBA16)
        std::memcpy(&colorPatch[c],data+8*7+2*c,2);
      else
        colorPatch[c]=257*data[4*7+2-c];
    }
    return true;
  }
};
unsigned int CaptureXbFormat(AVPixelFormat format) XFORMAT
void WriteCapture(const CaptureResult& result, const std::string& filename, bool displaySDR) WRITER
static double PQ(double nits) {
  const auto n=std::pow(nits/10000.0,2610.0/16384.0);
  return std::pow((3424.0/4096+(2413.0/128)*n)/(1+(2392.0/128)*n),2523.0/32);
}
static CaptureResult MakeHdr(AVPixelFormat format, bool limited=false,
                             bool brightOverlay=false, bool hlg=false) {
  CaptureResult frame;
  frame.width=16; frame.height=8; frame.format=format;
  frame.color={AVCOL_PRI_BT2020, hlg ? AVCOL_TRC_ARIB_STD_B67 : AVCOL_TRC_SMPTE2084,
               limited ? AVCOL_RANGE_MPEG : AVCOL_RANGE_JPEG};
  const unsigned bytes=format==AV_PIX_FMT_RGBA64LE ? 8 : 4;
  frame.stride=-static_cast<int>(bytes*frame.width+32);
  auto pixels=std::make_unique<uint8_t[]>(static_cast<unsigned>(-frame.stride)*frame.height+64);
  const double levels[]={0,18,50,100,hlg ? 203.0 : 400.0,1000};
  const auto encodeHLG=av_csp_itu_eotf_inv(AVCOL_TRC_ARIB_STD_B67);
  for (unsigned y=0; y<frame.height; ++y) {
    auto* row=pixels.get()+y*static_cast<unsigned>(-frame.stride);
    for (unsigned x=0; x<frame.width; ++x) {
      const double nits=x>=6 ? (brightOverlay ? 4000 : 100) :
                              (y==frame.height-1 ? levels[x] : levels[x]*.5);
      double encoded[]={PQ(nits),PQ(nits),PQ(nits)};
      if (x==7) {encoded[0]=PQ(100);encoded[1]=PQ(50);encoded[2]=PQ(18);}
      if (hlg) {
        encoded[0]=encoded[1]=encoded[2]=std::min(nits,1000.0);
        encodeHLG(1000,0,encoded);
      }
      const double value=encoded[1];
      if (format==AV_PIX_FMT_RGBA64LE) {
        uint16_t rgba[4];
        for (unsigned c=0;c<3;++c)
          rgba[c]=static_cast<uint16_t>(
              std::lround(limited ? 4096+56064*encoded[c] : 65535*encoded[c]));
        rgba[3]=65535;
        std::memcpy(row+8*x,rgba,sizeof(rgba));
      } else if (format==AV_PIX_FMT_X2BGR10LE) {
        const uint32_t code=std::lround(limited ? 64+876*value : 1023*value);
        const uint32_t packed=code | (code<<10) | (code<<20) | (3u<<30);
        std::memcpy(row+4*x,&packed,sizeof(packed));
      } else {
        row[4*x]=row[4*x+1]=row[4*x+2]=std::lround(255*value);
        row[4*x+3]=255;
      }
    }
  }
  frame.pixels=std::make_shared<CHeapCapturePixels>(std::move(pixels));
  return frame;
}
int main() {
  for (const auto format : {AV_PIX_FMT_RGBA, AV_PIX_FMT_X2BGR10LE, AV_PIX_FMT_RGBA64LE}) {
    const bool limited=format==AV_PIX_FMT_X2BGR10LE;
    const auto input=MakeHdr(format,limited);
    WriteCapture(input,"print.png",true);
    assert(CPicture::transfer==AVCOL_TRC_IEC61966_2_1 &&
           CPicture::primaries==AVCOL_PRI_BT709 && CPicture::range==AVCOL_RANGE_JPEG);
    assert(CPicture::format==(format==AV_PIX_FMT_RGBA ? XB_FMT_A8R8G8B8 : XB_FMT_RGBA16));
    assert(CPicture::top[0]<500 && CPicture::top[1]>CPicture::top[0]);
    assert(CPicture::bottom[3]<CPicture::top[3]); // signed, padded input stays upright
    assert(CPicture::top[2]>32000 && CPicture::top[3]>39000); // 50 and 100 nit patches
    assert(CPicture::top[4]>CPicture::top[3] && CPicture::top[5]>CPicture::top[4]);
    const auto neutral=CPicture::top[3];
    WriteCapture(MakeHdr(format,limited,true),"overlay.png",true);
    assert(CPicture::top[3]==neutral); // subtitle/OSD cannot change the movie exposure
  }
  auto hlg=MakeHdr(AV_PIX_FMT_RGBA64LE,false,false,true);
  WriteCapture(hlg,"hlg.png",true);
  assert(CPicture::transfer==AVCOL_TRC_IEC61966_2_1 && CPicture::top[4]>CPicture::top[3]);
  const auto diffuseWhite=CPicture::top[4]; // HLG 75% signal ~= 203 cd/m²
  assert(diffuseWhite>47000 && diffuseWhite<53000);
  hlg.color.transfer=AVCOL_TRC_SMPTE2084;
  WriteCapture(hlg,"pq-label-control.png",true);
  assert(CPicture::top[4]>diffuseWhite+5000);

  auto gamut=MakeHdr(AV_PIX_FMT_RGBA64LE);
  WriteCapture(gamut,"wide.png",true);
  const auto redFrom2020=CPicture::colorPatch[0];
  gamut.color.primaries=AVCOL_PRI_BT709;
  WriteCapture(gamut,"bt709.png",true);
  assert(redFrom2020>CPicture::colorPatch[0]+1000);

  auto native=MakeHdr(AV_PIX_FMT_RGBA64LE);
  WriteCapture(native,"native-pair.png",false);
  assert(CPicture::transfer==AVCOL_TRC_SMPTE2084 && CPicture::top[3]==std::lround(PQ(100)*65535));
  native.colorEncodingVerified=false;
  WriteCapture(native,"unverified.png",true);
  assert(CPicture::transfer==AVCOL_TRC_SMPTE2084 && CPicture::top[3]==std::lround(PQ(100)*65535));
  native.colorEncodingVerified=true;
  native.content=CaptureContent::VIDEO;
  WriteCapture(native,"video.png",true);
  assert(CPicture::transfer==AVCOL_TRC_SMPTE2084 && CPicture::top[3]==std::lround(PQ(100)*65535));
  native.content=CaptureContent::COMPOSITE;
  native.color={AVCOL_PRI_BT709,AVCOL_TRC_IEC61966_2_1,AVCOL_RANGE_JPEG};
  WriteCapture(native,"sdr.png",true);
  assert(CPicture::transfer==AVCOL_TRC_IEC61966_2_1 && CPicture::top[3]==std::lround(PQ(100)*65535));
}
'''
        program = program.replace("XFORMAT", body(source, "unsigned int CaptureXbFormat("))
        program = program.replace("WRITER", body(source, "void WriteCapture("))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "utils").mkdir()
            (root / "utils/log.h").write_text(
                "enum { LOGWARNING }; struct CLog { template<class... A> static void LogF(A...) {} };"
            )
            (root / "test.cpp").write_text(program)
            binary = root / "test"
            result = subprocess.run([
                "c++", "-std=c++20", "-I" + str(root), "-I" + str(TREE / "xbmc"),
                "-I" + prefix + "/include", str(root / "test.cpp"),
                str(TREE / "xbmc/rendering/capture/CaptureConvert.cpp"), "-L" + prefix + "/lib",
                "-lavutil", "-lswscale", "-o", str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
