"""Decode references must survive the negotiated DV clip presentation cut."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class LibblurayVideoPreroll(unittest.TestCase):
    def test_native_filter_keeps_video_references_without_relaxing_other_cuts(self):
        include = os.environ.get('LIBBLURAY_TEST_INCLUDE')
        if not include:
            self.skipTest('Matched libbluray sources required')
        original = Path(include)
        repo = Path(__file__).resolve().parents[2]
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            for name in ('bluray.c', 'bluray.h', 'decoders/m2ts_filter.c', 'decoders/m2ts_filter.h'):
                target = folder / 'src/libbluray' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(original / 'libbluray' / name, target)
            patched = subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                str(repo/'packages/multimedia/libbluray/patches/0002-navigation-read-boundary.patch')],
                cwd=folder, capture_output=True, text=True)
            self.assertEqual(patched.returncode, 0, patched.stdout + patched.stderr)
            native = folder/'src/libbluray/decoders/m2ts_filter.c'
            source = native.read_text()
            signature = source.split('M2TS_FILTER *m2ts_filter_init(', 1)[1].split('{', 1)[0]
            extra = ', keep' if 'video_preroll' in signature else ''
            # Only logging is replaced; all filter state and transport code is native.
            source = source.replace('#include "util/logging.h"', '#define BD_DEBUG(...) ((void)0)')
            native.write_text(source)
            program = r'''
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "src/libbluray/decoders/m2ts_filter.c"
static M2TS_FILTER* create(int64_t in, int64_t out, int keep) {
    return m2ts_filter_init(in,out,1,1,1,1 EXTRA);
}
static unsigned pid(const uint8_t* p) {return ((p[5]&31)<<8)|p[6];}
static void pts(uint8_t* p, int64_t value) {
    p[0]=0x21|((value>>29)&14); p[1]=value>>22;
    p[2]=1|((value>>14)&254); p[3]=value>>7; p[4]=1|((value<<1)&254);
}
static void pes(uint8_t* p,unsigned id,int64_t time) {
    memset(p,0xff,192);p[4]=0x47;p[5]=0x40|(id>>8);p[6]=id;p[7]=0x10;
    p[8]=p[9]=0;p[10]=1;p[11]=0xe0;p[12]=p[13]=0;p[14]=0x80;p[15]=0x80;p[16]=5;
    pts(p+17,time);p[22]=p[23]=p[24]=0;p[25]=1;p[26]=0x28;p[27]=1;
}
static void blank(uint8_t* p) { for(int i=0;i<32;++i)pes(p+192*i,0x1fff,0); }
int main(void) {
    const int64_t in=655338900,out=655695506;
    const int64_t ref=655327638;
    uint8_t block[6144],before[6144];
    for(int keep=1;keep>=0;--keep) {
        M2TS_FILTER* f=create(in,out,keep);assert(f);
        blank(block);pes(block,0x1011,ref);pes(block+192,0x1015,ref);
        pes(block+384,0x1100,ref);pes(block+576,0x1200,ref);pes(block+768,0x1400,ref);
        memcpy(before,block,sizeof(block));assert(m2ts_filter(f,block)==0);
        assert(pid(block)==(keep?0x1011:0x1fff) && "DV IDR reference must survive before authored IN");
        if(keep)assert(!memcmp(block,before,192));
        assert(!memcmp(block+192,before+192,192));
        assert(pid(block+384)==0x1fff && pid(block+576)==0x1fff && pid(block+768)==0x1fff);
        // Real presentation reordering: one later PTS precedes two pre-IN PTS.
        blank(block);pes(block,0x1011,655357668);pes(block+192,0x1011,655335146);
        pes(block+384,0x1011,in);memcpy(before,block,sizeof(block));
        assert(m2ts_filter(f,block)==0);assert(!memcmp(block,before,sizeof(block)));
        // Seeking must preserve the same reference policy, without unmuting audio/PG/IG.
        m2ts_filter_seek(f,0,in);blank(block);pes(block,0x1011,ref);pes(block+192,0x1100,ref);
        assert(m2ts_filter(f,block)==0);assert(pid(block)==(keep?0x1011:0x1fff));assert(pid(block+192)==0x1fff);
        m2ts_filter_close(&f);assert(!f);
        // Historical OUT rules remain: video/audio inclusive, PG/IG exclusive.
        f=create(in,out,keep);blank(block);
        pes(block,0x1011,out);pes(block+192,0x1100,out);pes(block+384,0x1200,out);pes(block+576,0x1400,out);
        assert(m2ts_filter(f,block)==0);
        assert(pid(block)==0x1011&&pid(block+192)==0x1100);
        assert(pid(block+384)==0x1fff&&pid(block+576)==0x1fff);
        blank(block);pes(block,0x1011,out+1);pes(block+192,0x1100,out+1);
        assert(m2ts_filter(f,block)==0&&pid(block)==0x1fff&&pid(block+192)==0x1fff);
        m2ts_filter_close(&f);
    }
    // Transport timestamps are 33-bit; no narrowing at the signed-32 boundary.
    M2TS_FILTER* f=create((INT64_C(1)<<32)+100,(INT64_C(1)<<32)+200,1);
    blank(block);pes(block,0x1011,(INT64_C(1)<<32)+50);
    assert(m2ts_filter(f,block)==0&&pid(block)==0x1011);m2ts_filter_close(&f);
}
'''.replace(' EXTRA', extra)
            (folder/'test.c').write_text(program)
            result = subprocess.run(['cc', '-std=c11', '-fsanitize=address,undefined',
                '-I'+str(folder), '-I'+str(original),
                '-I'+str(original/'libbluray/decoders'), str(folder/'test.c'), '-o',str(folder/'test')],
                capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(folder/'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
