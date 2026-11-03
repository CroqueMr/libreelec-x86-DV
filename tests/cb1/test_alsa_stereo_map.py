"""Keep a known stereo PCM layout when ALSA temporarily reports no channel names."""
import unittest
from test_ai_reentry import execute
from test_native_video_source import TREE, body


class ALSAStereoMapTests(unittest.TestCase):
    def test_unknown_stereo_map_uses_native_legacy_layout_without_guessing_multichannel(self):
        source=(TREE/'xbmc/cores/AudioEngine/Sinks/AESinkALSA.cpp').read_text()
        layout=body(source,'inline CAEChannelInfo CAESinkALSA::GetChannelLayout(')
        legacy=body(source,'inline CAEChannelInfo CAESinkALSA::GetChannelLayoutLegacy(')
        execute(r'''
#include <algorithm>
#include <cassert>
#include <cstdlib>
#include <string>
#include <vector>
enum AEChannel {AE_CH_UNKNOWN1,AE_CH_FL,AE_CH_FR,AE_CH_FC,AE_CH_LFE,AE_CH_BL,AE_CH_BR,AE_CH_SL,AE_CH_SR};
enum {AE_FMT_PCM,AE_FMT_RAW,LOGDEBUG};
struct CAEChannelInfo {
 std::vector<AEChannel> values;
 unsigned Count()const{return values.size();}
 AEChannel operator[](unsigned i)const{return values[i];}
 void operator+=(AEChannel c){values.push_back(c);}
 bool HasChannel(AEChannel c)const{return std::find(values.begin(),values.end(),c)!=values.end();}
 bool ContainsChannels(const CAEChannelInfo& other)const{
  return std::all_of(other.values.begin(),other.values.end(),[&](auto c){return HasChannel(c);});}
 bool IsLayoutValid()const{return std::any_of(values.begin(),values.end(),[](auto c){return c!=AE_CH_UNKNOWN1;});}
 int BestMatch(const std::vector<CAEChannelInfo>&)const{return 0;}
 explicit operator std::string()const{return {};}
};
struct AEAudioFormat{int m_dataFormat=AE_FMT_PCM;CAEChannelInfo m_channelLayout{{AE_CH_FL,AE_CH_FR}};};
struct snd_pcm_chmap_t{unsigned channels;AEChannel pos[8];};
inline snd_pcm_chmap_t reported{2,{AE_CH_UNKNOWN1,AE_CH_UNKNOWN1}};
inline bool hasMap=true;
snd_pcm_chmap_t* snd_pcm_get_chmap(int){
 if(!hasMap)return nullptr;
 auto* map=static_cast<snd_pcm_chmap_t*>(std::malloc(sizeof(reported)));*map=reported;return map;}
struct CLog{template<class... T>static void Log(T...) {}};
inline AEChannel LegacyALSAChannelMap[]={AE_CH_FL,AE_CH_FR,AE_CH_BL,AE_CH_BR,AE_CH_FC,AE_CH_LFE,AE_CH_SL,AE_CH_SR};
inline AEChannel LegacyALSAChannelMap51Wide[]={AE_CH_FL,AE_CH_FR,AE_CH_SL,AE_CH_SR,AE_CH_FC,AE_CH_LFE,AE_CH_BL,AE_CH_BR};
struct CAESinkALSA{
 int m_pcm=0;
 static CAEChannelInfo GetChannelLayoutRaw(const AEAudioFormat&){return {{AE_CH_FL,AE_CH_FR,AE_CH_BL,AE_CH_BR,AE_CH_FC,AE_CH_LFE,AE_CH_SL,AE_CH_SR}};}
 static CAEChannelInfo ALSAchmapToAEChannelMap(snd_pcm_chmap_t* m){CAEChannelInfo i;for(unsigned c=0;c<m->channels;++c)i+=m->pos[c];return i;}
 static std::string ALSAchmapToString(snd_pcm_chmap_t*){return {};}
 static CAEChannelInfo GetAlternateLayoutForm(const CAEChannelInfo&){return {};}
 static CAEChannelInfo GetChannelLayoutLegacy(const AEAudioFormat& format,unsigned minChannels,unsigned maxChannels) LEGACY
 CAEChannelInfo GetChannelLayout(const AEAudioFormat& format,unsigned channels) LAYOUT
};
int main(){
 CAESinkALSA sink;AEAudioFormat format;
 auto stereo=sink.GetChannelLayout(format,2);
 assert(stereo.values==std::vector<AEChannel>({AE_CH_FL,AE_CH_FR}));
 reported={2,{AE_CH_FR,AE_CH_FL}};
 assert(sink.GetChannelLayout(format,2).values==std::vector<AEChannel>({AE_CH_FR,AE_CH_FL}));
 reported={2,{AE_CH_UNKNOWN1,AE_CH_UNKNOWN1}};
 format.m_channelLayout={{AE_CH_FC}};assert(!sink.GetChannelLayout(format,2).IsLayoutValid());
 format.m_channelLayout={{AE_CH_FL,AE_CH_FR,AE_CH_FC,AE_CH_LFE,AE_CH_BL,AE_CH_BR}};
 reported.channels=6;assert(!sink.GetChannelLayout(format,6).IsLayoutValid());
 format.m_dataFormat=AE_FMT_RAW;assert(sink.GetChannelLayout(format,8).Count()==8);
 format=AEAudioFormat{};hasMap=false;
 assert(sink.GetChannelLayout(format,2).values==std::vector<AEChannel>({AE_CH_FL,AE_CH_FR}));
}
'''.replace('LAYOUT',layout).replace('LEGACY',legacy))
