#include <assert.h>
#include "libbluray/decoders/m2ts_demux.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
int main(int argc,char **argv) {
 unsigned len=!strcmp(argv[1],"pts")?9:!strcmp(argv[1],"dts")?14:19;
 uint8_t *buf=calloc(1,len);buf[2]=1;buf[3]=0xbd;buf[5]=len-6;
 buf[7]=len==9?0x80:0xc0;buf[8]=len-9;
 PES_BUFFER p={0};int result=_parse_pes(&p,buf,len);
 assert(len==19?result==0:result<0);free(p.buf);free(buf);
}
