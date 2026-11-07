#include <assert.h>
#include <string.h>
#include "libbluray/bdnav/sound_parse.c"
uint32_t debug_mask=0;
void bdpriv_debug(const char *f,int l,uint32_t m,const char *fmt,...) {}
typedef struct {int64_t pos;} FILE_DATA;
static const int64_t sample_pos=INT64_C(0x100000100);
static int64_t rd(BD_FILE_H *fp,uint8_t *out,int64_t n) {
 FILE_DATA *p=fp->internal;memset(out,0,n);
 if(p->pos==0) {
  /* BCLK header; one 16-bit mono sample, data_start+offset crosses 4 GiB. */
  memcpy(out,"BCLK0100",8);out[8]=out[9]=out[10]=0xff;
  out[43]=16;out[45]=1;out[46]=0x11;out[47]=0x40;
  out[50]=2;out[55]=2;
 } else if(p->pos==sample_pos){out[0]=0x12;out[1]=0x34;}
 p->pos+=n;return n;
}
static int64_t sk(BD_FILE_H *fp,int64_t offset,int32_t origin) {
 FILE_DATA *p=fp->internal;p->pos=offset;return offset;
}
int64_t file_size(BD_FILE_H *fp) {return sample_pos+65536;}
int main(int argc,char **argv) {
 FILE_DATA state={0};BD_FILE_H fp={.internal=&state,.seek=sk,.read=rd};
 SOUND_DATA *sound=_sound_parse(&fp);
 assert(sound&&sound->num_sounds==1&&sound->sounds[0].num_frames==1);
 assert(sound->sounds[0].samples[0]==0x1234);sound_free(&sound);assert(!sound);
}
