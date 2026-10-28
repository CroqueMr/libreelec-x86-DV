"""Exercise the real BeginDVBridge sink refresh admission, independently of packets."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE


class SinkRateTests(unittest.TestCase):
    def test_legacy_sinks_obey_2160p60_capability_and_v2_is_unchanged(self):
        source=(TREE/"xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp").read_text()
        start=source.index("    const auto sink = display->GetDolbyVisionCaps();",
                           source.index("bool CWinSystemGbmGLESContext::BeginDVBridge()"))
        end=source.index("    if (!m_dvState.Capture",start)
        native=source[start:end]
        code=r'''
#include <cassert>
#include <initializer_list>
struct Caps{unsigned version;bool legacy_vsif,supports_2160p60;};
struct Display{Caps caps;Caps GetDolbyVisionCaps()const{return caps;}};
struct Mode{unsigned clock,htotal,vtotal,vdisplay;};
struct DRM{const Mode*mode;const Mode*GetSelectedMode()const{return mode;}};
bool admitted(Display*display,const Mode*selected){
 DRM driver{selected};auto*drm=&driver;
 const auto failure=[](const char*,const char*){return false;};
 BODY
 return true;
}
int main(){
 for(unsigned version:{0u,1u,2u})for(bool bit:{false,true}){
  if(version==2 && !bit)continue; /* The V2 parser always supplies true. */
  Display display{{version,version<2,bit}};
  for(unsigned rate:{24u,25u,30u,50u,60u})for(unsigned height:{1080u,2160u}){
   Mode mode{9900*rate,4400,2250,height};
   bool expected=height<2160 || rate<=30 || bit;
   assert(admitted(&display,&mode)==expected);
  }
 }
 Display v2{{2,false,true}};
 Mode fractional{593406,4400,2250,2160};
 assert(admitted(&v2,&fractional));
}
'''.replace("BODY",native)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);path=root/"test.cpp";binary=root/"test"
            path.write_text(code)
            subprocess.run(["c++","-std=c++20","-Wall","-Wextra","-Werror",
                            str(path),"-o",str(binary)],check=True)
            result=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
