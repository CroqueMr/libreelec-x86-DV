"""An unused NLQ cap must not reject a provably representable residual."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class MasterNLQBound(unittest.TestCase):
    def test_large_cap_with_zero_reachable_residual_is_exact_and_admitted(self):
        prefix=os.environ.get('FFMPEG_TEST_PREFIX')
        if not prefix:self.skipTest('Matched FFmpeg headers/library required')
        root=Path(__file__).resolve().parents[2]
        source=root/'CB1/src'
        program=r'''
#include <assert.h>
#include <libavutil/dovi_meta.h>
#include <libavutil/mem.h>
#include "cb1_master_reference.h"
int main(void){
 size_t bytes;AVDOVIMetadata*m=av_dovi_metadata_alloc(&bytes);assert(m);
 AVDOVIRpuDataHeader*h=av_dovi_get_header(m);
 h->bl_bit_depth=h->el_bit_depth=10;h->vdr_bit_depth=12;h->coef_log2_denom=23;
 AVDOVIDataMapping*map=av_dovi_get_mapping(m);
 AVDOVIColorMetadata*c=av_dovi_get_color(m);c->signal_eotf=65535;c->source_max_pq=3079;
 for(int i=0;i<9;i++)c->ycc_to_rgb_matrix[i]=c->rgb_to_lms_matrix[i]=(AVRational){i%4==0,1};
 for(int ch=0;ch<3;ch++){
  c->ycc_to_rgb_offset[ch]=(AVRational){0,1};
  AVDOVIReshapingCurve*r=&map->curves[ch];r->num_pivots=2;r->pivots[1]=1023;
  r->mapping_idc[0]=AV_DOVI_MAPPING_POLYNOMIAL;r->poly_order[0]=1;r->poly_coef[0][1]=8388608;
  map->nlq[ch].nlq_offset=ch?511:0;map->nlq[ch].vdr_in_max=8388608;
 }
 struct pl_cb1_dovi_reference out;
 assert(cb1_master_reference_map(&out,m,bytes,true)==CB1_MASTER_READY);
 assert(out.residual);
 for(int ch=0;ch<3;ch++){
  assert(out.nlq[ch].maximum==8388608&&out.nlq[ch].slope==0&&out.nlq[ch].threshold==0);
  assert(out.comp[ch].poly[0][1]==8388608);
 }
 assert(cb1_master_reference_map(&out,m,bytes,false)==CB1_MASTER_INVALID);
 map->nlq[0].linear_deadzone_threshold=8388480;
 assert(cb1_master_reference_map(&out,m,bytes,true)==CB1_MASTER_READY);
 assert(out.nlq[0].threshold==8388480);
 map->nlq[0].linear_deadzone_threshold++;
 /* Positive 16776962 >> 8 is still 65535; offset zero cannot go negative. */
 assert(cb1_master_reference_map(&out,m,bytes,true)==CB1_MASTER_READY);
 map->nlq[0].nlq_offset=1;
 assert(cb1_master_reference_map(&out,m,bytes,true)==CB1_MASTER_UNSUPPORTED);
 map->nlq[0].nlq_offset=0;
 map->nlq[0].linear_deadzone_threshold=8388608;
 assert(cb1_master_reference_map(&out,m,bytes,true)==CB1_MASTER_UNSUPPORTED);
 map->nlq[0].linear_deadzone_threshold=0;
 map->nlq[0].linear_deadzone_slope=8388608;
 assert(cb1_master_reference_map(&out,m,bytes,true)==CB1_MASTER_UNSUPPORTED);
 av_free(m);
}
'''
        env=dict(os.environ,PKG_CONFIG_PATH=prefix+'/lib/pkgconfig:'+os.environ.get('PKG_CONFIG_PATH',''))
        flags=subprocess.check_output(['pkg-config','--cflags','--libs','libavutil','libplacebo'],env=env,text=True).split()
        with tempfile.TemporaryDirectory() as tmp:
            folder=Path(tmp);(folder/'check.c').write_text(program)
            command=['cc','-std=c11','-O2','-ffunction-sections','-fdata-sections','-Wl,--gc-sections','-I'+str(source),str(folder/'check.c'),str(source/'cb1_master_reference.c'),str(source/'dvbridge_placebo.c'),str(source/'cb1_master_ipt.c'),'-o',str(folder/'check'),*flags,'-lm']
            built=subprocess.run(command,env=env,capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            run=subprocess.run([str(folder/'check')],env=env,capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
