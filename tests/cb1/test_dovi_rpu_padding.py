"""Run the shipped FFmpeg NAL view and extension boundary, without film fixtures."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

class DoviRpuPadding(unittest.TestCase):
    def test_zero_padding_and_real_cm4_extension_boundary(self):
        source=os.environ.get('FFMPEG_MATCHED_SOURCE')
        if not source:self.skipTest('Matched FFmpeg source required')
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            text=(Path(source)/'libavcodec/dovi_rpudec.c').read_text()
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


    @unittest.skipUnless(os.environ.get('FFMPEG_MATCHED_SOURCE') and os.environ.get('FFMPEG_TEST_PREFIX'),
                         'Matched FFmpeg source and libraries required')
    def test_aligned_rpu_padding_keeps_metadata_and_crc_checks(self):
        source = Path(os.environ['FFMPEG_MATCHED_SOURCE'])
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        program = r'''
#include "libavcodec/dovi_rpudec.c"
#undef NDEBUG
#include <assert.h>

static int parse(const uint8_t *rpu, size_t length, AVDOVIDataMapping *mapping)
{
    DOVIContext context = {0};
    const int result = ff_dovi_rpu_parse(&context, rpu, length, AV_EF_CRCCHECK | AV_EF_EXPLODE);
    if (result == 0) {
        assert(context.mapping);
        assert(context.header.bl_bit_depth == 10);
        *mapping = *context.mapping;
    }
    ff_dovi_ctx_unref(&context);
    return result;
}

int main(void)
{
    /* Synthetic 10-bit RPU with byte-aligned polynomial mapping, followed by
       the CRC and terminator. No film data. */
    const uint8_t body[] = {
        0x19, 0x08, 0x09, 0x08, 0x40, 0xe4, 0xd9, 0x41, 0x3c, 0x00,
        0xff, 0xe0, 0x07, 0xff, 0x00, 0x3f, 0xfe, 0xa0, 0x00, 0x40,
        0x00, 0x80, 0x03, 0x40, 0x00, 0x80, 0x01, 0xa0, 0x00, 0x40, 0x00,
    };
    uint8_t rpu[sizeof(body) + 6 + AV_INPUT_BUFFER_PADDING_SIZE] = {0};
    AVDOVIDataMapping baseline, padded;
    memcpy(rpu, body, sizeof(body));
    memcpy(rpu + sizeof(body), (uint8_t[]){0xe6, 0xc7, 0x71, 0xb5, 0x80}, 5);
    assert(parse(rpu, sizeof(body) + 5, &baseline) == 0);

    memcpy(rpu + sizeof(body), (uint8_t[]){0, 0x18, 0x5e, 0xde, 0xcb, 0x80}, 6);
    assert(parse(rpu, sizeof(body) + 6, &padded) == 0);
    assert(!memcmp(&baseline, &padded, sizeof(baseline)));
    rpu[sizeof(body) + 4] ^= 1;
    assert(parse(rpu, sizeof(body) + 6, &padded) == AVERROR_INVALIDDATA);
    rpu[sizeof(body) + 5] = 0x70;
    assert(parse(rpu, sizeof(body) + 6, &padded) == AVERROR_PATCHWELCOME);

    /* The leading zero belongs to the CRC in this unpadded RPU. */
    rpu[10] = 0x85;
    rpu[11] = 0x20;
    memcpy(rpu + sizeof(body), (uint8_t[]){0, 0xbf, 0xb7, 0x76, 0x80, 0}, 6);
    assert(parse(rpu, sizeof(body) + 5, &padded) == 0);

    /* Both candidate terminators are 0x80; the second CRC check decides. */
    rpu[10] = 0xb5;
    rpu[11] = 0x60;
    memcpy(rpu + sizeof(body), (uint8_t[]){0, 1, 0x9a, 0x12, 0x80, 0x80}, 6);
    assert(parse(rpu, sizeof(body) + 6, &padded) == 0);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            test = root / 'test.c'
            test.write_text(program, encoding='utf-8')
            binary = root / 'test'
            compiled = subprocess.run([
                'cc', '-std=c11', '-DHAVE_AV_CONFIG_H', '-I' + str(source),
                str(test), str(source / 'libavcodec/dovi_rpu.c'),
                str(source / 'libavcodec/golomb.c'), '-L' + str(prefix / 'lib'),
                '-lavcodec', '-lavutil', '-pthread', '-lm', '-o', str(binary),
            ], capture_output=True, text=True)
            self.assertEqual(compiled.returncode, 0, compiled.stderr)
            executed = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(executed.returncode, 0, executed.stderr)
