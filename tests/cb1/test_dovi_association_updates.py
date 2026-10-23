"""Catch reversed Matroska layers and missed side-data-only TS changes."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body
from test_mkv_dual_track import matroska
from test_dual_carriage import transport


class DoviAssociationUpdates(unittest.TestCase):
    def test_rpu_track_resolves_mkv_configuration_placement(self):
        packets = [b'\0\0\0\3\x26\1\xaa',
                   b'\0\0\0\3\x26\1\xbb\0\0\0\3\x7c\1\xcc']
        fixtures = [(f'{name}.mkv', matroska(2, configured=placement, packet_pair=packets), want)
                    for name, placement, want in [('el', {1}, True), ('bl', {0}, True),
                                                   ('both', {0, 1}, True), ('none', set(), False)]]
        fixtures += [('unrelated.mkv', matroska(3, 1), False),
                     ('no-rpu.mkv', matroska(2, 0), False)]
        self.run_probe(fixtures, False)

    def test_hevc_only_late_descriptor_rebuilds_once(self):
        # Keep both PIDs HEVC before the DV descriptor arrives: no codec change.
        self.run_probe([('late.ts', transport('late', hevc_el=True), True)], True)

    def run_probe(self, fixtures, late):
        runtime = os.environ.get('CB1_CARRIAGE_ROOT')
        compiler = os.environ.get('CB1_CARRIAGE_CXX')
        target = bool(runtime and compiler)
        prefix = os.environ.get('FFMPEG_TEST_PREFIX')
        if not target and not prefix:
            self.skipTest('Matched FFmpeg prefix or isolated production runtime required')
        runtime = Path(runtime) if target else None
        compiler = compiler if target else 'c++'
        source = (TREE/'xbmc/cores/VideoPlayer/DVDDemuxers/DVDDemuxFFmpeg.cpp').read_text()
        program_change = body(source, 'bool CDVDDemuxFFmpeg::IsProgramChange()')
        program = r'''
#define HAVE_DVBRIDGE 1
#include <cassert>
#include <climits>
#include <vector>
#include <array>
extern "C" {
#include <libavformat/avformat.h>
#include <libavutil/dovi_meta.h>
}
struct CDemuxStream {
 virtual ~CDemuxStream()=default;AVCodecID codec{};
 struct Extra {int size{};int GetSize()const{return size;}} extraData;
};
struct CDemuxStreamAudioFFmpeg:CDemuxStream {int iChannels{};};
struct Demux {
 AVFormatContext* m_pFormatContext{};
 unsigned m_program=0,m_newProgram=0,m_initialProgramNumber=UINT_MAX,m_streamsInProgram=0;
 int m_blurayEnhancement=-1;
 unsigned m_doviGroups=0;
 std::vector<CDemuxStream> cache;
 CDemuxStream* GetStream(unsigned i){return i<cache.size()?&cache[i]:nullptr;}
 bool IsProgramChange() BODY
 void Snapshot(){
  m_doviGroups=0;
  for(unsigned i=0;i<m_pFormatContext->nb_stream_groups;i++){
   const auto* g=m_pFormatContext->stream_groups[i];
   m_doviGroups += g->type==AV_STREAM_GROUP_PARAMS_DOLBY_VISION;
  }
 }
};
int main(int argc,char**argv){
 av_log_set_level(AV_LOG_QUIET);
 const bool late=atoi(argv[1]);
 for(int i=2;i<argc;i+=2){
  Demux d;auto*& f=d.m_pFormatContext;
  assert(avformat_open_input(&f,argv[i],nullptr,nullptr)==0);
  const bool want=atoi(argv[i+1]);
  if(late){
   assert(f->nb_programs==1 && f->nb_streams==2 && !f->nb_stream_groups);
   d.m_streamsInProgram=f->programs[0]->nb_stream_indexes;d.cache.resize(2);
   for(int j=0;j<2;j++){d.cache[j].codec=f->streams[j]->codecpar->codec_id;
     d.cache[j].extraData.size=f->streams[j]->codecpar->extradata_size;}
   d.Snapshot();assert(!d.IsProgramChange());
  }
  AVPacket* p=av_packet_alloc();assert(p);
  while(av_read_frame(f,p)==0){
   av_packet_unref(p);
   if(late && f->nb_stream_groups)break;
  }
  if(late){
   assert(f->nb_stream_groups==1);
   assert(d.IsProgramChange() && "HEVC side-data-only DV discovery must rebuild streams");
   d.Snapshot();assert(!d.IsProgramChange() && "Stable association must not rebuild repeatedly");
   d.m_program=UINT_MAX;
   d.m_doviGroups=0;
   assert(d.IsProgramChange() && "Late groups must be observed without an MPEG program");
   d.Snapshot();assert(!d.IsProgramChange());
  }else{
   avformat_find_stream_info(f,nullptr);
   assert((f->nb_stream_groups==1)==want);
   if(want){const auto* g=f->stream_groups[0];assert(g->nb_streams==2);
     const auto* el=g->streams[g->params.layered_video->el_index];
     assert(el->index==1 && "Actual RPU track is EL");
     const auto* sd=av_packet_side_data_get(el->codecpar->coded_side_data,
         el->codecpar->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF);
     assert(sd && "Copied EL config must survive FFmpeg stream probing");}
  }
  av_packet_free(&p);avformat_close_input(&f);
 }
}
'''.replace('BODY', program_change)
        with tempfile.TemporaryDirectory(dir=runtime/'tmp' if target else None) as temporary:
            root=Path(temporary);(root/'probe.cpp').write_text(program)
            extra=[] if target else ['-I'+str(Path(prefix)/'include'),'-L'+str(Path(prefix)/'lib'),
                                     '-fsanitize=address,undefined','-latomic','-pthread']
            compile_run=subprocess.run([compiler,'-std=c++20','-O2',*extra,str(root/'probe.cpp'),
                                        '-lavformat','-lavcodec','-lavutil','-o',str(root/'probe')],
                                       capture_output=True,text=True)
            self.assertEqual(compile_run.returncode,0,compile_run.stderr[-3000:])
            args=(['chroot',str(runtime),'/usr/lib/ld-linux-x86-64.so.2','--inhibit-cache',
                  '/'+str((root/'probe').relative_to(runtime))] if target else [str(root/'probe')])
            args += [str(int(late))]
            for name,data,want in fixtures:
                (root/name).write_bytes(data)
                args += ['/'+str((root/name).relative_to(runtime)) if target else str(root/name),str(int(want))]
            run=subprocess.run(args,capture_output=True,text=True,timeout=30)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr[-3000:])
