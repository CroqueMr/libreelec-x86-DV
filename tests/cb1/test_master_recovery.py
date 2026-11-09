"""A performance downgrade is announced once, only after Standard is presented."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

@unittest.skipUnless(os.environ.get('KODI_NATIVE_SOURCE_TREE'), 'Set patched Kodi source tree')
class MasterRecoveryTests(unittest.TestCase):
    def test_accepted_output_and_file_lifecycle(self):
        tree=Path(os.environ['KODI_NATIVE_SOURCE_TREE'])
        header=(tree/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVPlaybackNotification.h').read_text()
        header='\n'.join(line for line in header.splitlines() if not line.startswith('#include'))
        program=r'''
#include <atomic>
#include <mutex>
#include <string>
#include <cassert>
#define HAVE_DVBRIDGE
struct Settings{bool enabled=false;bool GetBool(const char*){return enabled;}} settings;
struct Component{Settings* GetSettings(){return &settings;}} component;
struct CServiceBroker{static Component* GetSettingsComponent(){return &component;}};
struct CDVPlaybackInfo{enum{HDMI=1,HDR10=8,SDR=32};template<class T> static std::string Mode(const T&){return "mode";}};
namespace DVBRIDGE {
inline std::atomic<unsigned long long> nativeRevision{0};
enum class OutputMode{Disabled,Standard};
struct Preferences{OutputMode output=OutputMode::Standard;};
inline Preferences FrameOutputSettings(){return {};}
struct SourceBinding{unsigned long long stream{},picture{},revision{};bool Valid()const{return stream && picture && revision;}};
}
@@HEADER@@
static int recoveries=0,notifications=0;static std::string notified;
void DVBRIDGE::PlaybackNotification::EmitMasterRecovery(){++recoveries;}
void DVBRIDGE::PlaybackNotification::Emit(const std::string& text){++notifications;notified=text;}
void DVBRIDGE::PlaybackNotification::EmitAI(int){}
int main(){using N=DVBRIDGE::PlaybackNotification;
 struct Output{unsigned flags=1;int requested=5,effective=5;unsigned long long stream=1,picture=1;} out;
 N::StartVideo();N::ArmMasterRecovery();N::NativeOutputAccepted(out);assert(!recoveries);
 out.effective=1;out.flags=8;N::NativeOutputAccepted(out);assert(!recoveries);
 out.flags=1;out.requested=1;N::NativeOutputAccepted(out);assert(!recoveries);
 out.requested=5;N::NativeOutputAccepted(out);assert(recoveries==1);
 N::NativeOutputAccepted(out);assert(recoveries==1);
 N::ArmMasterRecovery();N::StopVideo();N::NativeOutputAccepted(out);assert(recoveries==1);
 N::ArmMasterRecovery();N::StartVideo();N::NativeOutputAccepted(out);assert(recoveries==1);
 settings.enabled=true;N::StartVideo();assert(N::Pending());
 const auto generation=N::Generation();out.stream=3;out.picture=5;out.flags=32;out.requested=out.effective=8;
 N::RenderedNative(generation,{out.stream,out.picture,9});
 auto stale=out;stale.picture=4;N::NativeOutputAccepted(stale);assert(N::Pending() && !notifications);
 N::NativeOutputAccepted(out);assert(!N::Pending() && notifications==1);
 N::NativeOutputAccepted(out);assert(notifications==1);
 N::StartVideo();const auto ordinary=N::Generation();N::RenderedOrdinary(ordinary);
 N::OrdinaryOutputAccepted(false);assert(N::Pending() && notifications==1);
 N::RenderedOrdinary(ordinary);N::OrdinaryOutputAccepted(true);
 assert(!N::Pending() && notifications==2 && notified=="Kodi default");
}
'''.replace('@@HEADER@@',header)
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'check.cpp').write_text(program)
            build=subprocess.run(['c++','-std=c++20',str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__':unittest.main()
