#include <assert.h>
#include "libbluray/bdnav/clpi_parse.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
typedef struct {uint8_t data[20];int64_t pos;} FILE_DATA;
static int64_t rd(BD_FILE_H *fp,uint8_t *out,int64_t n) {
 FILE_DATA *p=fp->internal;if(n>20-p->pos)n=20-p->pos;
 memcpy(out,p->data+p->pos,n);p->pos+=n;return n;
}
static int64_t sk(BD_FILE_H *fp,int64_t offset,int32_t origin) {
 FILE_DATA *p=fp->internal;p->pos=offset;return offset;
}
int64_t file_size(BD_FILE_H *fp) {return 20;}
int main(int argc,char **argv) {
 CLPI_CL cl={0};cl.clip.num_source_packets=999;uint32_t t=99;
 CLPI_EP_MAP_ENTRY e={0};CLPI_EP_COARSE c={.ref_ep_fine_id=0,.spn_ep=0};
 CLPI_EP_FINE f={.spn_ep=10,.pts_ep=1,.is_angle_change_point=1};
 if(!strcmp(argv[1],"stc")) {
  CLPI_STC_SEQ *seq=calloc(1,sizeof(*seq));seq->spn_stc_start=123;
  CLPI_ATC_SEQ atc={.offset_stc_id=4,.num_stc_seq=1,.stc_seq=seq};
  cl.sequence.num_atc_seq=1;cl.sequence.atc_seq=&atc;
  assert(clpi_find_stc_spn(&cl,0)==0);assert(clpi_find_stc_spn(&cl,4)==123);assert(clpi_find_stc_spn(&cl,5)==0);
  free(seq);
 } else if(!strcmp(argv[1],"no-map")) {
  assert(clpi_access_point(&cl,0,0,0,&t)==0&&t==0);
  assert(clpi_lookup_spn(&cl,0,0,0)==999&&clpi_lookup_spn(&cl,0,1,0)==0);
 } else if(!strcmp(argv[1],"empty-fine")) {
  cl.cpi.num_stream_pid=1;cl.cpi.entry=&e;e.num_ep_coarse=1;e.coarse=&c;
  assert(clpi_lookup_spn(&cl,0,1,0)==0);assert(clpi_lookup_spn(&cl,0,0,0)==999);
  assert(clpi_access_point(&cl,0,0,0,&t)==0&&t==0);
  e.num_ep_coarse=0;e.coarse=NULL;e.num_ep_fine=1;e.fine=&f;
  assert(clpi_lookup_spn(&cl,0,1,0)==0);assert(clpi_lookup_spn(&cl,0,0,0)==999);
  assert(clpi_access_point(&cl,0,0,0,&t)==0&&t==0);
 } else if(!strcmp(argv[1],"invalid-ref")) {
  /* A real EP map: coarse reference 3 exceeds the two fine records. */
  FILE_DATA data={.data={0,0,0,12,0,0,0xc0,0,0,0,0,0,0,0,0,10,0,0,0,20}};
  BD_FILE_H fp={.internal=&data,.seek=sk,.read=rd};BITSTREAM bs;assert(!bs_init(&bs,&fp));
  e.num_ep_coarse=1;e.num_ep_fine=2;assert(_parse_ep_map_stream(&bs,&e));
  assert(e.coarse[0].ref_ep_fine_id==1);cl.cpi.num_stream_pid=1;cl.cpi.entry=&e;
  assert(clpi_lookup_spn(&cl,1000,1,0)==20);free(e.coarse);free(e.fine);
 } else {
  cl.cpi.num_stream_pid=1;cl.cpi.entry=&e;e.num_ep_coarse=e.num_ep_fine=1;e.coarse=&c;e.fine=&f;
  /* STC/PTS combination reaches 'done' with jj=0: before must stay in bounds. */
  CLPI_EP_COARSE coarse[2]={{.pts_ep=2},{.ref_ep_fine_id=1,.spn_ep=131072,.pts_ep=4}};
  CLPI_EP_FINE fine[2]={f,f};e.num_ep_coarse=e.num_ep_fine=2;e.coarse=coarse;e.fine=fine;
  CLPI_STC_SEQ seq={.spn_stc_start=11};CLPI_ATC_SEQ atc={.num_stc_seq=1,.stc_seq=&seq};
  cl.sequence.num_atc_seq=1;cl.sequence.atc_seq=&atc;
  assert(clpi_lookup_spn(&cl,256,1,0)==10);
  e.num_ep_coarse=e.num_ep_fine=1;e.coarse=&c;e.fine=&f;
  assert(clpi_access_point(&cl,10,0,1,&t)==10&&t==256);
 }
}
