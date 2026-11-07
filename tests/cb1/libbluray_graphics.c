#include <assert.h>
#include "libbluray/decoders/graphics_processor.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
static PES_BUFFER *segment(unsigned n) {
 PES_BUFFER *p=calloc(1,sizeof(*p));p->buf=calloc(1,n);p->len=p->size=n;p->buf[0]=PGS_OBJECT;return p;
}
int main(int argc,char **argv) {
 if(!strcmp(argv[1],"lookup")) {
  PES_BUFFER *p=segment(1);uint8_t id[]={1,2,3};
  assert(_find_segment_by_idv(p,PGS_OBJECT,3,id,3)==NULL);pes_buffer_free(&p);
 } else if(!strcmp(argv[1],"header")) {
  for(unsigned n=3;n<7;++n){PES_BUFFER *p=segment(n);assert(_join_segment_fragments(p)==1);pes_buffer_free(&p);}
 } else {
  PES_BUFFER *p=segment(8);p->buf[6]=0x80;p->buf[7]=0xab;
  p->next=segment(6); /* matching ID but no sequence descriptor */
  p->next->next=segment(7);p->next->next->buf[6]=0x40; /* final header with no payload */
  assert(_join_segment_fragments(p)==1);assert(p->next==NULL&&p->len==8&&p->buf[7]==0xab);
  pes_buffer_free(&p);
 }
}
