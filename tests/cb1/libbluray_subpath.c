#include <assert.h>
#include "libbluray/bdnav/mpls_parse.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
int main(int argc,char **argv) {
 MPLS_SUB sub={.sub_playitem_count=2};
 if(!strcmp(argv[1],"allocated"))sub.sub_play_item=calloc(2,sizeof(*sub.sub_play_item));
 _clean_subpath(&sub);assert(sub.sub_play_item==NULL);
}
