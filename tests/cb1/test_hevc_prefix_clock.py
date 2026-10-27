"""A timestamp-free HEVC header must not hide the first timed picture's clock."""
import base64
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class HEVCPrefixClock(unittest.TestCase):
    def test_first_picture_uses_its_pes_clock_after_untimed_headers(self):
        prefix = os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:
            self.skipTest('Set FFMPEG_TEST_PREFIX to matched FFmpeg')
        packet = base64.b64decode('AAAAF0ABDAH//wQIAAADAJ+oAAADAAAeugJAAAAAJ0IBAQQIAAADAJ+oAAADAAAeoCCBBZbpKTC8BaAgAAADACAAAAMAIQAAAAZEAcBxgRIAAAALKAGt4NEXznMji4A=')
        header, picture = bytearray(), bytearray()
        offset = 0
        while offset < len(packet):
            size = int.from_bytes(packet[offset:offset+4], 'big')
            offset += 4
            nal = packet[offset:offset+size]
            (picture if (nal[0] >> 1) < 32 else header).extend(b'\0\0\0\1'+nal)
            offset += size
        array = lambda data: ','.join(map(str, data))
        program = r'''
#include <assert.h>
#include <string.h>
#include <libavcodec/avcodec.h>
enum {header_size=HEADER_SIZE,picture_size=PICTURE_SIZE};
static const unsigned char header[HEADER_SIZE+AV_INPUT_BUFFER_PADDING_SIZE]={HEADER};
static const unsigned char picture[PICTURE_SIZE+AV_INPUT_BUFFER_PADDING_SIZE]={PICTURE};
int main(void){
 const int64_t cases[][6]={
  {AV_NOPTS_VALUE,AV_NOPTS_VALUE,9000,8000,9000,8000},
  {5000,4000,9000,8000,5000,4000},
  {AV_NOPTS_VALUE,AV_NOPTS_VALUE,AV_NOPTS_VALUE,AV_NOPTS_VALUE,AV_NOPTS_VALUE,AV_NOPTS_VALUE},
  {5000,AV_NOPTS_VALUE,9000,8000,5000,AV_NOPTS_VALUE},
  {AV_NOPTS_VALUE,4000,9000,8000,AV_NOPTS_VALUE,4000},
  {AV_NOPTS_VALUE,AV_NOPTS_VALUE,9000,AV_NOPTS_VALUE,9000,AV_NOPTS_VALUE},
  {AV_NOPTS_VALUE,AV_NOPTS_VALUE,AV_NOPTS_VALUE,8000,AV_NOPTS_VALUE,8000},
  {AV_NOPTS_VALUE,AV_NOPTS_VALUE,0,0,0,0}};
 for(unsigned c=0;c<sizeof(cases)/sizeof(*cases);++c)for(int split=0;split<2;++split){
  const int64_t* clock=cases[c];
  AVCodecParserContext* parser=av_parser_init(AV_CODEC_ID_HEVC);
  AVCodecContext* codec=avcodec_alloc_context3(NULL);
  assert(parser && codec);codec->codec_id=AV_CODEC_ID_HEVC;
  unsigned char* output;int size;
  assert(av_parser_parse2(parser,codec,&output,&size,header,header_size,
      clock[0],clock[1],0)==header_size);
  assert(size==0);
  const int first=split?6:picture_size;
  unsigned char first_chunk[PICTURE_SIZE+AV_INPUT_BUFFER_PADDING_SIZE]={0};
  memcpy(first_chunk,picture,first);
  assert(av_parser_parse2(parser,codec,&output,&size,first_chunk,first,
      clock[2],clock[3],header_size)==first);
  assert(size==0);
  if(split){
   assert(av_parser_parse2(parser,codec,&output,&size,picture+first,picture_size-first,
       AV_NOPTS_VALUE,AV_NOPTS_VALUE,header_size+first)==picture_size-first);
   assert(size==0);
  }
  // A large PES is split across enough chunks to overwrite timestamp history.
  const unsigned char filler[8+AV_INPUT_BUFFER_PADDING_SIZE]={0,0,0,1,0x4c,1,0xff,0x80};
  for(int chunk=0;chunk<5;++chunk){
   assert(av_parser_parse2(parser,codec,&output,&size,filler,8,
       AV_NOPTS_VALUE,AV_NOPTS_VALUE,header_size+picture_size+chunk*8)==8);
   assert(size==0);
  }
  unsigned char* p=(unsigned char*)picture;int remaining=picture_size;
  while(remaining){
   int used=av_parser_parse2(parser,codec,&output,&size,p,remaining,12000,11000,
       header_size+picture_size+5*8);
   assert(used>=0);
   if(size){
    assert(parser->pts==clock[4] && "untimed header consumed or changed the actual picture PTS");
    assert(parser->dts==clock[5] && "untimed header consumed or changed the actual picture DTS");
    assert(size==header_size+picture_size+5*8);
    assert(!memcmp(output,header,header_size));
    assert(!memcmp(output+header_size,picture,picture_size));
    for(int chunk=0;chunk<5;++chunk)
     assert(!memcmp(output+header_size+picture_size+chunk*8,filler,8));
    p+=used;remaining-=used;
    break;
   }
   assert(used);p+=used;remaining-=used;
  }
  assert(size>0);
  while(remaining){
   int used=av_parser_parse2(parser,codec,&output,&size,p,remaining,12000,11000,
       header_size+picture_size+5*8);
   assert(used>0 && size==0);p+=used;remaining-=used;
  }
  av_parser_parse2(parser,codec,&output,&size,NULL,0,AV_NOPTS_VALUE,AV_NOPTS_VALUE,0);
  assert(size==picture_size && parser->pts==12000 && parser->dts==11000);
  assert(!memcmp(output,picture,picture_size));
  av_parser_close(parser);avcodec_free_context(&codec);
 }
}
'''.replace('HEADER_SIZE', str(len(header))).replace('PICTURE_SIZE', str(len(picture)))
        program = program.replace('HEADER', array(header)).replace('PICTURE', array(picture))
        with tempfile.TemporaryDirectory() as temporary:
            source, binary = Path(temporary)/'check.c', Path(temporary)/'check'
            source.write_text(program)
            built = subprocess.run(['cc', '-std=c11', '-I'+prefix+'/include', str(source),
                                    '-L'+prefix+'/lib', '-Wl,-rpath,'+prefix+'/lib',
                                    '-lavcodec', '-lavutil', '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            run = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
