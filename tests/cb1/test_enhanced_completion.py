"""Authored-DV Enhanced must complete analysis before Kodi advances the source."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from shipped_kodi import shipped_code

class EnhancedCompletion(unittest.TestCase):
    def test_bounded_completion_retains_the_current_picture(self):
        code=shipped_code('xbmc/windowing/gbm/WinSystemGbmGLESContext.cpp')
        start=code.index('  if (capturing || (metadata.Data() &&')
        end=code.index('  // A paused final surface',start)
        program=r'''
#include <cassert>
#include <algorithm>
#include <cstdint>
#include <chrono>
#include <thread>
constexpr int DVBRIDGE_MODE_ENHANCED_DV=4,DVBRIDGE_MODE_HDR10PLUS=6;
struct CDVBridgeGLES { enum class FrameStatus {Ready,Pending,Busy,Failed}; };
using Status=CDVBridgeGLES::FrameStatus;
static int polls;
Status run(bool authored,int mode,bool capturing,Status initial,int readyAfter,bool expired=false){
  struct {bool present;const void* Data()const{return present?this:nullptr;}} metadata{authored};
  struct {int mode;} policy{mode};
  struct Bridge{int remaining;bool PollReady(){++polls;return --remaining<=0;}
    Status PollStatus(uint64_t){assert(false && "Legacy wait must remain nonblocking");return Status::Failed;}
    void PrefetchHardwareFEL(int,int){assert(false && "Legacy path must not prefetch");}} bridge{readyAfter};
  auto* m_dvBridge=&bridge;
  auto prepare=[](){return Status::Pending;};
  polls=0;auto status=initial;
  bool prefetchFEL=false;const int *successor=nullptr;int preferences=0;
  const auto preparationDeadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(expired?-1:8);
'''+code[start:end]+r'''
  return status;
}
int main(){
  assert(run(true,4,false,Status::Pending,2)==Status::Ready && polls==2);
  assert(run(true,4,false,Status::Pending,1,true)==Status::Ready && polls==1);
  assert(run(true,4,false,Status::Ready,2)==Status::Ready && polls==0);
  assert(run(true,4,false,Status::Busy,2)==Status::Ready && polls==2);
  assert(run(true,4,false,Status::Pending,1000)==Status::Pending && polls<1000);
  assert(run(true,0,false,Status::Pending,2)==Status::Pending && polls==0);
  assert(run(false,4,false,Status::Pending,2)==Status::Pending && polls==0);
  assert(run(false,0,true,Status::Pending,2)==Status::Ready && polls==2);
}
'''
        with tempfile.TemporaryDirectory() as d:
            path=Path(d);source=path/'check.cpp';binary=path/'check';source.write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            result=subprocess.run([str(binary)],text=True,capture_output=True)
            self.assertEqual(result.returncode,0,result.stderr)
