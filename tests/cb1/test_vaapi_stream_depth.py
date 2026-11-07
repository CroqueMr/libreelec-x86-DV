"""Run the shipped depth selection inside a real FFmpeg get_format callback."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class VAAPIStreamDepth(unittest.TestCase):
    def test_decoded_software_format_overrides_stale_inputstream_hint(self):
        tree = os.environ.get('KODI_NATIVE_SOURCE_TREE')
        prefix = os.environ.get('FFMPEG_TEST_PREFIX')
        if not tree or not prefix or not shutil.which('ffmpeg'):
            self.skipTest('requires patched Kodi, matched FFmpeg libraries and a VP9 encoder')
        source = (Path(tree)/'xbmc/cores/VideoPlayer/DVDCodecs/Video/VAAPI.cpp').read_text()
        begin = source.index('  m_vaapiConfig.bitDepth = avctx->bits_per_raw_sample;')
        end = source.index('  m_DisplayState = VAAPI_OPEN;', begin)
        selection = source[begin:end]
        program = r'''
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/pixdesc.h>
}
#include <cassert>
#include <cstdio>
static int selectedDepth(AVCodecContext* avctx) {
  struct {int bitDepth;} m_vaapiConfig{};
  SELECTION
  return m_vaapiConfig.bitDepth;
}
static unsigned callbacks;
static AVPixelFormat format(AVCodecContext* context, const AVPixelFormat* formats) {
  const AVPixFmtDescriptor* decoded = av_pix_fmt_desc_get(context->sw_pix_fmt);
  assert(decoded && !(decoded->flags & AV_PIX_FMT_FLAG_HWACCEL));
  assert(context->bits_per_raw_sample == 8 && decoded->comp[0].depth == 10);
  std::printf("hint=%d decoded=%d selected=%d\n", context->bits_per_raw_sample,
              decoded->comp[0].depth, selectedDepth(context));
  std::fflush(stdout);
  assert(selectedDepth(context) == 10 && "stale inputstream hint selected 8-bit VA surfaces");
  ++callbacks;
  for (; *formats != AV_PIX_FMT_NONE; ++formats) {
    const AVPixFmtDescriptor* desc = av_pix_fmt_desc_get(*formats);
    if (desc && !(desc->flags & AV_PIX_FMT_FLAG_HWACCEL)) return *formats;
  }
  return AV_PIX_FMT_NONE;
}
int main(int argc, char** argv) {
  assert(argc == 2);
  AVFormatContext* input = nullptr;
  assert(avformat_open_input(&input, argv[1], nullptr, nullptr) == 0);
  // InputStream supplies codec parameters without a normal file probe.
  AVCodecContext* codec = avcodec_alloc_context3(avcodec_find_decoder(AV_CODEC_ID_VP9));
  assert(codec && avcodec_parameters_to_context(codec, input->streams[0]->codecpar) == 0);
  codec->bits_per_raw_sample = 8;
  codec->get_format = format;
  codec->thread_count = 1;
  assert(avcodec_open2(codec, codec->codec, nullptr) == 0);
  AVPacket* packet = av_packet_alloc();
  AVFrame* frame = av_frame_alloc();
  unsigned frames = 0;
  while (av_read_frame(input, packet) == 0) {
    assert(avcodec_send_packet(codec, packet) == 0);
    while (avcodec_receive_frame(codec, frame) == 0) {++frames; av_frame_unref(frame);}
    av_packet_unref(packet);
  }
  assert(callbacks && frames);
  AVCodecContext fallback{};
  fallback.sw_pix_fmt = AV_PIX_FMT_NONE; fallback.pix_fmt = AV_PIX_FMT_YUV420P10;
  assert(selectedDepth(&fallback) == 10);
  fallback.sw_pix_fmt = AV_PIX_FMT_VAAPI; fallback.bits_per_raw_sample = 8;
  assert(selectedDepth(&fallback) == 8);
  for (auto sw : {AV_PIX_FMT_YUV420P, AV_PIX_FMT_YUV420P10, AV_PIX_FMT_YUV420P12}) {
    fallback.sw_pix_fmt = sw;
    assert(selectedDepth(&fallback) == av_pix_fmt_desc_get(sw)->comp[0].depth);
  }
  av_frame_free(&frame); av_packet_free(&packet); avcodec_free_context(&codec);
  avformat_close_input(&input);
}
'''.replace('SELECTION', selection).replace('#include <cstdio>', '#include <cstdio>\n#include <initializer_list>')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            encoded = subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                'testsrc2=size=64x64:rate=1', '-frames:v', '2', '-pix_fmt', 'yuv420p10le',
                '-c:v', 'libvpx-vp9', '-profile:v', '2', '-threads', '1', str(root/'vp9.mkv')],
                capture_output=True, text=True)
            self.assertEqual(encoded.returncode, 0, encoded.stderr)
            (root/'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                '-I'+str(Path(prefix)/'include'), str(root/'test.cpp'),
                '-L'+str(Path(prefix)/'lib'), '-lavformat', '-lavcodec', '-lavutil',
                '-o', str(root/'test')], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            ran = subprocess.run([str(root/'test'), str(root/'vp9.mkv')],
                                 capture_output=True, text=True)
            self.assertEqual(ran.returncode, 0, ran.stdout+ran.stderr)


if __name__ == '__main__':
    unittest.main()
