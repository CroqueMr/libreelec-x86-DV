"""An absent native-DV property has a precise, non-enabling driver witness."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


@unittest.skipUnless(os.environ.get('CB1_KERNEL_SOURCE'), 'matched patched kernel required')
class AMDCapabilityDiagnosticsTests(unittest.TestCase):
    def test_attach_reports_family_route_and_parameter_without_enabling_dcn4(self):
        path = Path(os.environ['CB1_KERNEL_SOURCE']) / 'drivers/gpu/drm/amd/display/amdgpu_dm/amdgpu_dm_dv.c'
        source = path.read_text()
        gate = function(source, 'dv_display_supported')
        attach = function(source, 'amdgpu_dm_dv_attach')
        families = sorted(set(re.findall(r'\b(?:DCN|DCE)_VERSION_\w+', gate)) | {'DCN_VERSION_4_01', 'DCN_VERSION_4_02'})
        code = r'''
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <stdarg.h>
#include <string.h>
enum dce_version {FAMILIES};
enum {DRM_MODE_CONNECTOR_HDMIA=1,SIGNAL_TYPE_HDMI_TYPE_A=2,DRM_MODE_PROP_ATOMIC=3};
struct dc {struct {enum dce_version dce_version;}*ctx;};
struct amdgpu_device {struct {struct dc* dc;}dm;}device;
struct amdgpu_dm_connector {
 struct {void* dev;struct {unsigned id;}base;int connector_type;}base;
 struct {int connector_signal;}*dc_link;
 void *dv_standard_property,*hdr10_deep_color_property;
};
static bool dv_standard=true;static int properties;
static char message[1024];
static struct amdgpu_device* drm_to_adev(void* ignored){(void)ignored;return &device;}
static void* drm_property_create_bool(void* dev,int flags,const char* name){
 (void)dev;(void)flags;(void)name;++properties;return &properties;}
#define drm_object_attach_property(...) ((void)0)
static void drm_info(void* dev,const char* fmt,...){
 (void)dev;va_list args;va_start(args,fmt);vsnprintf(message,sizeof(message),fmt,args);va_end(args);}
GATE
ATTACH
int main(){
 struct {enum dce_version dce_version;}ctx={DCN_VERSION_3_2};
 struct dc dc={.ctx=(void*)&ctx};device.dm.dc=&dc;
 struct {int connector_signal;}link={SIGNAL_TYPE_HDMI_TYPE_A};
 struct amdgpu_dm_connector c={.base={.base={.id=409},.connector_type=DRM_MODE_CONNECTOR_HDMIA},.dc_link=(void*)&link};
 amdgpu_dm_dv_attach(&c);assert(properties==2);
 assert(strstr(message,"connector=409") && strstr(message,"family_supported=1") && strstr(message,"native_hdmi=1"));
 for(int version=DCN_VERSION_4_01;version<=DCN_VERSION_4_02;++version){
  ctx.dce_version=version;properties=0;message[0]=0;
  amdgpu_dm_dv_attach(&c);assert(properties==0 && strstr(message,"family_supported=0"));
 }
 ctx.dce_version=DCN_VERSION_3_2;link.connector_signal=99;message[0]=0;
 amdgpu_dm_dv_attach(&c);assert(!properties && strstr(message,"native_hdmi=0"));
 link.connector_signal=SIGNAL_TYPE_HDMI_TYPE_A;dv_standard=false;message[0]=0;
 amdgpu_dm_dv_attach(&c);assert(properties==1 && strstr(message,"dv_parameter=0"));
 device.dm.dc=NULL;properties=0;message[0]=0;
 amdgpu_dm_dv_attach(&c);assert(!properties && strstr(message,"family_supported=0"));
}
'''.replace('FAMILIES', ','.join(families)).replace('GATE', gate).replace('ATTACH', attach)
        with tempfile.TemporaryDirectory() as directory:
            codefile, binary = Path(directory)/'test.c', Path(directory)/'test'
            codefile.write_text(code)
            built = subprocess.run(['cc','-std=gnu11','-Wall','-Wextra','-Werror',
                '-Wno-unused-function',str(codefile),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
