"""Execute the real Intel display owners against CPU register/connector fixtures."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched kernel required')
class IntelXe3Backports(unittest.TestCase):
    def source(self, name):
        return (Path(os.environ['CB1_KERNEL_SOURCE']) /
                'drivers/gpu/drm/i915/display' / name).read_text()

    def run_native(self, code):
        with tempfile.TemporaryDirectory() as directory:
            source, binary = Path(directory)/'check.c', Path(directory)/'check'
            source.write_text(code)
            result = subprocess.run(['cc', '-std=c11', '-Wall', '-Wextra', '-Werror',
                                     '-Wno-unused-parameter', '-Wno-unused-function',
                                     str(source), '-o', str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            result = subprocess.run([str(binary)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_gpio_write_only_masks_and_read_only_sampling(self):
        source = self.source('intel_gmbus.c')
        names = (['gpio_mask_bits', 'gpio_preserved_bits', 'gpio_read_reg']
                 if 'static u32 gpio_mask_bits(' in source else ['get_reserved'])
        owners = '\n'.join(function(source, name) for name in
                           names + ['get_clock', 'get_data', 'set_clock', 'set_data'])
        defines = '\n'.join(re.findall(r'^#define\s+GPIO_(?:CLOCK|DATA)_.*$',
                                       self.source('intel_gmbus_regs.h'), re.M))
        self.run_native(r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
typedef uint32_t u32;
@@DEFINES@@
struct intel_display {int version; struct {bool i830,i845g;}platform;};
struct intel_gmbus {struct intel_display *display; int gpio_reg;};
#define DISPLAY_VER(d) ((d)->version)
#define INTEL_DISPLAY_WA_16025573575 1
#define intel_display_wa(d,w) ((void)(w),(d)->version >= 30)
static u32 reg_value; static unsigned writes, incomplete_masks;
static u32 read_reg(struct intel_display*d,int r){(void)d;(void)r;return reg_value;}
static void write_reg(struct intel_display*d,int r,u32 val){
 (void)r;writes++;
 const u32 masks=GPIO_CLOCK_DIR_MASK|GPIO_CLOCK_VAL_MASK|GPIO_DATA_DIR_MASK|GPIO_DATA_VAL_MASK;
 if(d->version>=30 && (val&masks)!=masks)incomplete_masks++;
 const u32 mask[]={GPIO_CLOCK_DIR_MASK,GPIO_CLOCK_VAL_MASK,GPIO_DATA_DIR_MASK,GPIO_DATA_VAL_MASK};
 const u32 bits[]={GPIO_CLOCK_DIR_OUT,GPIO_CLOCK_VAL_OUT,GPIO_DATA_DIR_OUT,GPIO_DATA_VAL_OUT};
 for(unsigned i=0;i<4;i++)if(val&mask[i])reg_value=(reg_value&~bits[i])|(val&bits[i]);
 const u32 pullups=GPIO_CLOCK_PULLUP_DISABLE|GPIO_DATA_PULLUP_DISABLE;
 reg_value=(reg_value&~pullups)|(val&pullups);
 /* Mask bits are write-only; reading cannot preserve them. */
}
#define intel_de_read_fw read_reg
#define intel_de_read_notrace read_reg
#define intel_de_write_fw write_reg
#define intel_de_write_notrace write_reg
#define intel_de_posting_read_fw read_reg
#define intel_de_posting_read read_reg
@@OWNERS@@
int main(void){
 const int versions[]={2,3,4,9,12,20,30,35};
 const u32 bits[]={GPIO_CLOCK_DIR_OUT,GPIO_CLOCK_VAL_OUT,GPIO_DATA_DIR_OUT,GPIO_DATA_VAL_OUT};
 for(unsigned v=0;v<sizeof(versions)/sizeof(*versions);v++)for(unsigned seed=0;seed<64;seed++){
  struct intel_display d={.version=versions[v]};struct intel_gmbus bus={&d,0};
  for(int clock=0;clock<2;clock++)for(int high=0;high<2;high++){
   u32 pullups=(seed&16?GPIO_CLOCK_PULLUP_DISABLE:0)|(seed&32?GPIO_DATA_PULLUP_DISABLE:0);
   reg_value=pullups;
   for(unsigned i=0;i<4;i++)if(seed&(1U<<i))reg_value|=bits[i];
   u32 sibling=reg_value&(clock?(GPIO_DATA_DIR_OUT|GPIO_DATA_VAL_OUT):(GPIO_CLOCK_DIR_OUT|GPIO_CLOCK_VAL_OUT));
   writes=incomplete_masks=0;
   if(clock)set_clock(&bus,high);else set_data(&bus,high);
   assert(incomplete_masks==0);
   assert((reg_value&(clock?(GPIO_DATA_DIR_OUT|GPIO_DATA_VAL_OUT):(GPIO_CLOCK_DIR_OUT|GPIO_CLOCK_VAL_OUT)))==sibling);
   u32 direction=clock?GPIO_CLOCK_DIR_OUT:GPIO_DATA_DIR_OUT;
   u32 output=clock?GPIO_CLOCK_VAL_OUT:GPIO_DATA_VAL_OUT;
   assert(!!(reg_value&direction)==!high);assert(!(reg_value&output));
   if(d.version<4)assert((reg_value&(GPIO_CLOCK_PULLUP_DISABLE|GPIO_DATA_PULLUP_DISABLE))==pullups);
   unsigned before=writes;reg_value|=GPIO_CLOCK_VAL_IN|GPIO_DATA_VAL_IN;
   assert(get_clock(&bus)==1 && get_data(&bus)==1);assert(writes==before);
   reg_value&=~(GPIO_CLOCK_VAL_IN|GPIO_DATA_VAL_IN);
   assert(get_clock(&bus)==0 && get_data(&bus)==0);assert(writes==before);
  }
 }
}
'''.replace('@@DEFINES@@', defines).replace('@@OWNERS@@', owners))

    def test_wcl_rejects_joiner_without_changing_other_platforms(self):
        owner = function(self.source('intel_dp.c'), 'intel_dp_has_joiner')
        self.run_native(r'''
#include <assert.h>
#include <stdbool.h>
struct intel_display {int version;};
struct intel_encoder {int port;};
struct intel_digital_port {struct intel_encoder base;};
struct intel_connector {struct {struct {struct {bool pipe_joiner_enable;}edp;}vbt;}panel;};
struct intel_dp {struct intel_display *display;struct intel_digital_port port;struct intel_connector *attached_connector;int mso_link_count;bool edp;};
#define to_intel_display(p) ((p)->display)
#define dp_to_dig_port(p) (&(p)->port)
#define intel_dp_is_edp(p) ((p)->edp)
#define DISPLAY_VER(p) ((p)->version/100)
#define DISPLAY_VERx100(p) ((p)->version)
#define PORT_A 0
@@OWNER@@
int main(void){
 const int versions[]={1000,1100,1200,2000,3000,3002,3500};
 for(unsigned i=0;i<sizeof(versions)/sizeof(*versions);i++)for(int port=0;port<2;port++){
  struct intel_display d={versions[i]};struct intel_connector c={0};struct intel_dp dp={.display=&d,.attached_connector=&c};dp.port.base.port=port;
  bool expected=(d.version>=1200 && d.version!=3002)||(d.version==1100 && port!=PORT_A);
  assert(intel_dp_has_joiner(&dp)==expected);
  dp.mso_link_count=2;assert(!intel_dp_has_joiner(&dp));dp.mso_link_count=0;
  dp.edp=true;assert(!intel_dp_has_joiner(&dp));c.panel.vbt.edp.pipe_joiner_enable=true;
  assert(intel_dp_has_joiner(&dp)==expected);
 }
}
'''.replace('@@OWNER@@', owner))

    def test_ptl_clock_probe_keeps_valid_bios_clock(self):
        owner = function(self.source('intel_cdclk.c'), 'bxt_sanitize_cdclk')
        self.run_native(r'''
#include <assert.h>
#include <stdint.h>
typedef uint32_t u32;
struct intel_cdclk_config {int vco,cdclk,bypass;};
struct intel_display {int version;struct {struct intel_cdclk_config hw;}cdclk;};
#define DISPLAY_VER(d) ((d)->version)
#define INVALID_PIPE -1
#define CDCLK_CTL 0
#define CDCLK_FREQ_DECIMAL_MASK 0x7ff
#define drm_dbg_kms(...) ((void)0)
#define intel_update_cdclk(...) ((void)0)
#define intel_cdclk_dump_config(...) ((void)0)
static u32 ctl;
static u32 intel_de_read(struct intel_display*d,int r){return ctl;}
static void intel_de_write(struct intel_display*d,int r,u32 v){ctl=v;}
static int bxt_calc_cdclk(struct intel_display*d,int v){return v;}
static int bxt_calc_cdclk_pll_vco(struct intel_display*d,int v){return 1000;}
static u32 bxt_cdclk_cd2x_pipe_mask(struct intel_display*d){return 0x380000;}
static u32 bxt_cdclk_cd2x_pipe(struct intel_display*d,int p){return 0x380000;}
static u32 bxt_cdclk_ctl(struct intel_display*d,const struct intel_cdclk_config*c,int p){return d->version>=30?0x100:0x380100;}
@@OWNER@@
int main(void){
 const int versions[]={11,12,20,30,35};
 for(unsigned i=0;i<sizeof(versions)/sizeof(*versions);i++){
  struct intel_display d={.version=versions[i],.cdclk.hw={1000,100,0}};
  ctl=0x100;bxt_sanitize_cdclk(&d);assert(d.cdclk.hw.cdclk==100 && d.cdclk.hw.vco==1000);
  d.cdclk.hw.vco=0;bxt_sanitize_cdclk(&d);assert(d.cdclk.hw.cdclk==0);
 }
}
'''.replace('@@OWNER@@', owner))

    def test_cd2x_helpers_compile_with_real_register_definitions(self):
        source = self.source('intel_cdclk.c')
        owners = '\n'.join(function(source, name) for name in
                           ('bxt_cdclk_cd2x_pipe_mask', 'bxt_cdclk_cd2x_pipe'))
        defines = '\n'.join(re.findall(r'^#define\s+(?:BXT|ICL|TGL)_CDCLK_CD2X_PIPE.*$',
                                       self.source('intel_display_regs.h'), re.M))
        self.run_native(r'''
#include <assert.h>
#include <stdint.h>
typedef uint32_t u32;
struct intel_display {int version;};
enum pipe {INVALID_PIPE=-1,PIPE_A,PIPE_B,PIPE_C};
#define DISPLAY_VER(d) ((d)->version)
#define REG_GENMASK(h,l) ((~0U<<(l))&(~0U>>(31-(h))))
#define REG_FIELD_PREP(mask,val) (((u32)(val)<<__builtin_ctz(mask))&(mask))
#define _PICK(index,...) (((const u32[]){__VA_ARGS__})[(index)])
@@DEFINES@@
@@OWNERS@@
int main(void){
 const int versions[]={9,11,12,20,30,35};
 for(unsigned i=0;i<sizeof(versions)/sizeof(*versions);i++){
  struct intel_display d={versions[i]};u32 mask=bxt_cdclk_cd2x_pipe_mask(&d);
  assert(mask==(d.version>=11?0x380000U:0x300000U));
  assert(bxt_cdclk_cd2x_pipe(&d,INVALID_PIPE)==mask);
  assert(bxt_cdclk_cd2x_pipe(&d,PIPE_A)==0);
  assert(bxt_cdclk_cd2x_pipe(&d,PIPE_B)==0x100000U);
  assert(bxt_cdclk_cd2x_pipe(&d,PIPE_C)==(d.version==11?0x300000U:0x200000U));
 }
}
'''.replace('@@DEFINES@@', defines).replace('@@OWNERS@@', owners))
