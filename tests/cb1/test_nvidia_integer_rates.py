"""Parse a CTA-only EDID with the real timing library of both driver branches."""
import subprocess
import tempfile
import unittest
from pathlib import Path
import test_nvidia_native_hdr as native_hdr


class NvidiaIntegerRates(unittest.TestCase):
    def test_cta_rates_include_fractional_and_integer_modes_on_both_stacks(self):
        program = r'''
#include "nvtiming.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static void checksum(NvU8* data) {
  unsigned sum=0; for(unsigned i=0;i<127;++i)sum+=data[i];
  data[127]=(NvU8)(-sum);
}
int main(void) {
  NvU8 edid[256]={0,255,255,255,255,255,255,0};
  edid[8]=0x4c;edid[9]=0x2d;edid[10]=1;edid[16]=1;edid[17]=36;
  edid[18]=1;edid[19]=4;edid[20]=0x80;edid[23]=120;
  for(unsigned i=38;i<54;i++)edid[i]=1;
  edid[126]=1;checksum(edid);
  edid[128]=2;edid[129]=3;edid[130]=8;
  edid[132]=0x43;edid[133]=93;edid[134]=95;edid[135]=16;checksum(edid+128);
  NVT_EDID_INFO info={0};
  assert(NvTiming_ParseEDIDInfo(edid,sizeof(edid),&info)==NVT_STATUS_SUCCESS);
  const unsigned fractional[]={23976,29970,59940};
  const unsigned integer[]={24000,30000,60000};
  const unsigned clocks[]={297000,297000,148500};
  for(unsigned c=0;c<3;c++) {
    unsigned old=0,twin=0;
    for(unsigned i=0;i<info.total_timings;i++) {
      const NVT_TIMING* t=&info.timing[i];
      if(t->HVisible!=(c==2?1920:3840)||t->VVisible!=(c==2?1080:2160))continue;
      if(t->etc.rrx1k==fractional[c])old++;
      if(t->etc.rrx1k==integer[c]) {twin++;assert(t->pclk1khz==clocks[c]);}
    }
    printf("rate=%u fractional=%u integer=%u\n",integer[c],old,twin);fflush(stdout);
    assert(old==1 && twin==1 && "CTA timing must retain its fractional and integer rate");
  }
}
'''
        for source in native_hdr.NvidiaNativeHdr.sources(self):
            with self.subTest(branch=str(source)), tempfile.TemporaryDirectory() as temporary:
                root=Path(temporary);(root/'test.c').write_text(program)
                timing=source/'src/common/modeset/timing'
                built=subprocess.run(['cc','-std=gnu11','-O1','-fsanitize=address,undefined',
                    '-I'+str(timing),'-I'+str(source/'src/common/inc'),
                    '-I'+str(source/'src/common/sdk/nvidia/inc'),str(root/'test.c'),
                    *map(str, sorted(timing.glob('*.c'))),'-lm','-o',str(root/'test')],
                    capture_output=True,text=True)
                self.assertEqual(built.returncode,0,built.stderr[-4000:])
                ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
                self.assertEqual(ran.returncode,0,ran.stdout+ran.stderr)


if __name__=='__main__':
    unittest.main()
