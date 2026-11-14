"""Run the shipped RPU level capture and the formatting behind the added Player information rows."""
from pathlib import Path
import os
import shlex
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE

DIALOG = TREE/'xbmc/dialogs/GUIDialogPlayerProcessInfo.cpp'


def helpers():
    # The dialog's file-local helpers, between the anonymous namespace braces.
    text = DIALOG.read_text()
    start = text.index('namespace\n{\n')
    return text[start:text.index('} // namespace', start)+len('} // namespace')]


def statement(prop):
    # One SetProperty statement of RefreshInfo, as the dialog ships it.
    text = DIALOG.read_text()
    start = text.index('SetProperty("'+prop+'",')
    return text[start:text.index(';', start)+1]


def run(test, program, flags=()):
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        for name, text in program.items():
            (root/name).parent.mkdir(parents=True, exist_ok=True)
            (root/name).write_text(text)
        build = subprocess.run(['c++', '-std=c++20', '-I'+str(root), '-I'+str(TREE/'xbmc'),
                                str(root/'test.cpp'), *flags, '-o', str(root/'test')],
                               capture_output=True, text=True)
        test.assertEqual(build.returncode, 0, build.stderr[-3000:])
        result = subprocess.run([str(root/'test')], capture_output=True, text=True)
        test.assertEqual(result.returncode, 0, result.stderr)


class FormattingTests(unittest.TestCase):
    def test_applied_sdr_components_and_profile10_are_truthful(self):
        source = DIALOG.read_text()
        start = source.index('    const bool partialL1 =')
        sdr = source[start:source.index('    SetProperty("DV.L5"', start)]
        start = source.index('    const bool plainHDRSDR =')
        guidance = source[start:source.index('    const double display =', start)]
        start = source.index('double PQNits(')
        nits = source[start:source.index('// A 12-bit PQ code', start)]
        program = r'''
#include "cores/VideoProcessingInfo.h"
#include <cassert>
#include <cmath>
#include <format>
#include <map>
struct StringUtils {template<class... T> static std::string Format(std::format_string<T...> pattern, T&&... args)
 {return std::format(pattern, std::forward<T>(args)...);}};
NITS
bool mockFits=true;
bool InfoValueFits(const std::string&){return mockFits;}
int main() {
 VideoProcessingInfo data;data.metadata=true;data.l1=true;data.profile=7;
 data.pq={11,3000,1000};data.appliedBlocks[1]=true;data.appliedBlocks[3]=true;data.blocks[3]=true;data.levels.l3={11,2100,2000};
 data.output.flags=32;data.output.effective=8;
 std::map<std::string,std::string> text;std::map<std::string,bool> used;
 auto SetProperty=[&]<class T>(const char* key,const T& value){
  if constexpr(std::is_same_v<T,bool>)used[key]=value;else text[key]=value;};
 auto refresh=[&]{const auto active=data.output.flags;const auto applied=data.AppliedBlocks();
  const bool metadata=active&&data.metadata;const bool hdr10=bool(active&8u);
  const auto& levels=data.levels;const auto carried=[&](unsigned n){return metadata&&data.blocks[n];};
  RAW_LUMINANCE SDR_BLOCK L3_BLOCK GUIDANCE_BLOCK PROFILE_BLOCK CREATIVE_BLOCK
 };
 refresh();assert(text["DV.UsedL1PQ"]=="3000 | 1000");
 assert(text["DV.CreativeTrims"].empty()&&!used["DV.UsedHDRStatic"]);
 data.output.flags=8;data.output.effective=3;refresh();assert(text["DV.UsedL1PQ"]=="3000 | 1000"&&text["DV.UsedL3"]=="2100 | 2000");
 data.output.effective=2;refresh();assert(text["DV.UsedL1PQ"]=="3000 | 1000");
 data.output.effective=3;data.appliedBlocks[3]=false;refresh();assert(text["DV.UsedL3"].empty());
 data.output.flags=1;data.output.effective=1;refresh();assert(text["DV.UsedL1PQ"].empty()&&!text["DV.UsedL1Nits"].empty());
 data.pq={4095,4095,4095};mockFits=false;refresh();
 assert(text["DV.L1Nits"]=="10000.0 | 10000.0 | 10000.0 nits");
 assert(text["DV.UsedL1Nits"]=="10000.0 | 10000.0 | 10000.0");mockFits=true;
 data.output.flags=32;data.output.effective=8;data.appliedBlocks.reset();refresh();assert(text["DV.UsedL1PQ"].empty());
 data.profile=0;refresh();assert(!used["DV.UsedHDRStatic"]&&!used["DV.UsedHDR10PlusMax"]&&!used["DV.UsedHDR10PlusAvg"]);
 data.output.sdrHDRInputUsed=25;data.output.sdrHDRInputValues={800,900,700,125};
 refresh();assert(used["DV.UsedHDRStatic"]&&used["DV.UsedHDR10PlusMax"]&&used["DV.UsedHDR10PlusAvg"]);
 assert(text["DV.UsedHDR10PlusMaxRGB"]=="800 | 900 | 700 nits" && text["DV.UsedHDR10PlusAverage"]=="125.0 nits");
 for(unsigned mask=0;mask<32;++mask){data.output.sdrHDRInputUsed=mask;refresh();
  assert(used["DV.UsedHDRStatic"]==bool(mask&7));
  assert(!text["DV.UsedHDRMin"].empty()==bool(mask&1));
  assert(!text["DV.UsedHDRMax"].empty()==bool(mask&2));
  assert(!text["DV.UsedHDRCLL"].empty()==bool(mask&4));
  assert(used["DV.UsedHDR10PlusMax"]==bool(mask&8)&&used["DV.UsedHDR10PlusAvg"]==bool(mask&16));}
 data.output.sdrHDRInputUsed=3;refresh();assert(!used["DV.UsedHDR10PlusMax"]&&!used["DV.UsedHDR10PlusAvg"]);
 data.output.effective=1;data.output.hdr10PlusDV=true;data.output.guidedSourceFields=2;
 refresh();assert(!used["DV.UsedHDRStatic"]&&used["DV.UsedHDR10PlusMax"]&&!used["DV.UsedHDR10PlusAvg"]);
 data.output.flags=0;refresh();assert(!used["DV.UsedHDRStatic"]&&!used["DV.UsedHDR10PlusMax"]);
 for(unsigned profile:{5u,7u,8u,10u}){data.profile=profile;data.compatibility=4;refresh();
  assert(text["DV.ProfileDetail"]==(profile==8?"8.4":profile==10?"10.4":std::to_string(profile)));}
 data.profile=10;data.compatibility=1;refresh();assert(text["DV.ProfileDetail"]=="10.1");
}
'''.replace('NITS', nits).replace('RAW_LUMINANCE',statement('DV.L1Nits')).replace('SDR_BLOCK', sdr).replace('L3_BLOCK',statement('DV.UsedL3')).replace('GUIDANCE_BLOCK', guidance).replace(
            'PROFILE_BLOCK', statement('DV.ProfileDetail')).replace('CREATIVE_BLOCK', statement('DV.CreativeTrims'))
        run(self, {'test.cpp': program})

    def test_level_values_are_named_as_authored(self):
        program = r'''
#include "cores/VideoProcessingInfo.h"
#include <algorithm>
#include <cassert>
#include <cmath>
#include <format>
#include <iterator>
#include <string>
#include <vector>
struct StringUtils {template<class... T> static std::string Format(std::format_string<T...> pattern, T&&... args)
 {return std::format(pattern, std::forward<T>(args)...);}};
static float mockWidth=-1;
struct CGUIFont {};
struct FontManager {CGUIFont font;CGUIFont* GetFont(const std::string&,bool){return &font;}} g_fontManager;
struct CGUITextLayout {std::string text;CGUITextLayout(CGUIFont*,bool){} void Update(const std::string& t){text=t;}
 float GetTextWidth()const{return mockWidth>=0?mockWidth:6.0f*text.size();}};
HELPERS
int main() {
 assert(RPUPrimaries(0)=="P3-D65" && RPUPrimaries(2)=="BT.2020" && RPUPrimaries(255)=="Custom");
 assert(PresetTargetNits(1)==100 && PresetTargetNits(49)==1000 && PresetTargetNits(24)==0);
 VideoDVLevels levels;
 // 2081, 2851 and 3079 are the codes of 100, 600 and 1000 nits; repeats show once.
 levels.l2={3079,2081,2851,2081}; levels.l2Count=4;
 assert(L2Targets(levels)=="100 · 600 · 1000 nits");
 // Presets resolve first, an unknown index through its L10 block, else by its index.
 levels.l8={27,24,1,50}; levels.l8Count=4;
 levels.l10[0]={24,0,2547,62}; levels.l10Count=1;
 assert(L8Targets(levels)=="100 · 300 · 600 nits · #50");
 levels.l8Count=0;
 assert(L8Targets(levels).empty());
 levels.l8={50}; levels.l8Count=1;
 assert(L8Targets(levels)=="#50");
 assert(L10Displays(levels)=="300 nits P3-D65");
 levels.l10[1]={60,2,3388,0}; levels.l10Count=2;
 assert(L10Displays(levels)=="300 nits P3-D65 · 2000 nits BT.2020");
 levels.contentType=1; levels.whitepoint=0; levels.referenceMode=true;
 assert(L11Content(levels)=="Cinema · D65 · reference mode");
 levels.contentType=4; levels.whitepoint=8; levels.referenceMode=false;
 assert(L11Content(levels)=="User-generated · D93");
 levels.contentType=9; levels.whitepoint=2;
 assert(L11Content(levels)=="Type 9 · 7254 K");
 // The native font bound preserves fitting explicit values and condenses only overflow.
 mockWidth=284;assert(InfoValueFits("exact boundary"));
 mockWidth=285;assert(!InfoValueFits("overflow"));
 assert(TargetList({48,100,300,600,1000,2000,4000,10000},{})=="8 targets · 48–10000 nits");
 assert(TargetList({48,100,300,600,1000,2000,4000,10000},{50,51})=="8: 48–10000 nits · 2 custom");
 assert(L10Displays(levels).find("displays")!=std::string::npos);
 mockWidth=-1;
 assert(PolicyText("Dolby Vision Adaptive HDR Mapping")=="DV Adaptive");

}
'''.replace('HELPERS', helpers())
        run(self, {'test.cpp': program})


class CaptureTests(unittest.TestCase):
    def test_rpu_levels_and_decoder_tags_reach_the_dialog(self):
        if not os.environ.get('FFMPEG_TEST_PREFIX'):
            self.skipTest('Set FFMPEG_TEST_PREFIX to the sanitizer-built FFmpeg prefix')
        prefix = Path(os.environ['FFMPEG_TEST_PREFIX'])
        cache = r'''
#pragma once
#include "cores/VideoProcessingInfo.h"
class CDataCacheCore {
public:
 bool SetVideoProcessingInfo(uint64_t,const VideoProcessingInfo& info) {m_info=info; return true;}
 VideoProcessingInfo GetVideoProcessingInfo() {return m_info;}
 VideoProcessingInfo m_info;
};
'''
        broker = r'''
#pragma once
#include "cores/DataCacheCore.h"
class CServiceBroker {public: static CDataCacheCore& GetDataCacheCore() {static CDataCacheCore cache; return cache;}};
'''
        program = r'''
#include "cores/VideoPlayer/DVDCodecs/Video/DVStreamTelemetry.h"
#include "dialogs/DVPixelFormat.h"
#include <cassert>
#include <map>
extern "C" {
#include <libavutil/mem.h>
}
int main() {
 size_t size=0;
 AVDOVIMetadata* data=av_dovi_metadata_alloc(&size);
 assert(data);
 const auto add=[&](uint8_t level) {
   auto* ext=av_dovi_get_ext(data,data->num_ext_blocks++); ext->level=level; return ext;
 };
 auto* l1=add(1);l1->l1.max_pq=3079;l1->l1.avg_pq=1000;
 for (uint16_t pq=2000; pq<2010; ++pq) add(2)->l2.target_max_pq=pq;
 auto* l3=add(3); l3->l3.min_pq_offset=2048; l3->l3.max_pq_offset=2111; l3->l3.avg_pq_offset=1987;
 auto* l4=add(4); l4->l4.anchor_pq=1500; l4->l4.anchor_power=2048;
 add(8)->l8.target_display_index=48;
 add(9)->l9.source_primary_index=0;
 auto* l10=add(10); l10->l10.target_display_index=60; l10->l10.target_primary_index=2;
 l10->l10.target_max_pq=3388; l10->l10.target_min_pq=62;
 auto* l11=add(11); l11->l11.content_type=1; l11->l11.whitepoint=0; l11->l11.reference_mode_flag=1;
 auto* l254=add(254); l254->l254.dm_mode=0; l254->l254.dm_version_index=2;
 auto* l255=add(255); l255->l255.dm_run_mode=1; l255->l255.dm_run_version=3;
 DVBRIDGE::SourceInfo source; source.profile=8; source.compatibility=1; source.bl=source.rpu=true;
 DVBRIDGE::StreamTelemetry::SourceBits(10,AV_PIX_FMT_YUV420P10LE,source,
     {AVCOL_PRI_BT2020,AVCOL_TRC_SMPTE2084,false,false,"FEL"});
 DVBRIDGE::StreamTelemetry::Metadata(data,true,10);
 const auto info=DVBRIDGE::NativeProcessingInfo(DVBRIDGE::StreamTelemetry::Read());
 // SDR is an actual accepted processing route, retaining original DV metadata in Input.
 auto rendered=DVBRIDGE::StreamTelemetry::Read();
 rendered.output.flags=CDVPlaybackInfo::SDR; rendered.output.effective=8;
 rendered.output.bits=10;
 auto sdr=DVBRIDGE::NativeProcessingInfo(rendered);
 assert(sdr.outputType==VideoOutputType::SDR && sdr.output.flags==CDVPlaybackInfo::SDR);
 assert(sdr.metadata && sdr.profile==8 && sdr.blocks[2] && sdr.levels.l2Count==10);
 assert(sdr.TransmittedBlocks().none() && sdr.AppliedBlocks()[1]);
 // HLG-base DV remains an original HLG-base source carrying its authored RPU.
 rendered.compatibility=4; rendered.tags.transfer=AVCOL_TRC_ARIB_STD_B67;
 sdr=DVBRIDGE::NativeProcessingInfo(rendered);
 assert(sdr.compatibility==4 && sdr.tags.transfer==AVCOL_TRC_ARIB_STD_B67 && sdr.metadata);

 assert(info.metadata && info.cm4 && info.compatibility==1);
 const auto& levels=info.levels;
 // All ten authored trim passes survive the bounded telemetry copy.
 assert(levels.l2Count==10 && levels.l2[0]==2000 && levels.l2[9]==2009);
 assert(levels.l3[0]==2048 && levels.l3[1]==2111 && levels.l3[2]==1987);
 assert(levels.l4[0]==1500 && levels.l4[1]==2048);
 assert(levels.l8Count==1 && levels.l8[0]==48 && levels.l9==0);
 assert(levels.l10Count==1 && levels.l10[0].index==60 && levels.l10[0].primaries==2 &&
        levels.l10[0].maxPQ==3388 && levels.l10[0].minPQ==62);
 assert(levels.contentType==1 && levels.whitepoint==0 && levels.referenceMode);
 assert(levels.dmMode==0 && levels.dmVersion==2 && levels.runMode==1 && levels.runVersion==3);
 assert(info.tags.enhancement=="FEL" && info.tags.primaries==AVCOL_PRI_BT2020);
 assert(DVBRIDGE::SourceColour(info.tags.primaries,info.tags.transfer,false,false)=="BT.2020 · PQ · Limited");
 assert(DVBRIDGE::SourceColour(AVCOL_PRI_BT709,AVCOL_TRC_BT709,true,true)=="BT.709 (assumed) · SDR · Full");
 assert(DVBRIDGE::SourceColour(-1,-1,false,false).empty());
 std::map<std::string,std::string> properties;
 const auto SetProperty=[&](const char* key,const std::string& value) {properties[key]=value;};
 auto shown=info;
 const auto colour=[&] {const auto& data=shown; COLOUR};
 colour(); assert(properties["DV.SourceColour"]=="BT.2020 · PQ · Limited");
 // Profiles 5 and 10.0 are IPT-PQc2 under unspecified tags, never Kodi's BT.709 guess.
 shown.profile=5; shown.compatibility=0;
 shown.tags={AVCOL_PRI_BT709,AVCOL_TRC_UNSPECIFIED,true,true,""};
 colour(); assert(properties["DV.SourceColour"]=="IPT-PQc2");
 shown.profile=10; colour(); assert(properties["DV.SourceColour"]=="IPT-PQc2");
 shown.compatibility=1; colour(); assert(properties["DV.SourceColour"]=="BT.709 (assumed) · Full");
 // The pinned parser admits seven static + 25 dynamic extension blocks.
 // L10 is static, L8 dynamic: all 32 slots form one legal mixed inventory.
 data->num_ext_blocks=0;
 for(unsigned i=0;i<7;++i){auto* t=add(10);t->l10.target_display_index=200+i;t->l10.target_max_pq=2000+i;}
 for(unsigned i=0;i<25;++i)add(8)->l8.target_display_index=i?uint8_t(200+i):48;
 assert(data->num_ext_blocks==AV_DOVI_MAX_EXT_BLOCKS);
 DVBRIDGE::StreamTelemetry::Begin(8,0,1,0,true,false,true);
 DVBRIDGE::StreamTelemetry::Metadata(data,true,10);
 auto complete=DVBRIDGE::NativeProcessingInfo(DVBRIDGE::StreamTelemetry::Read());
 assert(complete.levels.l8Count==25&&complete.levels.l8[24]==224);
 assert(complete.levels.l10Count==7&&complete.levels.l10[6].index==206);
 av_free(data);
}
'''.replace('COLOUR', statement('DV.SourceColour'))
        run(self, {'test.cpp': program, 'cores/DataCacheCore.h': cache, 'ServiceBroker.h': broker},
            ('-fsanitize=address,undefined', '-I'+str(prefix/'include'), '-L'+str(prefix/'lib'), '-lavutil', '-lm'))


class PictureStateTests(unittest.TestCase):
    def test_layer_type_and_primaries_guess_describe_the_current_stream(self):
        # The picture is reused from one stream to the next and only the FFmpeg decoder sets
        # these, so the player clears them where it clears the stereo mode.
        player = (TREE/'xbmc/cores/VideoPlayer/VideoPlayerVideo.cpp').read_text()
        opened = player[player.index('m_picture.stereoMode.clear();'):]
        opened = opened[:opened.index('m_stalled')]
        self.assertIn('m_picture.strDVELType.clear();', opened)
        self.assertIn('m_picture.colorPrimariesGuessed = false;', opened)
        self.assertIn('pPicture->colorPrimariesGuessed,', player)
        self.assertNotIn('m_originalColorPrimaries', player)
        # The flag is set where Kodi guesses, for every picture the FFmpeg decoder returns.
        ffmpeg = (TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/DVDVideoCodecFFmpeg.cpp').read_text()
        self.assertRegex(ffmpeg, r'colorPrimariesGuessed = pVideoPicture->color_primaries == AVCOL_PRI_UNSPECIFIED;'
                                 r'\s*if \(pVideoPicture->colorPrimariesGuessed\)\s*\{\s*'
                                 r'if \(pVideoPicture->iDisplayWidth > 1024')

    def test_hdr10plus_input_is_independent_of_processing(self):
        source = DIALOG.read_text()
        self.assertIn('const auto side = CServiceBroker::GetDataCacheCore().GetVideoSourceSideDataSnapshot();', source)
        self.assertNotIn('if (!(active && data.profile && !data.output.hdr10AI))', source)
        start=source.index('    const double display =')
        code=source[start:source.index('\n}',start)]
        program=r'''
#include <cassert>
#include <cmath>
#include <format>
#include <map>
#include <string>
extern "C" {
#include <libavutil/hdr_dynamic_metadata.h>
}
struct StringUtils {template<class... T> static std::string Format(std::format_string<T...> p,T&&... v)
{return std::format(p,std::forward<T>(v)...);}};
int main(){AVDynamicHDRPlus raw{};const auto* plus=&raw;
 struct Side {unsigned rejected{};unsigned RejectedSections()const{return rejected;}} owner;const auto* side=&owner;
 std::map<std::string,std::string> p;
 auto SetProperty=[&](const char* k,const std::string& v){p[k]=v;};
 const auto scaled=[](AVRational v){return 10000.0*av_q2d(v);};
 auto refresh=[&]{CODE};
 raw.num_windows=3;raw.application_version=1;raw.params[0].maxscl[0]={1,10};
 raw.params[0].maxscl[1]={2,10};raw.params[0].maxscl[2]={3,10};
 raw.params[0].average_maxrgb={1,100};raw.params[0].color_saturation_mapping_flag=1;
 raw.params[0].color_saturation_weight={3,2};refresh();
 assert(p["DV.HDR10PlusSection"]=="HDR10+ · window 1/3"&&p["DV.HDR10PlusCarried"]=="HDR10+ v1 / 3 windows");
 assert(p["DV.HDR10PlusMaxSCL"]=="1000 | 2000 | 3000 nits");
 assert(p["DV.HDR10PlusSaturation"]=="1.500×");
 raw.num_windows=1;refresh();assert(p["DV.HDR10PlusSection"]=="HDR10+ metadata");
 plus=nullptr;refresh();for(const auto& [k,v]:p)assert(v.empty());
 owner.rejected=4;refresh();assert(p["DV.HDR10PlusCarried"]=="HDR10+ · unavailable");
 assert(p["DV.HDR10PlusMaxSCL"].empty()&&p["DV.HDR10PlusSection"].empty());
}
'''.replace('CODE',code)
        run(self,{'test.cpp':program},('-I'+os.environ['FFMPEG_TEST_PREFIX']+'/include',))
        # A reachable published source can carry a valid pointer while PL declines dynamic use.
        from test_native_video_source import body
        from test_native_video_sidedata import SideDataTests
        renderer=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/DVBridgeGLES.cpp').read_text()
        importer=body(renderer,'bool ImportDVLayer(')
        start=source.index('    const bool plainHDRSDR =')
        guidance=source[start:source.index('    const double display =',start)]
        repo=Path(__file__).resolve().parents[2]
        program=r'''
#include "cores/VideoSourceSideData.h"
#include "cores/VideoProcessingInfo.h"
#include <cassert>
#include <cstdio>
#include <format>
#include <map>
extern "C" {
#include "FRAME_HEADER"
#include "STATS_HEADER"
}
struct Layer {
 dvbridge_gl_layout layout=DVBRIDGE_P010;int width=16,height=16;dvbridge_gl_plane planes[3]{};
 AVChromaLocation chromaLocation=AVCHROMA_LOC_LEFT;
 struct {unsigned profile{},informationGeneration=9;}sourceInfo;
 pl_hdr_metadata hdr{};bool hlg{},fullRange{};
 struct {bool Valid()const{return true;}}binding;
 unsigned sourceSerial=7;std::shared_ptr<const VideoSourceSideData> sourceSideData;
};
extern "C" bool dvbridge_gl_frame_import(dvbridge_gl_frame* out,pl_gpu,dvbridge_gl_layout,int,int,const dvbridge_gl_plane[3]){
 out->frame={};out->frame.color=pl_color_space_hdr10;return true;
}
extern "C" void dvbridge_gl_frame_set_chroma(dvbridge_gl_frame*,pl_chroma_location){}
pl_chroma_location SourceChroma(AVChromaLocation,unsigned){return PL_CHROMA_LEFT;}
bool ImportDVLayer(dvbridge_gl_frame* frame,pl_gpu gpu,const Layer& layer,unsigned* hdrInputUsed=nullptr) IMPORTER
struct StringUtils {template<class... T> static std::string Format(std::format_string<T...> f,T&&... v){return std::format(f,std::forward<T>(v)...);}};
int main(){
 AVFrame* frame=av_frame_alloc();auto* hdr=av_dynamic_hdr_plus_create_side_data(frame);assert(hdr);
 hdr->itu_t_t35_country_code=0xb5;hdr->application_version=1;hdr->num_windows=1;
 hdr->targeted_system_display_maximum_luminance={4000,1};
 for(auto& m:hdr->params[0].maxscl)m={1,10};
 hdr->params[0].average_maxrgb={0,1};hdr->params[0].fraction_bright_pixels={0,1};
 Layer layer;layer.hdr.min_luma=.01;layer.hdr.max_luma=1000;
 layer.sourceSideData=VideoSourceSideData::Capture(9,7,AV_CODEC_ID_HEVC,frame,nullptr);
 assert(layer.sourceSideData&&layer.sourceSideData->HDR10Plus()&&!layer.sourceSideData->RejectedSections());
 assert(layer.sourceSideData->JSON().find("hdr10plus")!=std::string::npos);
 dvbridge_gl_frame importedFrame{};unsigned used=99;
 assert(ImportDVLayer(&importedFrame,nullptr,layer,&used)&&used==3);
 VideoProcessingInfo data;data.output.flags=32;data.output.effective=8;data.output.sdrHDRInputUsed=used;
 data.sourceMin=.01;data.sourceMax=1000;
 std::map<std::string,bool> facts;std::map<std::string,std::string> text;
 auto SetProperty=[&]<class T>(const char* k,const T& v){if constexpr(std::is_same_v<T,bool>)facts[k]=v;else text[k]=v;};
 const auto active=data.output.flags;
 GUIDANCE
 assert(facts["DV.UsedHDRStatic"]&&!facts["DV.UsedHDR10PlusMax"]&&!facts["DV.UsedHDR10PlusAvg"]);
 assert(text["DV.UsedHDRMax"]=="1000 nits"&&text["DV.UsedHDR10PlusMaxRGB"].empty());
 av_frame_free(&frame);
}
'''.replace('IMPORTER',importer).replace('GUIDANCE',guidance).replace(
            'FRAME_HEADER',str(repo/'CB1/src/dvbridge_gl_frame.h')).replace(
            'STATS_HEADER',str(repo/'CB1/src/cb1_hdr10plus_dovi.h'))
        with tempfile.TemporaryDirectory() as tmp:
            adapter=Path(tmp)/'adapter.o'
            build=subprocess.run(['cc','-std=c11','-I'+os.environ['FFMPEG_TEST_PREFIX']+'/include',
                '-I'+str(repo/'CB1/src'),'-c',str(repo/'CB1/src/cb1_hdr10plus_dovi.c'),'-o',str(adapter)],
                capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            env=dict(os.environ)
            prefix=env['FFMPEG_TEST_PREFIX']
            env['PKG_CONFIG_PATH']=prefix+'/lib/pkgconfig:'+env.get('PKG_CONFIG_PATH','')
            flags=shlex.split(subprocess.check_output(['pkg-config','--cflags','--libs','libplacebo'],env=env,text=True))
            libdir=subprocess.check_output(['pkg-config','--variable=libdir','libplacebo'],env=env,text=True).strip()
            SideDataTests().compile_run(program,objects=(adapter,*flags,'-Wl,-rpath,'+libdir))




if __name__ == '__main__':
    unittest.main()
