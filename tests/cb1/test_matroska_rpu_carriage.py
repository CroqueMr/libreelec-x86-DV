"""Execute the actual patched Matroska layer association, not a reimplementation."""
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from test_native_video_source import body

ROOT=Path(__file__).resolve().parents[2]

class MatroskaRpuCarriage(unittest.TestCase):
    def test_rpu_on_either_layer_keeps_the_base_and_enhancement_roles(self):
        archive=os.environ.get('FFMPEG_SOURCE_ARCHIVE')
        prefix=os.environ.get('FFMPEG_TEST_PREFIX')
        if not archive or not prefix:self.skipTest('Matched FFmpeg archive and libraries required')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'libavformat/matroskadec.c';source.parent.mkdir()
            with tarfile.open(archive) as tar:
                entry=next(m for m in tar if m.name.endswith('/libavformat/matroskadec.c'))
                source.write_bytes(tar.extractfile(entry).read())
            patch=ROOT/'projects/Generic/patches/ffmpeg/ffmpeg-9900-05-matroska-dovi-association.patch'
            applied=subprocess.run(['patch','-p1','--fuzz=0','--batch','-i',str(patch)],cwd=root,capture_output=True,text=True)
            self.assertEqual(applied.returncode,0,applied.stdout+applied.stderr)
            function=body(source.read_text(),'static int matroska_parse_dovi_streams(')
            program=r'''
extern "C" {
#include <libavformat/avformat.h>
#include <libavutil/dovi_meta.h>
}
#include <cassert>
#include <cstring>
#include <initializer_list>
struct Internal { int need_context_update; };
Internal* ffstream(AVStream* s) {static Internal state[4];assert(s->index<4);return &state[s->index];}
static int matroska_parse_dovi_streams(AVFormatContext* s,const AVPacket* pkt) BODY
int main() {
 for(int carrier : {0,1})for(int placement : {0,1,2})for(bool joined : {false,true}) {
  AVFormatContext* f=avformat_alloc_context();assert(f);
  for(int i=0;i<2;++i) {
   AVStream* st=avformat_new_stream(f,nullptr);assert(st);auto* cp=st->codecpar;
   cp->codec_type=AVMEDIA_TYPE_VIDEO;cp->codec_id=AV_CODEC_ID_HEVC;
   cp->width=i?1920:3840;cp->height=i?1080:2160;
   cp->extradata=(uint8_t*)av_mallocz(23+AV_INPUT_BUFFER_PADDING_SIZE);assert(cp->extradata);
   cp->extradata_size=23;cp->extradata[0]=1;cp->extradata[21]=3;
   if(placement==2||placement==i) {
    auto* sd=av_packet_side_data_new(&cp->coded_side_data,&cp->nb_coded_side_data,
        AV_PKT_DATA_DOVI_CONF,sizeof(AVDOVIDecoderConfigurationRecord),0);assert(sd);
    auto* dv=(AVDOVIDecoderConfigurationRecord*)sd->data;
    dv->dv_profile=7;dv->bl_present_flag=dv->el_present_flag=dv->rpu_present_flag=1;
   }
  }
  AVPacket* p=av_packet_alloc();assert(p&&av_new_packet(p,joined?23:14)==0);
  const uint8_t nal[]={0,0,0,3,0x26,1,0xaa,0,0,0,3,0x7c,1,0xcc};
  memcpy(p->data,nal,14);p->stream_index=carrier;
  if(joined) {
   const uint8_t wrapped[]={0,0,0,5,0x7e,1,0x26,1,0xbb};memcpy(p->data+14,wrapped,9);
   assert(matroska_parse_dovi_streams(f,p)==0&&!f->nb_stream_groups);
   av_packet_free(&p);avformat_free_context(f);continue;
  }
  assert(matroska_parse_dovi_streams(f,p)==0&&f->nb_stream_groups==1);
  const auto* group=f->stream_groups[0];
  assert(group->streams[group->params.layered_video->el_index]->index==1);
  assert(group->streams[1-group->params.layered_video->el_index]->index==0);
  assert(!memcmp(p->data,nal,14));
  av_packet_free(&p);avformat_free_context(f);
 }
}
'''.replace('BODY',function)
            (root/'probe.cpp').write_text(program)
            command=['c++','-std=c++20','-fsanitize=address,undefined','-I'+str(Path(prefix)/'include'),
                str(root/'probe.cpp'),'-L'+str(Path(prefix)/'lib'),'-lavformat','-lavcodec','-lavutil','-o',str(root/'probe')]
            compiled=subprocess.run(command,capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            executed=subprocess.run([str(root/'probe')],capture_output=True,text=True)
            self.assertEqual(executed.returncode,0,executed.stdout+executed.stderr)
