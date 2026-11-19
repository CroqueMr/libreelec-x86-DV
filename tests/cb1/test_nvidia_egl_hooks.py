"""Execute EGL-GBM hooks; the device and public handle boundary are test doubles."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_hdr10_transport import function


class NvidiaEGLHooks(unittest.TestCase):
    def test_config_bounds_and_pbuffer_handle_lifetime(self):
        source=os.environ.get('CB1_EGL_GBM_SOURCE')
        if not source:
            self.skipTest('requires matched EGL-GBM source')
        source=Path(source)/'src'
        hooks=function((source/'gbm-display.c').read_text(),'eGbmChooseConfigHook')+'\n'+function((source/'gbm-platform.c').read_text(),'CreatePbufferSurfaceHook')
        program=r'''
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
typedef struct {int refs;} GbmObject;
typedef struct {
  struct {PFNEGLCHOOSECONFIGPROC ChooseConfig;
          PFNEGLCREATEPBUFFERSURFACEPROC CreatePbufferSurface;} egl;
} GbmPlatformData;
typedef struct {GbmObject base;GbmPlatformData* data;EGLDisplay devDpy;} GbmDisplay;
static GbmPlatformData data;
static GbmDisplay display;
static unsigned allocations;
static bool failAllocation;
static EGLint choices=3,lastError=EGL_SUCCESS;
static void* allocate(size_t size) {
  allocations++;
  return failAllocation && allocations==2 ? NULL : malloc(size);
}
static void* eGbmRefHandle(EGLDisplay handle) {
  if(handle!=(EGLDisplay)&display)return NULL;
  display.base.refs++;return &display;
}
static void eGbmUnrefObject(GbmObject* object) {assert(object==&display.base);object->refs--;}
static void eGbmSetError(GbmPlatformData* owner,EGLint error) {assert(owner==&data);lastError=error;}
static uint32_t ConfigToDrmFourCC(GbmDisplay* owner,EGLConfig config) {
  assert(owner==&display && config);return 0x34325258;
}
static EGLBoolean choose(EGLDisplay dpy,const EGLint* attrs,EGLConfig* configs,EGLint size,EGLint* count) {
  (void)dpy;(void)attrs;
  if(!count)return EGL_FALSE;
  if(configs)for(EGLint i=0;i<size && i<choices;i++)configs[i]=(EGLConfig)(uintptr_t)(i+1);
  *count=choices;return EGL_TRUE;
}
static EGLSurface pbuffer(EGLDisplay dpy,EGLConfig config,const EGLint* attrs) {
  (void)dpy;(void)config;(void)attrs;return (EGLSurface)(uintptr_t)33;
}
#define malloc allocate
HOOKS
#undef malloc
int main(int argc,char** argv) {
  assert(argc==2);int test=atoi(argv[1]);
  display.base.refs=1;display.data=&data;
  data.egl.ChooseConfig=choose;data.egl.CreatePbufferSurface=pbuffer;
  EGLint attrs[]={EGL_NATIVE_VISUAL_ID,0x34325258,EGL_NONE};
  EGLint count=3;EGLConfig config;
  if(test==1)assert(eGbmChooseConfigHook((EGLDisplay)&display,NULL,NULL,0,&count) && count==3);
  if(test==2) {count=0;assert(eGbmChooseConfigHook((EGLDisplay)&display,attrs,NULL,0,&count) && count==3);}
  if(test==3) {count=1;assert(eGbmChooseConfigHook((EGLDisplay)&display,attrs,&config,1,&count) && count==1 && config);}
  if(test==4)assert(!eGbmChooseConfigHook((EGLDisplay)&display,attrs,NULL,0,NULL) && lastError==EGL_BAD_PARAMETER);
  if(test==5) {failAllocation=true;assert(!eGbmChooseConfigHook((EGLDisplay)&display,attrs,NULL,0,&count) && lastError==EGL_BAD_ALLOC);}
  if(test==6)assert(CreatePbufferSurfaceHook(EGL_NO_DISPLAY,NULL,NULL)==EGL_NO_SURFACE);
  if(test==7)assert(CreatePbufferSurfaceHook((EGLDisplay)&display,NULL,NULL)==(EGLSurface)(uintptr_t)33);
  if(test==8) {choices=0;assert(eGbmChooseConfigHook((EGLDisplay)&display,attrs,NULL,0,&count) && count==0);}
  assert(display.base.refs==1 && "display reference must be returned on every path");
}
'''.replace('HOOKS',hooks)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'test.c').write_text(program)
            built=subprocess.run(['cc','-std=gnu11','-O1','-fsanitize=address,undefined',
                str(root/'test.c'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            for case in range(1,9):
                with self.subTest(case=case):
                    ran=subprocess.run([str(root/'test'),str(case)],capture_output=True,text=True)
                    self.assertEqual(ran.returncode,0,ran.stderr[-3000:])


if __name__=='__main__':
    unittest.main()
