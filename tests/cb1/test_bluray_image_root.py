"""Exercise native Open path selection before handing the disc to libbluray."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class BlurayImageRoot(unittest.TestCase):
    def test_menu_and_direct_images_share_a_playlist_readable_vfs_root(self):
        source = (TREE / 'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp').read_text()
        opening = body(source, 'bool CDVDInputStreamBluray::Open()')
        opening = opening.split('  // root should not have trailing slash', 1)[0]
        # The fixture models URL protocol/host boundaries, not URL escaping. Open's
        # native branches decide whether to construct UDF and which host to use.
        program = r'''
#include <cassert>
#include <string>
#include <vector>
constexpr int STARTOFFSET_RESUME = -1;
struct CURL {
 std::string protocol, host, file;
 CURL(std::string path) {
  auto colon=path.find("://");
  if(colon==std::string::npos) {file=path;return;}
  protocol=path.substr(0,colon);file=path.substr(colon+3);
  if(protocol=="udf" || protocol=="bluray") {
   if(file.starts_with("{")) {
    auto end=file.rfind('}');host=file.substr(1,end-1);file=file.substr(end+1);
   }
  }
 }
 bool IsProtocol(const std::string& p)const{return protocol==p;}
 std::string GetHostName()const{return host;}
 std::string GetFileName()const{return file;}
 void SetHostName(const std::string& h){host=h;}
 std::string Get()const{return protocol+"://{"+host+"}/";}
};
namespace URIUtils {
bool IsProtocol(const std::string& s,const std::string& p){return CURL(s).IsProtocol(p);}
std::string GetFileName(const std::string& s){return s.substr(s.find_last_of('/')+1);}
std::string GetDirectory(const std::string& s){return s.substr(0,s.find_last_of('/')+1);}
void RemoveSlashAtEnd(std::string& s){if(!s.empty()&&s.back()=='/')s.pop_back();}
}
struct StringUtils {static bool EqualsNoCase(const std::string& a,const std::string& b){return a==b;}};
struct CFileItem {
 std::string path;int offset=0;bool resume=false;
 CFileItem(std::string p):path(p){} CFileItem(const CURL& u,bool):path(u.protocol.empty()?u.file:u.protocol+"://"+u.file){}
 std::string GetDynPath()const{return path;}
 void SetPath(const std::string& s){path=s;}
 bool IsDiscImage()const{auto file=path.substr(0,path.find('?'));return file.ends_with(".iso") || file.ends_with(".img");}
 int GetStartOffset()const{return offset;}bool IsResumable()const{return resume;}
};
namespace VIDEO {bool IsProtectedBlurayDisc(const CFileItem& item){return item.path=="/dev/sr0";}}
struct Disc {
 void* m_player=this;CFileItem m_item;std::string m_vfsRoot;std::vector<std::string> opened;
 bool streamOK=true;
 Disc(std::string p):m_item(p){}
 bool OpenStream(const CFileItem& item){opened.push_back(item.GetDynPath());return streamOK;}
 bool Open() OPENING
 return true;}
};
int main(){
 for(const std::string image:{"http://media:19453/1.iso","/media/Film avec espaces.iso","smb://server/share/disc.img","http://media/100%25 film.iso?test=1"}){
  const std::string udf="udf://{"+image+"}/";
  for(const std::string entry:{image,"bluray://{"+image+"}/menu","bluray://{"+udf+"}/menu"}){
   Disc disc(entry);assert(disc.Open());
   assert(disc.opened==std::vector<std::string>{image});
   assert(disc.m_vfsRoot==udf && "Image menu entry must retain UDF for Kodi's MPLS reader");
  }
 }
 const std::string nested="udf://{/media/outer.iso}/inner.iso";
 Disc inner(nested);assert(inner.Open());assert(inner.opened==std::vector<std::string>{nested});
 assert(inner.m_vfsRoot=="udf://{"+nested+"}/");
 Disc folder("/media/disc/BDMV/PLAYLIST/00800.mpls");assert(folder.Open());
 assert(folder.opened.empty() && folder.m_vfsRoot=="/media/disc");
 Disc selected("bluray://{udf://{http://media/1.iso}/}/BDMV/PLAYLIST/00800.mpls");
 assert(selected.Open() && selected.opened.empty());assert(selected.m_vfsRoot=="udf://{http://media/1.iso}/");
 Disc resume("bluray://{udf://{http://media/1.iso}/}/menu");
 resume.m_item.offset=STARTOFFSET_RESUME;resume.m_item.resume=true;
 assert(resume.Open() && resume.opened.empty());assert(resume.m_vfsRoot=="udf://{http://media/1.iso}/");
 Disc failed("bluray://{http://media/1.iso}/menu");failed.streamOK=false;assert(!failed.Open());
 Disc physical("/dev/sr0");assert(physical.Open() && physical.opened.empty());
}
'''.replace('OPENING', opening)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / 'test.cpp').write_text(program)
            built = subprocess.run(['c++', '-std=c++20', '-fsanitize=address,undefined',
                                    str(root / 'test.cpp'), '-o', str(root / 'test')],
                                   capture_output=True, text=True)
            self.assertEqual(built.returncode, 0, built.stderr)
            result = subprocess.run([str(root / 'test')], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
