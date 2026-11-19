/* Execute the complete production instruction owner; IO/control callbacks are inert. */
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "libbluray/hdmv/mobj_data.h"
#include "libbluray/hdmv/hdmv_insn.h"
#define BD_DEBUG(...) ((void)0)
typedef struct {const MOBJ_OBJECT *object; uint32_t pc, result; uint64_t rand;} HDMV_VM;
static void _fetch_operands(HDMV_VM *p, MOBJ_CMD *c, uint32_t *d, uint32_t *s) {*d=c->dst;*s=c->src;}
#define _hdmv_trace_cmd(...) ((void)0)
#define _hdmv_trace_res(...) ((void)0)
#define _jump_title(...) 0
#define _call_title(...) 0
#define _resume_object(...) 0
#define _jump_object(...) 0
#define _call_object(...) 0
#define _play_at(...) 0
#define _link_at(...) 0
#define _play_stop(...) 0
#define _set_stream(...) 0
#define _set_sec_stream(...) 0
#define _set_nv_timer(...) 0
#define _set_button_page(...) 0
#define _enable_button(...) 0
#define _popup_off(...) 0
#define _set_still_mode(...) 0
#define _set_output_mode(...) 0
#define _set_stream_ss(...) 0
#define _setsystem_0x10(...) 0
#define _store_result(p,c,s,d,s0,d0) ((p)->result=(d))
#define SWAP_u32(a,b) do {uint32_t t=a;a=b;b=t;} while(0)
static inline uint32_t ADD_u32(uint32_t a,uint32_t b) @ADD@
static inline uint32_t MUL_u32(uint32_t a,uint32_t b) @MUL@
static inline uint32_t RAND_u32(HDMV_VM *p,uint32_t range) @RAND@
static int _hdmv_step(HDMV_VM *p) @STEP@
int main(int argc,char **argv) {
 MOBJ_CMD cmd={0};MOBJ_OBJECT obj={.num_cmds=1,.cmds=&cmd};HDMV_VM vm={.object=&obj};
 cmd.insn.op_cnt=2;
 if(!strcmp(argv[1],"bc")) {
  cmd.insn.grp=INSN_GROUP_CMP;cmd.insn.cmp_opt=INSN_BC;
  const uint32_t values[]={0,1,2,3,0x27,0x80000000,UINT32_MAX};
  for(unsigned d=0;d<7;++d)for(unsigned s=0;s<7;++s){
   vm.pc=0;cmd.dst=values[d];cmd.src=values[s];_hdmv_step(&vm);
   assert(vm.pc==(((cmd.dst&cmd.src)==cmd.src)?1:2));
  }
 } else {
  cmd.insn.grp=INSN_GROUP_SET;cmd.insn.sub_grp=SET_SET;
  const unsigned counts[]={0,1,31,32,33,UINT32_MAX};
  for(unsigned i=0;i<6;++i)for(unsigned op=INSN_BITSET;op<=INSN_SHR;++op){
   cmd.insn.set_opt=op;cmd.dst=0x10203040;cmd.src=counts[i];vm.pc=0;vm.result=cmd.dst;
   _hdmv_step(&vm);uint32_t expected=cmd.dst;
   if(op==INSN_BITSET && counts[i]<32)expected|=UINT32_C(1)<<counts[i];
   if(op==INSN_BITCLR && counts[i]<32)expected&=~(UINT32_C(1)<<counts[i]);
   if(op==INSN_SHL)expected=counts[i]<32?cmd.dst<<counts[i]:0;
   if(op==INSN_SHR)expected=counts[i]<32?cmd.dst>>counts[i]:0;
   assert(vm.result==expected);
  }
 }
}
