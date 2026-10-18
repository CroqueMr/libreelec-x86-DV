# SPDX-License-Identifier: MIT
"""Run decoder cadence accounting and the real MVC pairer/filter without a display."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

if not os.environ.get('KODI_NATIVE_SOURCE_TREE'):
    raise unittest.SkipTest('Set KODI_NATIVE_SOURCE_TREE to the patched Kodi tree')
TREE = Path(os.environ['KODI_NATIVE_SOURCE_TREE'])


def body(text, signature):
    start = text.index('{', text.index(signature))
    end, depth = start + 1, 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]

VIDEO = TREE / 'xbmc/cores/VideoPlayer/DVDCodecs/Video'


class MVCCadenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            raise unittest.SkipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        prefix = Path(os.environ.get('MVC_FFMPEG_TEST_PREFIX', os.environ['FFMPEG_TEST_PREFIX']))
        cls.temporary = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.temporary.cleanup)
        root = Path(cls.temporary.name)
        (root / 'cores').mkdir()
        (root / 'utils').mkdir()
        (root / 'cores/FFmpeg.h').write_text('#define FFMPEG_HAVE_MULTIVIEW 1\n')
        (root / 'utils/log.h').write_text(r'''
#pragma once
#include <string_view>
constexpr int LOGDEBUG=0, LOGINFO=1, LOGERROR=2;
struct CLog {
  static inline int lost{};
  template<class... T> static void Log(int, std::string_view message, T&&...) {
    if (message.find("lost diff") != message.npos) ++lost;
  }
};
''')
        source = (VIDEO / 'DVDVideoCodecFFmpeg.cpp').read_text()
        header = (VIDEO / 'DVDVideoCodecFFmpeg.h').read_text()
        control = 'struct CDropControl ' + body(header, 'struct CDropControl') + ' m_dropCtrl;'
        accounting = source.split('// here we got a frame\n', 1)[1]
        accounting = accounting.split('  if (m_pDecodedFrame->flags & AV_FRAME_FLAG_KEY)', 1)[0]
        functions = '\n'.join(signature + body(source, signature) for signature in (
            'CDVDVideoCodecFFmpeg::CDropControl::CDropControl()',
            'void CDVDVideoCodecFFmpeg::CDropControl::Reset(bool init)',
            'void CDVDVideoCodecFFmpeg::CDropControl::Process(int64_t pts, bool drop)',
            'CDVDVideoCodec::VCReturn CDVDVideoCodecFFmpeg::FilterProcess(AVFrame* frame)'))
        # Compile the same harness before and after introducing the accounting helper.
        helper = 'void CDVDVideoCodecFFmpeg::UpdateDropControl(int64_t pts)'
        if helper in source:
            functions += '\n' + helper + body(source, helper)
        program = r'''
#include <cassert>
#include <algorithm>
#include <cmath>
#include <cstring>
#include <deque>
#include <iostream>
#include <string>
#include "utils/log.h"
#include "MultiviewFramePairer.h"
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavfilter/buffersrc.h>
#include <libavfilter/buffersink.h>
#include <libavutil/mathematics.h>
}
constexpr int DVD_CODEC_CTRL_DRAIN=1;
class CDVDVideoCodec {
public: enum VCReturn {VC_ERROR, VC_BUFFER, VC_PICTURE};
};
class CDVDVideoCodecFFmpeg : public CDVDVideoCodec {
public:
  CONTROL
  bool m_multiview, m_interlaced{}, m_filterEof{};
  int m_droppedFrames{}, m_codecControlFlags{};
  bool m_started{};
  int m_iLastKeyframe{};
  struct {int fpsrate=24000, fpsscale=1001;} m_hints;
  AVCodecContext context{};
  AVCodecContext* m_pCodecContext=&context;
  AVFilterGraph* graph{};
  AVFilterContext *m_pFilterIn{}, *m_pFilterIn2{}, *m_pFilterOut{};
  AVFrame *m_pDecodedFrame=av_frame_alloc(), *m_pFilterFrame=av_frame_alloc();
  AVFrame* m_pFrame=av_frame_alloc();
  CMultiviewFramePairer m_multiviewPairer;
  std::string m_stereoMode="left_right";
  std::deque<std::pair<int64_t,int>> expected;
  int outputs{};
  explicit CDVDVideoCodecFFmpeg(bool mvc=true, bool rescale=false) : m_multiview(mvc) {
    context.skip_frame=AVDISCARD_DEFAULT;
    context.time_base={1,1000000};
    graph=avfilter_graph_alloc(); assert(graph); graph->nb_threads=1;
    auto create=[&](AVFilterContext** out,const char* filter,const char* name,const char* args) {
      assert(avfilter_graph_create_filter(out,avfilter_get_by_name(filter),name,args,nullptr,graph)==0);
    };
    const char* args="video_size=4x2:pix_fmt=8:time_base=1/1000000:pixel_aspect=1/1";
    create(&m_pFilterIn,"buffer","left",args);
    AVFilterContext* tail=m_pFilterIn;
    if (mvc) {
      create(&m_pFilterIn2,"buffer","right",args);
      create(&tail,"hstack","pair","inputs=2");
      assert(avfilter_link(m_pFilterIn,0,tail,0)==0);
      assert(avfilter_link(m_pFilterIn2,0,tail,1)==0);
      m_multiviewPairer.SetInputs(m_pFilterIn,m_pFilterIn2);
    }
    if (rescale) {
      AVFilterContext* clock{}; create(&clock,"settb","clock","expr=1/90000");
      assert(avfilter_link(tail,0,clock,0)==0); tail=clock;
    }
    create(&m_pFilterOut,"buffersink","output",nullptr);
    assert(avfilter_link(tail,0,m_pFilterOut,0)==0);
    assert(avfilter_graph_config(graph,nullptr)==0);
  }
  ~CDVDVideoCodecFFmpeg() {
    m_multiviewPairer.SetInputs(nullptr,nullptr);
    avfilter_graph_free(&graph);
    av_frame_free(&m_pDecodedFrame); av_frame_free(&m_pFilterFrame); av_frame_free(&m_pFrame);
  }
  void UpdateDropControl(int64_t pts);
  void AccountDecoded() { ACCOUNTING }
  VCReturn Startup() {
    m_pDecodedFrame->pict_type=AV_PICTURE_TYPE_I;
    if (!m_started) STARTUP return VC_PICTURE;
  }
  VCReturn FilterProcess(AVFrame* frame);
  void Accept(VCReturn result) {
    assert(result!=VC_ERROR);
    if (result==VC_PICTURE) {
      ++outputs;
      assert(m_pFrame->width==(m_multiview ? 8 : 4));
      assert(!expected.empty());
      const auto [pts,right]=expected.front(); expected.pop_front();
      if(pts!=AV_NOPTS_VALUE) {
        const auto outputPTS=av_rescale_q(m_pFrame->pts,av_buffersink_get_time_base(m_pFilterOut),context.time_base);
        assert(std::abs(outputPTS-pts)<=12);
      }
      for(int row=0;row<2;++row)
        for(int x=0;x<m_pFrame->width;++x)
          assert(m_pFrame->data[0][row*m_pFrame->linesize[0]+x]==(x<4 ? 10 : right));
    }
  }
  void View(int64_t pts, int eye=0) {
    av_frame_unref(m_pDecodedFrame);
    m_pDecodedFrame->format=AV_PIX_FMT_GRAY8;
    m_pDecodedFrame->width=4; m_pDecodedFrame->height=2;
    m_pDecodedFrame->pts=m_pDecodedFrame->best_effort_timestamp=pts;
    m_pDecodedFrame->sample_aspect_ratio={1,1};
    assert(av_frame_get_buffer(m_pDecodedFrame,0)==0);
    for(int row=0;row<2;++row) std::memset(m_pDecodedFrame->data[0]+row*m_pDecodedFrame->linesize[0],eye ? 200 : 10,4);
    if (m_multiview) {
      auto* sd=av_frame_new_side_data(m_pDecodedFrame,AV_FRAME_DATA_VIEW_ID,sizeof(int));
      assert(sd); std::memcpy(sd->data,&eye,sizeof(eye));
    }
    AccountDecoded(); Accept(FilterProcess(m_pDecodedFrame));
  }
  void Pair(int64_t pts, bool dependent=true) {
    expected.emplace_back(pts,dependent ? 200 : 10);
    View(pts); if(m_multiview && dependent) View(pts,1);
  }
  void Drain() {
    m_codecControlFlags=DVD_CODEC_CTRL_DRAIN; Accept(FilterProcess(nullptr));
    m_codecControlFlags=0;
    while(!m_filterEof) Accept(FilterProcess(nullptr));
  }
};
FUNCTIONS
int main(int argc,char** argv) {
  assert(argc==2); std::string test=argv[1];
  const bool mono=test=="mono" || test=="mono-drop", rescale=test=="clock";
  CDVDVideoCodecFFmpeg codec(!mono,rescale);
  auto pts=[](int i) {return int64_t(i)*1001000/24;};
  if(test=="startup") {
    codec.m_pDecodedFrame->pict_type=AV_PICTURE_TYPE_I;
    codec.m_iLastKeyframe=142; assert(codec.Startup()==codec.VC_BUFFER && !codec.m_started);
    codec.m_iLastKeyframe=143; assert(codec.Startup()==codec.VC_PICTURE && codec.m_started);
    for(int invalid : {0,-1}) {
      codec.m_started=false; codec.m_hints.fpsscale=invalid;
      codec.m_iLastKeyframe=299; assert(codec.Startup()==codec.VC_BUFFER);
      codec.m_iLastKeyframe=300; assert(codec.Startup()==codec.VC_PICTURE);
    }
    codec.m_started=false; codec.m_hints={60000,1001};
    codec.m_iLastKeyframe=300; assert(codec.Startup()==codec.VC_PICTURE);
    codec.m_started=false; codec.m_multiview=false; codec.m_hints={24000,1001};
    codec.m_iLastKeyframe=143; assert(codec.Startup()==codec.VC_BUFFER);
    codec.m_dropCtrl.m_state=codec.m_dropCtrl.VALID; codec.m_dropCtrl.m_diffPTS=41708;
    assert(codec.Startup()==codec.VC_PICTURE);
  } else if(test=="unknown") {
    codec.Pair(AV_NOPTS_VALUE); codec.Drain();
    assert(codec.outputs==1 && codec.m_dropCtrl.m_lastPTS==AV_NOPTS_VALUE && CLog::lost==0);
  } else if(test=="drop" || test=="mono-drop") {
    for(int i=0;i<40;++i) codec.Pair(pts(i));
    codec.context.skip_frame=AVDISCARD_NONREF;
    codec.Pair(pts(42)); codec.Pair(pts(43));
    assert(codec.m_droppedFrames==1);
  } else if(test=="discontinuity") {
    for(int i=0;i<40;++i) codec.Pair(pts(i));
    for(int i=0;i<40;++i) codec.Pair(pts(40)+int64_t(i)*33333);
    assert(CLog::lost>0); assert(codec.m_dropCtrl.m_diffPTS==33333);
  } else if(test=="seek") {
    for(int i=0;i<40;++i) codec.Pair(pts(i));
    codec.m_multiviewPairer.Reset(); codec.m_dropCtrl.Reset(false);
    for(int i=0;i<40;++i) codec.Pair(pts(i));
    assert(CLog::lost==0); assert(codec.m_dropCtrl.m_diffPTS>=41707 && codec.m_dropCtrl.m_diffPTS<=41709);
  } else if(test=="drain") {
    codec.expected.emplace_back(0,10); codec.View(0); assert(codec.outputs==0);
    codec.Drain(); assert(codec.outputs==1);
    assert(codec.m_dropCtrl.m_lastPTS==0);
  } else {
    int count=test=="cadence" ? 2160 : 60;
    for(int i=0;i<count;++i) codec.Pair(pts(i),test!="base-only" && !(test=="mixed" && i>=20 && i<40));
    codec.Drain();
    std::cout<<test<<": pictures="<<codec.outputs<<" lost_diff="<<CLog::lost
             <<" estimated_us="<<codec.m_dropCtrl.m_diffPTS<<std::endl;
    assert(codec.outputs==count);
    assert(CLog::lost==0);
    assert(codec.m_dropCtrl.m_state==codec.m_dropCtrl.VALID);
    assert(codec.m_dropCtrl.m_diffPTS>=41700 && codec.m_dropCtrl.m_diffPTS<=41720);
  }
}
'''.replace('CONTROL', control).replace('ACCOUNTING', accounting).replace('FUNCTIONS', functions)
        program = program.replace('STARTUP', body(source.split('// here we got a frame', 1)[1],
                                                  'if (!m_started)'))
        (root / 'test.cpp').write_text(program)
        cls.executable = root / 'test'
        command = ['c++', '-std=c++20', '-D__STDC_CONSTANT_MACROS',
                   '-fsanitize=address,undefined', '-g',
                   '-I'+str(root), '-I'+str(VIDEO), '-I'+str(prefix/'include'),
                   str(root/'test.cpp'), str(VIDEO/'MultiviewFramePairer.cpp'),
                   '-L'+str(prefix/'lib'), '-lavfilter', '-lavcodec', '-lavutil', '-lm',
                   '-pthread', '-o', str(cls.executable)]
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr)

    def test_mvc_temporal_cadence_and_non_regressions(self):
        for case in ('cadence', 'mono', 'base-only', 'mixed', 'clock', 'seek',
                     'drain', 'discontinuity', 'drop', 'mono-drop', 'startup', 'unknown'):
            with self.subTest(case=case):
                result = subprocess.run([str(self.executable), case], capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                print(result.stdout, end='')


if __name__ == '__main__':
    unittest.main()
