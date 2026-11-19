/* SPDX-License-Identifier: MIT */
/* Private experiment adapter: source bodies are extracted verbatim from the
 * immutable native replay before compilation. No production test API. */
#include "cores/VideoSourceSideData.h"
#include "cores/VideoPlayer/DVDCodecs/Video/DVMetadataBuffer.h"
#include <cassert>
extern "C" {
#include "dvbridge_gl_frame.h"
#include "dvbridge_placebo.h"
#include "cb1_hdr10plus_dovi.h"
}
struct CDVBridgeGLES {
    struct Layer {
        dvbridge_gl_layout layout;
        int width,height;
        dvbridge_gl_plane planes[3];
        AVChromaLocation chromaLocation=AVCHROMA_LOC_LEFT;
        DVBRIDGE::SourceInfo sourceInfo{};
        DVBRIDGE::SourceBinding binding{1,1,1};
        pl_hdr_metadata hdr{};
        bool hlg=false,fullRange=false;
        uint64_t sourceSerial=7;
        std::shared_ptr<const VideoSourceSideData> sourceSideData;
    };
};
pl_chroma_location SourceChroma(AVChromaLocation source,unsigned profile) SOURCE_CHROMA_BODY
bool ImportDVLayer(dvbridge_gl_frame* frame,pl_gpu gpu,const CDVBridgeGLES::Layer& layer,
                   unsigned* hdrInputUsed=nullptr) IMPORT_BODY

extern "C" bool raw_native_import(dvbridge_gl_frame* out,pl_gpu gpu,dvbridge_gl_layout layout,
    int width,int height,const dvbridge_gl_plane planes[3],unsigned metadataCase,
    bool fullRange,unsigned chroma,unsigned* used)
{
    CDVBridgeGLES::Layer layer{};layer.layout=layout;layer.width=width;layer.height=height;
    for(unsigned i=0;i<3;i++)layer.planes[i]=planes[i];
    layer.fullRange=fullRange;layer.chromaLocation=static_cast<AVChromaLocation>(chroma);
    layer.sourceInfo.informationGeneration=9;
    layer.hdr.min_luma=.01;layer.hdr.max_luma=1000;
    if(metadataCase==1){layer.hdr.max_luma=0;layer.hdr.max_cll=900;}
    if(metadataCase==2)layer.hdr={};
    if(metadataCase==9)layer.hdr.max_fall=5000;
    if(metadataCase==10)layer.hdr.min_luma=1000;
    if(metadataCase==100)layer.sourceInfo.profile=7;
    AVFrame* frame=av_frame_alloc();assert(frame);
    if(metadataCase>=3&&metadataCase<=8){
        auto* hdr=av_dynamic_hdr_plus_create_side_data(frame);assert(hdr);
        hdr->itu_t_t35_country_code=0xb5;hdr->application_version=1;hdr->num_windows=metadataCase==6?2:1;
        hdr->targeted_system_display_maximum_luminance={4000,1};
        for(unsigned c=0;c<3;c++)hdr->params[0].maxscl[c]={static_cast<int>(c+1),10};
        hdr->params[0].average_maxrgb={metadataCase==4?0:1,20};
        hdr->params[0].fraction_bright_pixels={0,1};
        if(metadataCase==5){
            hdr->params[0].maxscl[0]={0,1};
            hdr->params[0].num_distribution_maxrgb_percentiles=1;
            hdr->params[0].distribution_maxrgb[0].percentage=99;
            hdr->params[0].distribution_maxrgb[0].percentile={1,5};
        }
    }
    layer.sourceSideData=VideoSourceSideData::Capture(9,7,AV_CODEC_ID_HEVC,frame,nullptr);
    assert(layer.sourceSideData);
    if(metadataCase==6)assert(layer.sourceSideData->RejectedSections()&4);
    if(metadataCase==7)layer.sourceSerial=8;
    if(metadataCase==8)layer.sourceInfo.informationGeneration=10;
    bool ok=ImportDVLayer(out,gpu,layer,used);
    if(ok){
        assert(out->frame.repr.alpha==PL_ALPHA_UNKNOWN);
        for(int p=0;p<out->frame.num_planes;p++)for(int c=0;c<out->frame.planes[p].components;c++)
            assert(out->frame.planes[p].component_mapping[c]!=PL_CHANNEL_A);
        if(metadataCase==0||metadataCase==4||metadataCase==6||metadataCase==7||metadataCase==8||metadataCase==9)assert(*used==3);
        if(metadataCase==1)assert(*used==5);
        if(metadataCase==2||metadataCase==10||metadataCase==100)assert(*used==0);
        if(metadataCase==3||metadataCase==5){
            assert(*used==25&&out->frame.color.hdr.scene_avg==500);
            assert(out->frame.color.hdr.scene_max[0]==(metadataCase==5?2000:1000));
        }
    }
    av_frame_free(&frame);return ok;
}
