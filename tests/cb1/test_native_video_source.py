"""Execute shipped source-label and library serialization code, without a renderer."""
from pathlib import Path
import subprocess
import tempfile
import unittest
import os

if not os.environ.get('KODI_NATIVE_SOURCE_TREE'):
    raise unittest.SkipTest('Set KODI_NATIVE_SOURCE_TREE to the patched Kodi tree')
TREE = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])

def body(text, signature):
    start = text.index('{', text.index(signature))
    depth = 1
    end = start + 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

class SourceTests(unittest.TestCase):
    def test_dv_configuration_wins_over_hdr_base_in_native_demux(self):
        code=body((TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text(),
                  'StreamHdrType CDVDDemuxFFmpeg::DetermineHdrType')
        program=r'''
#include <cassert>
extern "C" {
#include <libavformat/avformat.h>
#include <libavcodec/packet.h>
}
enum class StreamHdrType {HDR_TYPE_NONE,HDR_TYPE_HDR10,HDR_TYPE_HLG,HDR_TYPE_DOLBYVISION};
StreamHdrType determine(AVStream* pStream) BODY
int main() {
 AVStream source{}; AVCodecParameters parameters{}; source.codecpar=&parameters;
 AVStream* stream=&source;
 assert(determine(stream)==StreamHdrType::HDR_TYPE_NONE);
 stream->codecpar->color_trc=AVCOL_TRC_SMPTE2084;
 assert(determine(stream)==StreamHdrType::HDR_TYPE_HDR10);
 assert(av_packet_side_data_new(&stream->codecpar->coded_side_data,&stream->codecpar->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF,8,0));
 assert(determine(stream)==StreamHdrType::HDR_TYPE_DOLBYVISION);
 stream->codecpar->color_trc=AVCOL_TRC_ARIB_STD_B67;
 assert(determine(stream)==StreamHdrType::HDR_TYPE_DOLBYVISION);
 av_packet_side_data_free(&parameters.coded_side_data,&parameters.nb_coded_side_data);
}
'''.replace('BODY',code)
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to the sanitizer-built FFmpeg prefix')
        prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-I'+str(prefix/'include'),str(root/'test.cpp'),
                '-fsanitize=address,undefined','-L'+str(prefix/'lib'),'-lavcodec','-lavutil','-lm','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr[-3000:])
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

    def test_source_detail_never_contains_output_mode(self):
        text = (TREE/'xbmc/guilib/guiinfo/VideoGUIInfo.cpp').read_text()
        branch = text.split('    case VIDEOPLAYER_HDR_DETAIL:', 1)[1].split('    case VIDEOPLAYER_AUDIO_CODEC:', 1)[0]
        helper = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVPlaybackInfo.h').read_text()
        mapping = body((TREE/'xbmc/utils/StreamDetails.cpp').read_text(), 'std::string CStreamDetails::HdrTypeToString')
        serial = body((TREE/'xbmc/utils/StreamDetails.cpp').read_text(), 'void CStreamDetailVideo::Serialize')
        program = r'''
#include <cassert>
#include <map>
#include <string>
#include <variant>
#define HAVE_DVBRIDGE
HELPER
enum class StreamHdrType { HDR_TYPE_NONE, HDR_TYPE_HDR10, HDR_TYPE_HLG, HDR_TYPE_HDR10PLUS, HDR_TYPE_DOLBYVISION };
struct CStreamDetails { static std::string HdrTypeToString(StreamHdrType hdrType) MAPPING };
struct VideoInfo { StreamHdrType hdrType{}; std::string hdrDetail; } m_videoInfo;
namespace DVBRIDGE { struct StreamTelemetry { struct Result { unsigned output=9; }; static Result Read() {return {};} }; }
bool getLabel(std::string& value) { BRANCH }
std::string label() { std::string value; assert(getLabel(value)); return value; }
struct CVariant { std::map<std::string,std::variant<std::string,int,float>> values;
  auto& operator[](const char* key) {return values[key];} };
struct CLangCodeExpander { static std::string AsBcp47(const std::string& s) {return s;} };
struct CStreamDetailVideo {
 std::string m_strCodec, m_strStereoMode, m_strLanguage, m_strHdrType, m_strHdrDetail;
 float m_fAspect{}; int m_iHeight{},m_iWidth{},m_iDuration{},m_source{},m_version{};
 void Serialize(CVariant& value) const SERIAL
};
int main() {
  for(const char* detail : {"5", "7FEL", "7MEL", "8.1", "8.4"}) {
    m_videoInfo={StreamHdrType::HDR_TYPE_DOLBYVISION,detail};
    assert(label()==detail);
    CStreamDetailVideo library; library.m_strHdrType="dolbyvision"; library.m_strHdrDetail=detail;
    CVariant out; library.Serialize(out);
    assert(std::get<std::string>(out.values["hdrtype"])=="dolbyvision");
    assert(std::get<std::string>(out.values["hdrdetail"])==detail);
  }
  m_videoInfo={StreamHdrType::HDR_TYPE_HDR10,""}; assert(label().empty());
  assert(CStreamDetails::HdrTypeToString(m_videoInfo.hdrType)=="hdr10");
  m_videoInfo={StreamHdrType::HDR_TYPE_NONE,""}; assert(label().empty());
  assert(CStreamDetails::HdrTypeToString(m_videoInfo.hdrType).empty());
}
'''.replace('HELPER',helper).replace('MAPPING',mapping).replace('SERIAL',serial).replace('BRANCH',branch)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__': unittest.main()
