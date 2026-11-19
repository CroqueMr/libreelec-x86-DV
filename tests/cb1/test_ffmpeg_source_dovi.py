"""Apply the pinned FFmpeg patch, execute its raw ownership helpers against libavutil."""
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from test_native_video_source import body


class RawSourceTests(unittest.TestCase):
    def test_av1_raw_retention_preserves_bytes_and_optional_failure(self):
        patch=Path(__file__).resolve().parents[2]/'CB1/patches/ffmpeg/ffmpeg-9900-03-source-dovi-raw.patch'
        self.assertTrue(patch.exists(),'AV1 raw source retention patch is missing')
        prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
        archive=Path(os.environ.get('FFMPEG_SOURCE_ARCHIVE',
            str(patch.parents[3]/'sources/ffmpeg/ffmpeg-9.0.tar.xz')))
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)
            with tarfile.open(archive) as source:
                for name in ('libavcodec/itut35.c','libavcodec/itut35.h','libavutil/frame.h'):
                    path=root/name; path.parent.mkdir(parents=True,exist_ok=True)
                    path.write_bytes(source.extractfile('ffmpeg-9.0/'+name).read())
            apply=subprocess.run(['patch','-p1','--fuzz=0','-i',str(patch)],cwd=root,capture_output=True,text=True)
            self.assertEqual(apply.returncode,0,apply.stdout+apply.stderr)
            self.assertNotIn('offset',apply.stdout)
            code=(root/'libavcodec/itut35.c').read_text()
            header=(root/'libavcodec/itut35.h').read_text()
            struct='struct FFITUTT35 '+body(header,'typedef struct FFITUTT35 {')+';'
            helper='static AVBufferRef *itut_t35_dovi_raw(const FFITUTT35 *itut_t35) '+body(code,'static AVBufferRef *itut_t35_dovi_raw(')
            attach='static void itut_t35_attach_dovi_raw(FFITUTT35Meta *metadata, AVFrame *frame) '+body(code,'static void itut_t35_attach_dovi_raw(')
            metadata_attach='static int failed_metadata_attach(FFITUTT35Meta& metadata,AVFrame* frame) { if(metadata.dovi) '+body(code,'if (metadata.dovi) {')+' return 0; }'
            program=r'''
#include <cstdint>
#include <cstring>
#include <cassert>
extern "C" {
#include <libavutil/frame.h>
#include <libavutil/buffer.h>
}
@@STRUCT@@
struct FFITUTT35Meta {AVBufferRef* dovi_raw;AVBufferRef* dovi{};};
bool allocationFails=false;
AVBufferRef* source_test_alloc(size_t size) {return allocationFails ? nullptr : av_buffer_alloc(size);}
#define av_buffer_alloc source_test_alloc
@@HELPER@@
#undef av_buffer_alloc
@@ATTACH@@
AVFrameSideData* fail_metadata(AVFrame*, AVFrameSideDataType, AVBufferRef*) {return nullptr;}
#define av_frame_new_side_data_from_buf fail_metadata
@@METADATA_ATTACH@@
#undef av_frame_new_side_data_from_buf
int main() {
 uint8_t payload[]={0x19,0,0,3,1,0x80};
 FFITUTT35 input{0xb5,0x3b,0x800,payload,sizeof(payload)};
 auto* raw=itut_t35_dovi_raw(&input); assert(raw && raw->size==13);
 const uint8_t expected[]={0xb5,0,0x3b,0,0,8,0,0x19,0,0,3,1,0x80};
 assert(!std::memcmp(raw->data,expected,sizeof(expected)));
 std::memset(payload,0xff,sizeof(payload)); assert(!std::memcmp(raw->data,expected,sizeof(expected)));
 FFITUTT35Meta metadata{raw}; auto* frame=av_frame_alloc();
 itut_t35_attach_dovi_raw(&metadata,frame); assert(!metadata.dovi_raw);
 const auto* sd=av_frame_get_side_data(frame,AV_FRAME_DATA_DOVI_RPU_BUFFER);
 assert(sd && sd->size==sizeof(expected) && !std::memcmp(sd->data,expected,sizeof(expected)));
 av_frame_free(&frame);
 allocationFails=true; assert(!itut_t35_dovi_raw(&input)); allocationFails=false;
 input.payload_size=1024*1024; assert(!itut_t35_dovi_raw(&input));
 input.payload_size=0; assert(!itut_t35_dovi_raw(&input));
 input.payload_size=6; input.provider_code=0x3c; assert(!itut_t35_dovi_raw(&input));
 auto* retained=av_buffer_alloc(8); assert(retained);
 FFITUTT35Meta failed{av_buffer_ref(retained),av_buffer_alloc(8)};
 assert(av_buffer_get_ref_count(retained)==2);
 assert(failed_metadata_attach(failed,nullptr)<0);
 assert(!failed.dovi && !failed.dovi_raw && av_buffer_get_ref_count(retained)==1);
 av_buffer_unref(&retained);
}
'''.replace('@@STRUCT@@',struct).replace('@@HELPER@@',helper).replace('@@ATTACH@@',attach).replace('@@METADATA_ATTACH@@',metadata_attach)
            (root/'test.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',
                '-I'+str(prefix/'include'),str(root/'test.cpp'),'-L'+str(prefix/'lib'),
                '-lavutil','-lm','-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr[-5000:])
            run=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr[-5000:])


if __name__=='__main__': unittest.main()
