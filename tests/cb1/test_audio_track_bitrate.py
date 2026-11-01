"""Accepted track binding must start a fresh native bitrate measurement."""
import unittest
from test_native_video_source import TREE, body
import test_audio_information_wiring as wiring


class AudioTrackBitrate(unittest.TestCase):
    run_cpp = wiring.AudioInformationWiring.run_cpp

    def test_accepted_track_change_does_not_publish_the_previous_bitrate(self):
        native = (TREE/'xbmc/cores/VideoPlayer/VideoPlayerAudio.cpp').read_text()
        opening = body(native, 'void CVideoPlayerAudio::OpenStream(CDVDStreamInfo&')
        bind = opening[opening.index('  /* store our stream hints */'):opening.index('  /* update codec information')]
        stats = (TREE/'xbmc/utils/BitstreamStats.cpp').read_text()
        stats = '\n'.join(line for line in stats.splitlines() if not line.startswith('#include'))
        code = r'''
#include "utils/BitstreamStats.h"
#include "cores/AudioEngine/Utils/AEAudioSourceInfo.h"
#include <cassert>
int64_t ticks=0;
int64_t CurrentHostCounter(){return ticks;}
int64_t CurrentHostFrequency(){return 1000;}
STATS
constexpr int LOGINFO=0;
struct CLog{template<class... T>static void Log(T...){}};
struct Hints{int codec=1,profile=0,samplerate=48000,bitspersample=24,channels=2,channellayout=3;
 AE::AudioSourceInfo GetAudioSourceInfo()const{return {};}};
struct Observer{void Reset(const AE::AudioSourceInfo&){}AE::AudioSourceInfo Get(){return {};}};
struct Process{void SetAudioSourceInfo(const AE::AudioSourceInfo&){}};
struct Worker{Hints m_streaminfo;Observer m_audioSource;bool m_audioSourceLogged=false;Process m_processInfo;BitstreamStats m_audioStats;
 void Bind(Hints hints){BIND}
};
int main(){
 Worker w;w.m_audioStats.Start();ticks=3000;w.m_audioStats.AddSampleBytes(30000);
 assert(w.m_audioStats.GetBitrate()==80000);
 w.Bind({});assert(w.m_audioStats.GetBitrate()==0);
 ticks=4000;w.m_audioStats.AddSampleBytes(40000);assert(w.m_audioStats.GetBitrate()==0);
 ticks=6000;w.m_audioStats.AddSampleBytes(50000);assert(w.m_audioStats.GetBitrate()==240000);
}
'''.replace('STATS',stats).replace('BIND',bind)
        self.run_cpp(code)
