/* Native source-owner slices, inserted verbatim by the test loader. */
extern "C" {
#include <libavcodec/avcodec.h>
#include <libavformat/avformat.h>
#include <libavutil/mastering_display_metadata.h>
#include "dvbridge_metadata_bounds.h"
#include "task3_fixture.h"
}
constexpr int LOGWARNING=2,DVP_FLAG_DROPPED=1;
struct CLog {template<class...T>static void Log(T...){}};
enum class StreamHdrType {HDR_TYPE_DOLBYVISION,HDR_TYPE_HDR10,HDR_TYPE_HLG};
struct Picture {
 CDVMetadataBuffer doviMetadata;DVBRIDGE::SourceBinding doviSourceBinding;DVBRIDGE::SourceInfo doviSourceInfo;
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;
 int colorBits=10;bool hasLightMetadata=false,hasDisplayMetadata=false;
 AVContentLightMetadata lightMetadata{};AVMasteringDisplayMetadata displayMetadata{};
 int64_t doviSourcePts{};std::string strDVELType;unsigned iFlags{};
 std::shared_ptr<const VideoSourceSideData>sourceSideData;
};
static void admitted(AVStream *bl,AVStream *el,bool transport){
 bool normalize=true;std::unique_ptr<AVCodecParameters,void(*)(AVCodecParameters*)> combined(avcodec_parameters_alloc(),[](AVCodecParameters*p){avcodec_parameters_free(&p);});
 struct Join {AVCodecParameters*p;bool Configure(AVCodecParameters*,AVCodecParameters*,AVRational,AVRational,bool){return true;}AVCodecParameters*BaseParameters(){return p;}}instance{bl->codecpar},*join=&instance;
 auto report=[](const char*){};
 @ADMISSION@
 assert(avcodec_parameters_copy(bl->codecpar,combined.get())==0);
}
static AVDOVIDecoderConfigurationRecord copied(AVStream*pStream){
 struct {AVDOVIDecoderConfigurationRecord dovi{};}storage,*st=&storage;
 const AVPacketSideData*sideData=nullptr;
 @DEMUX_COPY@
 struct {AVDOVIDecoderConfigurationRecord dovi{};} hints;
 auto*stream=st;auto&dovi=hints.dovi;
 @HINTS_COPY@
 return hints.dovi;
}
static void decoded(Picture*pVideoPicture,AVFrame*m_pFrame,AVDOVIDecoderConfigurationRecord config,unsigned generation,bool joined=true){
 struct {AVDOVIDecoderConfigurationRecord dovi;}m_hints{config};
 DVBRIDGE::SourceOwner m_dvSourceOwner;m_dvSourceOwner.BeginStream();
 unsigned m_videoProcessingGeneration=generation;bool m_dvLayerEpoch=joined,m_dvVideoWindow=true;
 static int presentableDVPacket,decodeOnlyDVPacket;
 if(!m_pFrame->opaque)m_pFrame->opaque=&presentableDVPacket;
 AVFrameSideData*sd=nullptr;
 @DECODED@
}
static CDVBridgeGLES::Layer copied_layer(std::shared_ptr<Picture>picture){
 struct {std::shared_ptr<Picture>doviSourcePicture;CDVMetadataBuffer doviMetadata;}buffer{picture,picture->doviMetadata};
 const auto&source=*picture;bool hdr10=!source.doviSourceInfo.profile;
 CDVBridgeGLES::Layer layer{};
 @LAYER_BINDING@
 @LAYER_COPY@
 layer.pts=1;return layer;
}
static void provenance(){
 size_t bytes;auto*m=task3_fixture(&bytes);unsigned positive=0,negative=0;
 for(bool supplied:{false,true}){
  AVStream bl{},el{};bl.codecpar=avcodec_parameters_alloc();el.codecpar=avcodec_parameters_alloc();
  if(supplied){auto*sd=av_packet_side_data_new(&el.codecpar->coded_side_data,&el.codecpar->nb_coded_side_data,AV_PKT_DATA_DOVI_CONF,sizeof(AVDOVIDecoderConfigurationRecord),0);assert(sd);auto*c=reinterpret_cast<AVDOVIDecoderConfigurationRecord*>(sd->data);*c={};c->dv_profile=7;c->rpu_present_flag=c->el_present_flag=1;}
  admitted(&bl,&el,true);auto config=copied(&bl);assert(config.dv_profile==7&&config.rpu_present_flag&&config.el_present_flag&&config.bl_present_flag);
  for(int bad=0;bad<8;bad++){
   auto picture=std::make_shared<Picture>();AVFrame*frame=av_frame_alloc();frame->pts=frame->best_effort_timestamp=1;
   auto*sd=av_frame_new_side_data(frame,AV_FRAME_DATA_DOVI_METADATA,bytes);assert(sd);memcpy(sd->data,m,bytes);
   if(bad!=1){auto*raw=av_frame_new_side_data(frame,AV_FRAME_DATA_DOVI_RPU_BUFFER,5);assert(raw);raw->data[0]=bad==2?0:25;raw->data[1]=8;}
   if(bad==3)frame->flags|=AV_FRAME_FLAG_CORRUPT;
   if(bad==4)frame->pts=AV_NOPTS_VALUE;
   if(bad==5)frame->decode_error_flags=1;
   if(bad==6)frame->opaque=reinterpret_cast<void*>(1);
   if(bad==7)reinterpret_cast<AVDOVIMetadata*>(sd->data)->header_offset=bytes+1;
   decoded(picture.get(),frame,config,19);auto layer=copied_layer(picture);
   CDVBridgeGLES r;setup(r);DVBRIDGE::OutputPreferences prefs;prefs.output=DVBRIDGE::OutputMode::SDR;prefs.revision=23;auto policy=prefs.Policy();
   auto before=directCalls;dvbridge_geometry g{8,8,0,0,8,8,8,8};
   auto result=r.PrepareFrame(layer,nullptr,picture->doviMetadata,g,prefs,true,&policy,false);
   if(!bad){assert(result==CDVBridgeGLES::FrameStatus::Ready&&directCalls==before+1&&layer.sourceInfo.informationGeneration==19);++positive;}
   else{assert(result==CDVBridgeGLES::FrameStatus::Failed&&directCalls==before);++negative;}
   av_frame_free(&frame);
  }
  avcodec_parameters_free(&bl.codecpar);avcodec_parameters_free(&el.codecpar);
 }
 for(auto type:{StreamHdrType::HDR_TYPE_HDR10,StreamHdrType::HDR_TYPE_HLG}){
  auto picture=std::make_shared<Picture>();picture->hdrType=type;AVFrame*f=av_frame_alloc();f->pts=1;
  decoded(picture.get(),f,{},20,false);auto layer=copied_layer(picture);layer.hlg=type==StreamHdrType::HDR_TYPE_HLG;
  // Generated RPU work retains the original decoder's profile0 facts.
  layer.binding={99,1,1};CDVMetadataBuffer generated;assert(generated.Assign(reinterpret_cast<const uint8_t*>(m),bytes,layer.binding));
  CDVBridgeGLES r;setup(r);DVBRIDGE::OutputPreferences prefs;prefs.output=DVBRIDGE::OutputMode::SDR;prefs.revision=23;auto p=prefs.Policy();
  auto before=directCalls;assert(r.PrepareFrame(layer,nullptr,generated,{8,8,0,0,8,8,8,8},prefs,true,&p,false)==CDVBridgeGLES::FrameStatus::Ready);
  assert(directCalls==before&&layer.sourceInfo.profile==0);++negative;av_frame_free(&f);
 }
 av_free(m);assert(positive==2&&negative==16);
 std::cout<<"COMPLETE provenance 2 positive 16 negative controls\n";
}
static void raw_sources(){
 unsigned cases=0;
 for(unsigned metadataCase=0;metadataCase<11;metadataCase++){
  CDVBridgeGLES::Layer layer{};layer.binding={8,metadataCase+1,3};layer.pts=1;
  layer.lease=std::make_shared<int>(1);layer.sourceInfo.informationGeneration=9;layer.sourceSerial=7;
  layer.hdr.min_luma=.01;layer.hdr.max_luma=1000;
  if(metadataCase==1){layer.hdr.max_luma=0;layer.hdr.max_cll=900;}
  if(metadataCase==2)layer.hdr={};
  if(metadataCase==9)layer.hdr.max_fall=5000;
  if(metadataCase==10)layer.hdr.min_luma=1000;
  AVFrame*frame=av_frame_alloc();assert(frame);
  if(metadataCase>=3&&metadataCase<=8){
   auto*hdr=av_dynamic_hdr_plus_create_side_data(frame);assert(hdr);
   hdr->itu_t_t35_country_code=0xb5;hdr->application_version=1;hdr->num_windows=metadataCase==6?2:1;
   hdr->targeted_system_display_maximum_luminance={4000,1};
   for(unsigned c=0;c<3;c++)hdr->params[0].maxscl[c]={static_cast<int>(c+1),10};
   hdr->params[0].average_maxrgb={metadataCase==4?0:1,20};hdr->params[0].fraction_bright_pixels={0,1};
   if(metadataCase==5){hdr->params[0].maxscl[0]={0,1};hdr->params[0].num_distribution_maxrgb_percentiles=1;
    hdr->params[0].distribution_maxrgb[0].percentage=99;hdr->params[0].distribution_maxrgb[0].percentile={1,5};}
  }
  layer.sourceSideData=VideoSourceSideData::Capture(9,7,AV_CODEC_ID_HEVC,frame,nullptr);assert(layer.sourceSideData);
  if(metadataCase==6)assert(layer.sourceSideData->RejectedSections()&4);
  if(metadataCase==7)layer.sourceSerial=8;
  if(metadataCase==8)layer.sourceInfo.informationGeneration=10;
  CDVBridgeGLES r;setup(r);DVBRIDGE::OutputPreferences prefs;prefs.output=DVBRIDGE::OutputMode::SDR;prefs.hdr10Source=DVBRIDGE::HDR10SourceMode::SDR;prefs.revision=23;auto policy=prefs.Policy();
  auto before=directCalls;CDVMetadataBuffer empty;
  assert(r.PrepareFrame(layer,nullptr,empty,{8,8,0,0,8,8,8,8},prefs,true,&policy,false)==CDVBridgeGLES::FrameStatus::Ready);
  assert(directCalls==before+1&&r.ResolveHDR10(false)&&r.Presented(true,r.m_submission));
  const auto&out=DVBRIDGE::StreamTelemetry::accepted.output;
  unsigned used=metadataCase==1?5:metadataCase==2||metadataCase==10?0:metadataCase==3||metadataCase==5?25:3;
  assert(out.sdrHDRInputUsed==used&&out.effective==8&&out.requested==8);
  if(metadataCase==3||metadataCase==5)assert(out.sdrHDRInputValues[0]==(metadataCase==5?2000:1000)&&out.sdrHDRInputValues[3]==500);
  av_frame_free(&frame);++cases;
 }
 assert(cases==11);std::cout<<"COMPLETE actual Capture/Import/Presented 11 raw metadata controls\n";
}
