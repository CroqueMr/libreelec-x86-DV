"""Run the shipped FFmpeg NAL view and extension boundary, without film fixtures."""
import os
from pathlib import Path
import re
import subprocess
import tarfile
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[2]

class DoviRpuPadding(unittest.TestCase):
    def test_zero_padding_and_real_cm4_extension_boundary(self):
        archive=os.environ.get('FFMPEG_SOURCE_ARCHIVE')
        if not archive:self.skipTest('Pinned FFmpeg source archive required')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'libavcodec/dovi_rpudec.c';source.parent.mkdir()
            with tarfile.open(archive) as tar:
                entry=next(m for m in tar if m.name.endswith('/libavcodec/dovi_rpudec.c'))
                source.write_bytes(tar.extractfile(entry).read())
            patch=ROOT/'projects/Generic/patches/ffmpeg/ffmpeg-9900-00-libavcodec__dovi_rpudec.c.patch'
            result=subprocess.run(['patch','-p1','--fuzz=0','--batch','-i',str(patch)],cwd=root,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            text=source.read_text()
            start=text.index('        /* NAL unit with prefix and trailing zeroes */')
            branch=text[start:text.index('\n    }',start)]
            predicate=re.search(r'if \((get_bits_left\(gb\) [^\n]+?)\) \{\n\s+if \(\(ret = parse_ext_blocks\(s, gb, 2,',text)[1]
            program=r'''
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <string.h>
#define VALIDATE(v,lo,hi) do { if((v)<(lo)||(v)>(hi)) return -1; } while(0)
static int length(const uint8_t* rpu,size_t rpu_size) {
 if(rpu_size<5)return -1;
 BRANCH
 return rpu_size;
}
static int cm4(int left) {return PREDICATE;}
int main(void) {
 uint8_t rpu[40]={25,8,0x12,0x34,0x80},before[40];
 memcpy(before,rpu,sizeof(rpu));
 for(int padding=0;padding<=32;++padding)assert(length(rpu,5+padding)==4);
 assert(!memcmp(before,rpu,sizeof(rpu))); /* original raw RPU is never rewritten */
 for(int n=0;n<5;++n)assert(length(rpu,n)<0);
 uint8_t zero[40]={0};assert(length(zero,40)<0);
 for(int bits=40;bits<52;++bits)assert(!cm4(bits));
 for(int bits=52;bits<=80;++bits)assert(cm4(bits));
}
'''.replace('BRANCH',branch).replace('PREDICATE',predicate.replace('get_bits_left(gb)','left'))
            (root/'test.c').write_text(program)
            compiled=subprocess.run(['cc','-std=c11','-fsanitize=address,undefined',str(root/'test.c'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            executed=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(executed.returncode,0,executed.stdout+executed.stderr)
