"""Run the shipped RPU level capture and the formatting behind the added Player information rows."""
from pathlib import Path
import os
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
 // The panel follows its tallest column until the top margin, then cuts the columns.
 const auto fit=FitPanel(700,1080);
 assert(fit.height==824 && fit.top==232 && fit.columns==570);
 const auto full=FitPanel(1100,1080);
 assert(full.height==1032 && full.top==24 && full.columns==778);
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
 add(1)->l1.max_pq=3079;
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
 assert(info.metadata && info.cm4 && info.compatibility==1);
 const auto& levels=info.levels;
 // At most eight trim passes are kept, in stream order.
 assert(levels.l2Count==8 && levels.l2[0]==2000 && levels.l2[7]==2007);
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

    def test_hdr10plus_rows_skip_dolby_vision_rendered_by_cb1(self):
        self.assertRegex(DIALOG.read_text(), r'if \(!\(active && data\.profile && !data\.output\.hdr10AI\)\)\s*'
                         r'side = CServiceBroker::GetDataCacheCore\(\)\.GetVideoSourceSideDataSnapshot\(\);')


if __name__ == '__main__':
    unittest.main()
