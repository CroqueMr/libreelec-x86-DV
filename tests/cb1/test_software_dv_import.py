"""Software-decoded DV reuses Kodi's uploaded planar textures."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE,body


class SoftwareDVImportTests(unittest.TestCase):
    def test_planar_ten_bit_frame_is_admitted_before_output_selection(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/LinuxRendererGLES.cpp').read_text()
        upload=body(source,'bool CLinuxRendererGLES::UploadTexture(')
        build=body(source,'bool CLinuxRendererGLES::BuildDVBridgeLayer(') if \
            'bool CLinuxRendererGLES::BuildDVBridgeLayer(' in source else '{return false;}'
        program=r'''
#include <cassert>
#include <cmath>
#include <memory>
#define HAVE_DVBRIDGE
constexpr int AV_PIX_FMT_YUV420P10LE=1,AV_PIX_FMT_YUV444P10LE=2,
 AV_PIX_FMT_NV12=3,AV_PIX_FMT_YUYV422=4,AV_PIX_FMT_UYVY422=5,
 GL_TEXTURE_2D=6,FIELD_FULL=0,DVBRIDGE_YUV420P10=7,DVBRIDGE_YUV444P10=8;
constexpr double DVD_NOPTS_VALUE=-1,DVD_TIME_BASE=1000000,AV_NOPTS_VALUE=-2;
enum class StreamHdrType {HDR_TYPE_DOLBYVISION,HDR_TYPE_HDR10,HDR_TYPE_HDR10PLUS};
double av_q2d(double value){return value;}
struct SourceInfo{int profile=8;};
struct Side{unsigned Serial()const{return 1;}};
struct HDR{double max_luma{},min_luma{},max_cll{},max_fall{};};
struct Binding{int picture=0;bool Valid()const{return picture>0;}};
struct Metadata{const char* Data()const{return "dv";}::Binding Binding()const{return {1};}};
struct Picture{SourceInfo doviSourceInfo;std::shared_ptr<Side> sourceSideData;int chroma_position{};::Binding doviSourceBinding{1};
 StreamHdrType hdrType=StreamHdrType::HDR_TYPE_DOLBYVISION;double pts=1000000,doviSourcePts=1000000;
 int color_range{};bool hasDisplayMetadata{},hasLightMetadata{};
 struct{bool has_luminance{};double max_luminance{},min_luminance{};}displayMetadata;
 struct{unsigned MaxCLL{},MaxFALL{};}lightMetadata;};
struct Plane{unsigned id,texwidth,texheight;};
struct YuvImage{int plane[3]{},stride[3]{};};
struct VideoBuffer{void GetPlanes(int*){} void GetStrides(int*){}};
struct Buffer{std::shared_ptr<Picture>doviSourcePicture=std::make_shared<Picture>();
 std::shared_ptr<VideoBuffer>videoBuffer=std::make_shared<VideoBuffer>();
 Metadata doviMetadata;double doviPts=100;bool loaded=false;YuvImage image;
 Plane fields[1][3]={{{11,3840,1920},{12,1920,960},{13,1920,960}}};};
struct CDVBridgeGLES{struct Layer{int layout{},scalingMethod{},width{},height{};
 double pts{};::Binding binding{};std::shared_ptr<void>lease;SourceInfo sourceInfo;std::shared_ptr<Side> sourceSideData;unsigned sourceSerial{};int chromaLocation{};bool fullRange{},hdr10PlusSource{};HDR hdr;
 struct{unsigned texture;int width,height;}planes[3]{};};};
struct WindowBase{virtual ~WindowBase()=default;};
namespace KODI::WINDOWING::GBM{struct CWinSystemGbmGLESContext:WindowBase{
 int observed{};bool usable{};::Binding last{};
 void ObserveDVImport(::Binding binding,int,bool value){observed++;usable=value;last=binding;}};}
KODI::WINDOWING::GBM::CWinSystemGbmGLESContext window;
struct CServiceBroker{static WindowBase*GetWinSystem(){return &window;}};
struct CLinuxRendererGLES{
 int m_format=AV_PIX_FMT_YUV420P10LE,m_textureTarget=GL_TEXTURE_2D;
 int m_sourceWidth=3840,m_sourceHeight=1920,m_renderOrientation{};
 Buffer m_buffers[1];int uploads{};
 bool UploadNV12Texture(int){return false;} bool UploadPackedYUVTexture(int){return false;}
 bool UploadPlanarYUVTexture(int){uploads++;return true;}
 void CalculateTextureSourceRects(int,int){} int SelectScalingMethod(){return 9;}
 int DVBridgeGeometry(){return 42;}
 bool BuildDVBridgeLayer(int index,CDVBridgeGLES::Layer& layer) BUILD
 bool UploadTexture(int index) UPLOAD
};
int main(){CLinuxRendererGLES r;
 assert(r.UploadTexture(0));assert(r.uploads==1);
 assert(window.observed==1 && window.usable);
 CDVBridgeGLES::Layer layer;assert(r.BuildDVBridgeLayer(0,layer));
 assert(layer.layout==DVBRIDGE_YUV420P10 && layer.width==3840 && layer.height==1920);
 assert(layer.planes[0].texture==11 && layer.planes[1].texture==12 && layer.planes[2].texture==13);
 assert(layer.planes[1].width==1920 && layer.planes[1].height==960);
 assert(layer.lease && layer.binding.Valid() && layer.pts==100 && !layer.hdr10PlusSource);
 assert(r.UploadTexture(0) && r.uploads==1 && window.observed==2);
 r.m_format=AV_PIX_FMT_YUV444P10LE;
 r.m_buffers[0].fields[0][1]={12,3840,1920};r.m_buffers[0].fields[0][2]={13,3840,1920};
 assert(r.BuildDVBridgeLayer(0,layer) && layer.layout==DVBRIDGE_YUV444P10);
 r.m_format=AV_PIX_FMT_NV12;assert(!r.BuildDVBridgeLayer(0,layer));
 r.m_format=AV_PIX_FMT_YUV420P10LE;r.m_renderOrientation=90;
 assert(!r.BuildDVBridgeLayer(0,layer));
 assert(r.UploadTexture(0) && !window.usable && window.last.Valid());
 r.m_renderOrientation=0;r.m_sourceWidth=320;r.m_sourceHeight=181;
 r.m_buffers[0].fields[0][0]={11,320,181};
 r.m_buffers[0].fields[0][1]={12,160,90};r.m_buffers[0].fields[0][2]={13,160,90};
 assert(!r.BuildDVBridgeLayer(0,layer));
 assert(r.UploadTexture(0) && !window.usable && window.last.Valid());
 r.m_sourceHeight=180;r.m_buffers[0].fields[0][0]={11,320,180};
 assert(r.UploadTexture(0) && window.usable && window.last.Valid());
 r.m_renderOrientation=0;r.m_buffers[0].doviPts=DVD_NOPTS_VALUE;
 assert(!r.BuildDVBridgeLayer(0,layer));
 auto& source=*r.m_buffers[0].doviSourcePicture;
 source.doviSourceInfo.profile=0;source.hdrType=StreamHdrType::HDR_TYPE_HDR10;
 source.hasDisplayMetadata=true;source.displayMetadata.has_luminance=true;source.displayMetadata.max_luminance=1000;
 assert(r.BuildDVBridgeLayer(0,layer) && layer.pts==1 && layer.hdr.max_luma==1000 && !layer.hdr10PlusSource);
 source.hdrType=StreamHdrType::HDR_TYPE_HDR10PLUS;
 assert(r.BuildDVBridgeLayer(0,layer) && layer.hdr10PlusSource);
 source.hdrType=StreamHdrType::HDR_TYPE_HDR10;
 assert(r.BuildDVBridgeLayer(0,layer) && !layer.hdr10PlusSource);
 source.doviSourcePts=AV_NOPTS_VALUE;assert(!r.BuildDVBridgeLayer(0,layer));}
'''.replace('BUILD',build).replace('UPLOAD',upload)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'check.cpp').write_text(program)
            compiled=subprocess.run(['c++','-std=c++20','-Wall','-Wextra','-Werror',
                '-Wno-unused-parameter',str(root/'check.cpp'),'-o',str(root/'check')],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            run=subprocess.run([str(root/'check')],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__':unittest.main()
