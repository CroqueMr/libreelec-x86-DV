#include <assert.h>
#include <stdarg.h>
#include <string.h>
#include "libbluray/bdnav/navigation.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
static unsigned used_stc;
uint32_t clpi_lookup_spn(const CLPI_CL *cl,uint32_t t,int before,uint8_t stc) {used_stc=stc;return 15;}
int main(int argc,char **argv) {
 NAV_CLIP clip={.start_pkt=10,.title_pkt=100,.angle=0};
 NAV_MARK marks[1]={{.clip_ref=0,.clip_pkt=20}};
 MPLS_CLIP angles[1]={{.stc_id=7}};MPLS_PI pi={.clip=angles,.angle_count=1};
 MPLS_PLM plm={.play_item_ref=0,.time=50};
 MPLS_PL pl={.list_count=1,.play_item=&pi,.play_mark=&plm};
 NAV_TITLE title={.pl=&pl,.angle=8};NAV_MARK mark={0};
 title.clip_list.count=1;title.clip_list.clip=&clip;
 title.chap_list.count=title.mark_list.count=1;title.chap_list.mark=title.mark_list.mark=marks;
 uint32_t cp=0,op=0;
 if(!strcmp(argv[1],"chapter")) {
  assert(nav_chapter_search(&title,1,&cp,&op)==&clip);assert(cp==10&&op==100);
  title.chap_list.count=0;title.chap_list.mark=NULL;
  assert(nav_chapter_search(&title,0,&cp,&op)==&clip);assert(cp==10&&op==100);
 } else if(!strcmp(argv[1],"mark")) {
  assert(nav_mark_search(&title,1,&cp,&op)==&clip);assert(cp==10&&op==100);
  title.mark_list.count=0;title.mark_list.mark=NULL;
  assert(nav_mark_search(&title,0,&cp,&op)==&clip);assert(cp==10&&op==100);
 } else if(!strcmp(argv[1],"invalid-ref")) {
  plm.play_item_ref=1;_fill_mark(&title,&mark,0);assert(mark.clip_ref==0&&mark.clip_pkt==10);
 } else if(!strcmp(argv[1],"empty")) {
  title.clip_list.count=0;title.clip_list.clip=NULL;_fill_mark(&title,&mark,0);assert(mark.clip_ref==0);
 } else {
  CLPI_CL cl={0};clip.cl=&cl;_fill_mark(&title,&mark,0);assert(used_stc==7&&mark.clip_pkt==15);
 }
}
