#include <assert.h>
#include "libbluray/decoders/pg_decode.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
/* Observe the owner's allocation request and enforce its documented initial cap. */
void *refcnt_realloc(void *p,size_t n,void (*cleanup)(void *)) {
 assert(n<=65536*sizeof(BD_PG_RLE_ELEM));return realloc(p,n);
}
int main(int argc,char **argv) {
 uint8_t pixels[]={1,2};BITBUFFER bb;bb_init(&bb,pixels,2);BD_PG_OBJECT obj={0};
 obj.width=!strcmp(argv[1],"cap")?1024:!strcmp(argv[1],"overflow")?65535:2;
 obj.height=!strcmp(argv[1],"cap")?1024:!strcmp(argv[1],"overflow")?65535:1;
 int ok=_decode_rle(&bb,&obj);
 if(!strcmp(argv[1],"valid")){assert(ok);assert(obj.img[0].len==1&&obj.img[0].color==1);assert(obj.img[1].color==2);}
 else assert(!ok);
 free(obj.img);
}
