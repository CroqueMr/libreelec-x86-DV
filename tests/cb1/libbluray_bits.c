#include <assert.h>
#include <string.h>
#include "util/bits.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
typedef struct {uint8_t data[BF_BUF_SIZE+8];int64_t pos;int seek_error,read_error;} FILE_DATA;
static int64_t rd(BD_FILE_H *fp,uint8_t *out,int64_t n) {
 FILE_DATA *p=fp->internal;if(p->read_error)return -1;
 if(n>(int64_t)sizeof(p->data)-p->pos)n=sizeof(p->data)-p->pos;
 memcpy(out,p->data+p->pos,n);p->pos+=n;return n;
}
static int64_t sk(BD_FILE_H *fp,int64_t offset,int32_t origin) {
 FILE_DATA *p=fp->internal;if(p->seek_error)return -1;p->pos=offset;return offset;
}
int64_t file_size(BD_FILE_H *fp) {return sizeof(((FILE_DATA*)0)->data);}
int main(int argc,char **argv) {
 FILE_DATA data={0};for(unsigned i=0;i<sizeof(data.data);++i)data.data[i]=i%251;
 BD_FILE_H fp={.internal=&data,.seek=sk,.read=rd};BITSTREAM bs;assert(!bs_init(&bs,&fp));
 if(!strcmp(argv[1],"wide")) {
  const uint8_t v[]={0x12,0x34,0x56,0x78,0x9a};BITBUFFER bb;bb_init(&bb,v,sizeof(v));
  assert(bb_read(&bb,40)==0x12345678);assert(bb_read(&bb,8)==0x9a);
  assert(bs_read(&bs,40)==0x00010203);assert(bs_read(&bs,8)==4);return 0;
 }
 for(unsigned i=0;i<BF_BUF_SIZE-2;++i)assert(bs_read(&bs,8)==i%251);
 assert(bs_read(&bs,4)==((BF_BUF_SIZE-2)%251)>>4);
 if(!strcmp(argv[1],"seek-error")||!strcmp(argv[1],"skip-error"))data.seek_error=1;
 if(!strcmp(argv[1],"read-error"))data.read_error=1;
 if(!strcmp(argv[1],"skip-error")) {bs_skip(&bs,16);assert(bs.size==0);return 0;}
 uint32_t got=bs_read(&bs,24);
 if(data.seek_error||data.read_error){assert(got==0&&bs.size==0);return 0;}
 uint32_t expected=(((BF_BUF_SIZE-2)%251)&15)<<20;
 expected|=((BF_BUF_SIZE-1)%251)<<12;expected|=(BF_BUF_SIZE%251)<<4;
 expected|=((BF_BUF_SIZE+1)%251)>>4;assert(got==expected);
 for(unsigned i=0;i<20;++i)bs_read(&bs,32);assert(bs_read(&bs,32)==0&&bs.size==0);
}
