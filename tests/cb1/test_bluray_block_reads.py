"""Native Blu-ray stream reads must fill sectors across fragmented VFS reads."""
from pathlib import Path
import subprocess
import tempfile
import unittest
from test_native_video_source import TREE, body


class BlurayBlockReads(unittest.TestCase):
    def test_fragmented_reads_and_real_end_of_file(self):
        self.check(False)

    def test_native_buffered_fragmented_reads_and_seek(self):
        self.check(True)

    def check(self,buffered):
        bluray=(TREE/'xbmc/cores/VideoPlayer/DVDInputStreams/DVDInputStreamBluray.cpp').read_text()
        file=(TREE/'xbmc/filesystem/File.cpp').read_text()
        program=r'''
#include <algorithm>
#include <cassert>
#include <climits>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <streambuf>
#include <string>
#include <sys/types.h>
#include <vector>
#define XBMCCOMMONS_HANDLE_UNCHECKED
enum { LOGERROR,LOGWARNING };
struct CLog {template<class... T>static void Log(T&&...){} template<class... T>static void LogF(T&&...){} };
struct CURL {static std::string GetRedacted(const std::string& s){return s;} };
namespace XFILE {enum {READ_TRUNCATED=1,READ_BITRATE=2,READ_NO_CACHE=4};}
using namespace XFILE;
struct Stats {void AddSampleBytes(ssize_t){} };
struct Fragmented {
 std::vector<uint8_t> bytes;size_t position=0;int calls=0;bool seekFailure=false;
 Fragmented():bytes(8192){for(size_t i=0;i<bytes.size();++i)bytes[i]=uint8_t(i*17+3);}
 ssize_t Read(void* out,size_t wanted){++calls;size_t n=std::min({wanted,size_t(511),bytes.size()-position});
  memcpy(out,bytes.data()+position,n);position+=n;return n;}
 int64_t GetPosition(){return position;}int64_t GetLength(){return bytes.size();}
 int64_t Seek(int64_t offset,int way){
  if(seekFailure)return -1;
  int64_t next=offset+(way==SEEK_CUR?int64_t(position):way==SEEK_END?int64_t(bytes.size()):0);
  if(next<0||next>int64_t(bytes.size()))return -1;position=next;return next;}
};
struct CFileStreamBuffer:std::streambuf {
 Fragmented* m_file;char storage[65536];char* m_buffer{storage};int m_backsize=0,m_frontsize=sizeof(storage);
 explicit CFileStreamBuffer(Fragmented* file):m_file(file){setg(nullptr,nullptr,nullptr);}
 int_type underflow() override;std::streamsize showmanyc() override;
 pos_type seekoff(off_type,std::ios_base::seekdir,std::ios_base::openmode) override;
 pos_type seekpos(pos_type,std::ios_base::openmode) override;
};
CFileStreamBuffer::int_type CFileStreamBuffer::underflow() UNDERFLOW
std::streamsize CFileStreamBuffer::showmanyc() SHOWMANY
CFileStreamBuffer::pos_type CFileStreamBuffer::seekoff(off_type offset,std::ios_base::seekdir way,std::ios_base::openmode mode) SEEKOFF
CFileStreamBuffer::pos_type CFileStreamBuffer::seekpos(pos_type pos,std::ios_base::openmode mode) SEEKPOS
struct CFile {
 Fragmented input;Fragmented* m_pFile{&input};std::streambuf* m_pBuffer=nullptr;
 Stats* m_bitStreamStats=nullptr;unsigned m_flags=0;
 ssize_t Read(void*,size_t);
 int64_t Seek(int64_t,int);
};
ssize_t CFile::Read(void* lpBuf,size_t uiBufSize) FILE_READ
int64_t CFile::Seek(int64_t iFilePosition,int iWhence) FILE_SEEK
struct CFileItem {std::string GetPath(){return "test.iso";} };
bool buffered=false;
struct CDVDInputStreamFile {
 CFile file;CFileStreamBuffer buffer{&file.input};
 CDVDInputStreamFile(CFileItem&,unsigned flags){file.m_flags=flags;}
 bool Open(){if(buffered)file.m_pBuffer=&buffer;return true;}
 int64_t Seek(int64_t offset,int way){return file.Seek(offset,way);}
 int Read(uint8_t* out,int count){return int(file.Read(out,count));}
};
struct CDVDInputStreamBluray {
 std::unique_ptr<CDVDInputStreamFile> m_pstream;std::mutex m_readBlocksLock;
 bool OpenStream(CFileItem&);int ReadBlocks(uint8_t*,int,int);void Close(){m_pstream.reset();}
};
bool CDVDInputStreamBluray::OpenStream(CFileItem& item) OPEN_STREAM
int CDVDInputStreamBluray::ReadBlocks(uint8_t* buf,int lba,int num_blocks) BLOCK_READ
int main(int argc,char**){
 buffered=argc>1;
 CDVDInputStreamBluray disc;CFileItem item;assert(disc.OpenStream(item));
 uint8_t bytes[4096];memset(bytes,0xcc,sizeof(bytes));
 assert(disc.ReadBlocks(bytes,1,2)==2 && "libbluray needs complete sectors, not one network fragment");
 assert(disc.m_pstream->file.input.calls>1);
 assert(!memcmp(bytes,disc.m_pstream->file.input.bytes.data()+2048,sizeof(bytes)));
 assert(disc.ReadBlocks(bytes,3,2)==1 && "A true EOF still returns the available full sector");
 assert(disc.ReadBlocks(bytes,4,1)==0);
 assert(disc.ReadBlocks(bytes,0,1)==1);
 assert(!memcmp(bytes,disc.m_pstream->file.input.bytes.data(),2048));
 disc.m_pstream->file.input.seekFailure=true;assert(disc.ReadBlocks(bytes,20,1)==-1);
}
'''.replace('FILE_READ',body(file,'ssize_t CFile::Read('))
        for token,signature in [('FILE_SEEK','int64_t CFile::Seek('),
                ('UNDERFLOW','CFileStreamBuffer::int_type CFileStreamBuffer::underflow('),
                ('SHOWMANY','std::streamsize CFileStreamBuffer::showmanyc('),
                ('SEEKOFF','CFileStreamBuffer::pos_type CFileStreamBuffer::seekoff('),
                ('SEEKPOS','CFileStreamBuffer::pos_type CFileStreamBuffer::seekpos(')]:
            program=program.replace(token,body(file,signature))
        program=program.replace('OPEN_STREAM',body(bluray,'bool CDVDInputStreamBluray::OpenStream('))
        program=program.replace('BLOCK_READ',body(bluray,'int CDVDInputStreamBluray::ReadBlocks('))
        with tempfile.TemporaryDirectory() as temporary:
            folder=Path(temporary)
            source=folder/'check.cpp';source.write_text(program)
            binary=folder/'check'
            built=subprocess.run(['c++','-std=c++20','-fsanitize=address,undefined',str(source),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            checked=subprocess.run([str(binary)]+(['--buffered'] if buffered else []),capture_output=True,text=True)
            self.assertEqual(checked.returncode,0,checked.stderr)


if __name__=='__main__':unittest.main()
