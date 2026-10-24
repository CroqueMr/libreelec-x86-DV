"""Execute the native cache and configuration; double only VA/EGL operations."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE,body


class VAAPIResourceTests(unittest.TestCase):
    def test_producer_exposes_its_pool_without_removing_decode_wait(self):
        source=(TREE/'xbmc/cores/VideoPlayer/DVDCodecs/Video/VAAPI.cpp').read_text()
        block=body(source,'CVaapiRenderPicture* COutput::ProcessPicture(')
        program=r'''
#include <cassert>
#include <vector>
constexpr int VA_STATUS_SUCCESS=0;
constexpr unsigned VA_INVALID_ID=~0u;
constexpr int LOGERROR=1,DVD_NOPTS_VALUE=-1;
struct CLog{template<class...T>static void Log(T&&...){}};
int waited{},failure{};int vaSyncSurface(void*,unsigned surface){assert(surface==17);++waited;return failure;}
struct AVFrame{int pixels{};};
void av_frame_move_ref(AVFrame* to,AVFrame* from){to->pixels=from->pixels;from->pixels=0;}
struct VideoPicture{int dts{},iWidth{},iHeight{};void SetParams(const VideoPicture& p){*this=p;}};
struct CVaapiProcessedPicture;
struct Source{bool hardware{true};int cleared{};bool UseVideoSurface(){return hardware;}
 void ClearRef(CVaapiProcessedPicture&){++cleared;}};
struct CVaapiProcessedPicture{VideoPicture DVDPic;unsigned videoSurface{17},id{},fourcc{};Source* source{};AVFrame* frame{};};
struct CVaapiRenderPicture{VideoPicture DVDPic;CVaapiProcessedPicture procPic;
 AVFrame storage,*avFrame=&storage;void* vadsp{};unsigned decodeSurfaceCount{};
 bool decodeCompleted{},valid{};int released{};void Release(){++released;}};
struct Output{
 struct{void* dpy{};unsigned maxReferences{38},pixelFormat{10};int vidWidth{3840},vidHeight{2160};}m_config;
 struct Pool{unsigned procPicId{};std::vector<CVaapiProcessedPicture>processedPicsAway;
  CVaapiRenderPicture picture;CVaapiRenderPicture* GetVaapi(){return &picture;}}pool,*m_bufferPool=&pool;
 CVaapiRenderPicture* ProcessPicture(CVaapiProcessedPicture& pic) @@BLOCK@@
};
int main(){
 Output output;Source source;AVFrame frame{123};CVaapiProcessedPicture pic;pic.source=&source;pic.frame=&frame;
 auto* current=output.ProcessPicture(pic);
 assert(current && current->decodeSurfaceCount==38 && waited==1 && current->decodeCompleted);
 assert(output.pool.processedPicsAway.size()==1 && current->procPic.videoSurface==17);
 source.hardware=false;assert(output.ProcessPicture(pic)==current);
 assert(!current->decodeCompleted && waited==1 && current->storage.pixels==123 && frame.pixels==0 && source.cleared==1);
 assert(current->valid && current->procPic.videoSurface==VA_INVALID_ID);
 source.hardware=true;failure=1;assert(output.ProcessPicture(pic)==current);
 assert(waited==2 && !current->decodeCompleted);
 failure=0;assert(output.ProcessPicture(pic)==current && current->decodeCompleted);
 pic.source=nullptr;assert(!output.ProcessPicture(pic) && !current->decodeCompleted && current->released==1);
}
'''.replace('@@BLOCK@@',block)
        self.run_native(program)

    def test_borrowed_import_keeps_the_current_surface_wait(self):
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/VaapiEGL.cpp').read_text()
        code=body(source,'bool CVaapi2Texture::Import(CVaapiRenderPicture* pic, const VADRMPRIMESurfaceDescriptor& surface)')
        code=code[:code.index('  m_textureSize.Set')]+ '\nreturn true;}'
        program=r'''
#include <cassert>
constexpr int VA_STATUS_SUCCESS=0,LOGERROR=1;using VAStatus=int;
struct CLog{template<class...T>static void Log(T&&...){}};
const char* vaErrorStr(int){return "error";}
int waited{},failure{};int vaSyncSurface(void*,unsigned surface){assert(surface==17);++waited;return failure;}
struct CVaapiRenderPicture{void* vadsp{};struct{unsigned videoSurface{17};}procPic;bool decodeCompleted{};};
struct VADRMPRIMESurfaceDescriptor{unsigned num_objects{2},num_layers{2};};
struct Texture{bool m_imported{};int resets{};void Reset(){++resets;m_imported=false;}
 bool Import(CVaapiRenderPicture* pic,const VADRMPRIMESurfaceDescriptor& surface) @@CODE@@
};
int main(){Texture texture;CVaapiRenderPicture pic;VADRMPRIMESurfaceDescriptor surface;
 assert(texture.Import(&pic,surface) && waited==1 && !texture.resets);
 pic.decodeCompleted=true;assert(texture.Import(&pic,surface) && waited==1);
 pic.decodeCompleted=false;
 failure=1;assert(!texture.Import(&pic,surface) && waited==2 && texture.resets==1);
 failure=0;surface.num_objects=5;assert(!texture.Import(&pic,surface) && waited==2 && texture.resets==2);
}
'''.replace('@@CODE@@',code)
        self.run_native(program)

    def run_native(self,program):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'test.cpp').write_text(program)
            built=subprocess.run(['c++','-std=c++20',str(root/'test.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)

    def test_real_pool_retains_views_and_current_decode_wait(self):
        renderer=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/RendererVAAPIGLES.cpp').read_text()
        configure=body(renderer,'bool CRendererVAAPIGLES::Configure(')
        configure=configure[configure.index('m_texturePool.ReleaseAll();'):configure.index('for (auto& tex : m_vaapiTextures)')]
        source=(TREE/'xbmc/cores/VideoPlayer/VideoRenderers/HwDecRender/VaapiEGL.cpp').read_text()
        get=body(source,'CVaapi2Texture* CVaapiTexturePool::Get(')
        init=body(source,'void CVaapiTexturePool::Init(')
        release=body(source,'void CVaapiTexturePool::ReleaseAll(')
        program=r'''
#include "cores/VideoPlayer/Buffers/DmaBufIdentityCache.h"
#include <algorithm>
#include <array>
#include <cassert>
#include <memory>
#include <set>
#include <span>
#include <vector>
#define CB1_HAS_HDR10_AI 1
#define HAVE_DVBRIDGE 1
constexpr int LOGWARNING=0,LOGERROR=1,VA_STATUS_SUCCESS=0;
constexpr int VA_SURFACE_ATTRIB_MEM_TYPE_DRM_PRIME_2=1;
constexpr int VA_EXPORT_SURFACE_READ_ONLY=2,VA_EXPORT_SURFACE_SEPARATE_LAYERS=4;
struct CLog{template<class...T> static void Log(T&&...){}};
struct InteropInfo{};
struct CVaapiRenderPicture{void* vadsp{};unsigned decodeSurfaceCount{38};bool decodeCompleted{};
 struct{unsigned videoSurface{};}procPic;
 struct{int iWidth{3840},iHeight{2160};}DVDPic;};
struct VADRMPRIMESurfaceDescriptor{unsigned num_objects{2},key{};struct{int fd{-1};}objects[4];};
using VAStatus=int;
int exports{},imports{},waits{},closes{},nextFD{100};bool exportOK=true,importOK=true;
std::set<int> openFDs;
int vaExportSurfaceHandle(void*,unsigned surface,int,int,VADRMPRIMESurfaceDescriptor* out){
 ++exports;if(!exportOK)return 1;out->key=surface;
 for(unsigned i=0;i<out->num_objects;i++){out->objects[i].fd=nextFD++;openFDs.insert(out->objects[i].fd);}return 0;}
int close(int fd){assert(openFDs.erase(fd)==1);++closes;return 0;}
const char* vaErrorStr(int){return "error";}
int vaSyncSurface(void*,unsigned){++waits;return 0;}
namespace KODI::UTILS::POSIX{struct CFileHandle{int fd{-1};void attach(int value){fd=value;}
 ~CFileHandle(){if(fd>=0)close(fd);}};}
std::optional<DRMPRIME::DmaBufIdentity> IdentityFromVaDescriptor(const VADRMPRIMESurfaceDescriptor& d,int w,int h){
 DRMPRIME::DmaBufIdentity value;value.nbObjects=1;value.inode[0]=d.key+1;value.width=w;value.height=h;return value;}
struct CVaapi2Texture{
 void Init(InteropInfo&){}void Reset(){}
 bool Import(CVaapiRenderPicture* pic){
  VADRMPRIMESurfaceDescriptor d;assert(vaExportSurfaceHandle(nullptr,pic->procPic.videoSurface,1,6,&d)==0);
  bool ok=Import(pic,d);for(unsigned i=0;i<d.num_objects;i++)close(d.objects[i].fd);return ok;}
 bool Import(CVaapiRenderPicture* pic,const VADRMPRIMESurfaceDescriptor& d){
  for(unsigned i=0;i<d.num_objects;i++)assert(openFDs.contains(d.objects[i].fd));
  assert(d.key==pic->procPic.videoSurface);++imports;if(!pic->decodeCompleted)vaSyncSurface(nullptr,d.key);return importOK;}
};
using CVaapiTexture=CVaapi2Texture;
class CVaapiTexturePool{
public:
 static constexpr size_t MAX_ENTRIES=32;
 InteropInfo m_interop;DRMPRIME::CDmaBufIdentityCache m_cache{32,"vaapi"};
 std::vector<std::shared_ptr<CVaapi2Texture>>m_entries;std::vector<size_t>m_free;
 void Init(InteropInfo& interop,size_t maxEntries=MAX_ENTRIES) @@INIT@@
 void ReleaseAll() @@RELEASE@@
 CVaapi2Texture* Get(CVaapiRenderPicture* pic,std::span<CVaapiTexture* const> inUse) @@GET@@
};
namespace VAAPI{using CVaapiTexturePool=::CVaapiTexturePool;}
struct Fixture{
 CVaapiTexturePool m_texturePool;unsigned m_aiBuffers{6};static constexpr unsigned NUM_BUFFERS=6;
 void configure(bool dv,unsigned pool,unsigned ai=6){
  assert(openFDs.empty());exports=imports=waits=closes=0;
  InteropInfo interop;CVaapiRenderPicture current,*pic=&current;current.decodeSurfaceCount=pool;
  struct{struct{int profile{};}doviSourceInfo;}picture;picture.doviSourceInfo.profile=dv?7:0;
  m_aiBuffers=ai;
  @@CONFIGURE@@
 }
 void cycle(unsigned count,unsigned rounds){for(unsigned round=0;round<rounds;round++)for(unsigned i=0;i<count;i++){
  CVaapiRenderPicture pic;pic.procPic.videoSurface=i;
  assert(m_texturePool.Get(&pic,{}));assert(openFDs.empty());}}
};
int main(){
 Fixture f;f.configure(true,38);f.cycle(38,2);
 assert(imports==38 && "P7 decoded surfaces must retain imports across a full cycle");
 assert(exports==76 && "One descriptor export per access, including import misses");
 assert(waits==76 && "Cached storage still waits for its current decoded content");
 assert(closes==exports*2 && openFDs.empty());
 {CVaapiRenderPicture pic;pic.decodeCompleted=true;int previous=waits;
  assert(f.m_texturePool.Get(&pic,{}));assert(waits==previous && openFDs.empty());}
 f.configure(false,22);f.cycle(22,2);assert(imports==22 && waits==44);
 f.configure(false,30,14);f.cycle(38,2);assert(imports==38 && waits==76);
 f.configure(false,38);f.cycle(38,2);assert(imports>38 && "Unrelated native cache policy is unchanged");
 f.configure(true,38);importOK=false;CVaapiRenderPicture pic;
 assert(!f.m_texturePool.Get(&pic,{}));assert(openFDs.empty());
 importOK=true;exportOK=false;assert(!f.m_texturePool.Get(&pic,{}));assert(openFDs.empty());
}
'''.replace('@@CONFIGURE@@',configure).replace('@@INIT@@',init).replace('@@RELEASE@@',release).replace('@@GET@@',get)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'utils').mkdir()
            (root/'utils/log.h').write_text('constexpr int LOGWARNING=0; struct CLog {template<class...T>static void Log(T&&...){}};\n')
            (root/'test.cpp').write_text(program)
            buffers=TREE/'xbmc/cores/VideoPlayer/Buffers'
            prefix=Path(os.environ['FFMPEG_TEST_PREFIX'])
            built=subprocess.run(['c++','-std=c++20','-I'+str(root),'-I'+str(TREE/'xbmc'),
                '-I'+str(prefix/'include'),str(root/'test.cpp'),str(buffers/'DmaBufIdentityCache.cpp'),
                str(buffers/'DmaBufIdentity.cpp'),'-o',str(root/'test')],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            ran=subprocess.run([str(root/'test')],capture_output=True,text=True)
            self.assertEqual(ran.returncode,0,ran.stderr)


if __name__=='__main__':unittest.main()
