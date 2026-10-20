"""Exercise checked HDMI Forum extension counts in the shared sink parser."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_driver_policy import replacement
from test_native_video_source import TREE


class EdidExtensionCountTests(unittest.TestCase):
    def test_forum_override_preserves_checksums_and_declared_bounds(self):
        header = (TREE / 'xbmc/utils/DVBridgeEdid.h').read_text()
        self.assertEqual(header, replacement('include/drm/drm_dvbridge_edid.h'))
        program = r'''
#include <assert.h>
#include <string.h>
#include "edid.h"
static void checksum(unsigned char* block) {
 unsigned char sum=0; block[127]=0;
 for(int i=0;i<127;++i) sum+=block[i];
 block[127]=-sum;
}
static void prepare(unsigned char edid[512], unsigned version, bool override) {
 memset(edid,0,512);
 const unsigned char magic[8]={0,255,255,255,255,255,255,0};
 memcpy(edid,magic,8); edid[126]=override?1:2;
 unsigned char* cta=edid+128; cta[0]=2; cta[1]=3;
 unsigned pos=4;
 if(override) {cta[pos++]=0xe2; cta[pos++]=0x78; cta[pos++]=2;}
 unsigned len=version==0?21:11;
 cta[pos++]=0xe0|len;
 cta[pos]=1; cta[pos+1]=0x46; cta[pos+2]=0xd0;
 cta[pos+4]=(version<<5)|2; cta[pos+6]=2;
 cta[2]=pos+len;
 for(int i=0;i<4;++i) checksum(edid+128*i);
}
int main(void) {
 unsigned char edid[512];
 for(unsigned v=0;v<3;++v) {
   prepare(edid,v,false);
   assert(dvbridge_parse_edid(edid,384).status==DV_EDID_STANDARD);
   prepare(edid,v,true);
   struct dvbridge_sink_caps caps=dvbridge_parse_edid(edid,384);
   assert(caps.status==DV_EDID_STANDARD && caps.version==v);
   assert(dvbridge_parse_edid(edid,256).status==DV_EDID_INVALID);
   assert(dvbridge_parse_edid(edid,383).status==DV_EDID_INVALID);
   assert(dvbridge_parse_edid(edid,512).status==DV_EDID_INVALID);
   edid[300]^=1;
   assert(dvbridge_parse_edid(edid,384).status==DV_EDID_INVALID);
 }
 prepare(edid,2,true); edid[128+5]=0x77; checksum(edid+128);
 assert(dvbridge_parse_edid(edid,384).status==DV_EDID_INVALID);
 prepare(edid,2,true); edid[128+6]=0; checksum(edid+128);
 assert(dvbridge_parse_edid(edid,384).status==DV_EDID_INVALID);
 prepare(edid,2,true); memset(edid+128+7,0,edid[128+2]-7); checksum(edid+128);
 assert(dvbridge_parse_edid(edid,384).status==DV_EDID_NO_DV);
 prepare(edid,2,true); edid[128+7+1+6]=0; checksum(edid+128);
 assert(dvbridge_parse_edid(edid,384).status==DV_EDID_LLDV_ONLY);
 prepare(edid,2,false); edid[126]=1; checksum(edid);
 assert(dvbridge_parse_edid(edid,384).status==DV_EDID_INVALID);
 assert(dvbridge_parse_edid(edid,127).status==DV_EDID_INVALID);
 assert(dvbridge_parse_edid(NULL,0).status==DV_EDID_ABSENT);
}
'''
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'edid.h').write_text(header)
            (root / 'test.c').write_text(program)
            build = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                    str(root / 'test.c'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(build.returncode, 0, build.stderr)
            run = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
