"""Execute native EVO1 serialization through its real packet-write boundary."""
import unittest
from test_hdr10_transport import function
import test_nvidia_native_hdr as native_hdr


class NvidiaPacketBytes(unittest.TestCase):
    sources = native_hdr.NvidiaNativeHdr.sources
    compile_run = native_hdr.NvidiaNativeHdr.compile_run

    def test_checksum_insertion_preserves_the_last_payload_byte(self):
        for root in self.sources():
            source=(root/'src/nvidia-modeset/src/nvkms-evo1.c').read_text()
            native='\n'.join(function(source,name) for name in (
                'nvEvo1NvtToHdmiInfoFramePacketType',
                'EvoInfoFrameToHdmiLibTransmitCtrl','nvEvo1SendHdmiInfoFrame'))
            program=r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
typedef uint8_t NvU8; typedef unsigned NvU32; typedef int NvBool;
typedef int NVHDMIPKT_TC; typedef int NVHDMIPKT_TYPE; typedef int NVHDMIPKT_RESULT;
enum {FALSE=0,TRUE=1,NVHDMIPKT_SUCCESS=0};
enum {NVT_INFOFRAME_TYPE_EXTENDED_METADATA_PACKET=0x7f,
 NVT_INFOFRAME_TYPE_VENDOR_SPECIFIC=0x81,NVT_INFOFRAME_TYPE_VIDEO=0x82,
 NVT_INFOFRAME_TYPE_DYNAMIC_RANGE_MASTERING=0x87};
enum {hdmi_pktType_ExtendedMetadata=0x7f,hdmi_pktType_VendorSpecInfoFrame=0x81,
 hdmi_pktType_AviInfoFrame=0x82,hdmi_pktType_DynamicRangeMasteringInfoFrame=0x87};
enum {NVHDMIPKT_TYPE_GENERIC=1,NVHDMIPKT_TYPE_AVI_INFOFRAME=2,
 NVHDMIPKT_TYPE_VENDOR_SPECIFIC_INFOFRAME=4};
enum {NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_SINGLE_FRAME=1,
 NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_EVERY_FRAME=2,
 NVHDMIPKT_TRANSMIT_CONTROL_ENABLE_SINGLE_FRAME=13,
 NVHDMIPKT_TRANSMIT_CONTROL_ENABLE_EVERY_FRAME=9};
#define NV_EVO_INFOFRAME_TRANSMIT_CONTROL_SINGLE_FRAME 1
#define NV_EVO_INFOFRAME_TRANSMIT_CONTROL_EVERY_FRAME 2
#define DRF_DEF(a,b,c,d) 8
#define nvAssert assert
#define nvkms_memcpy memcpy
#define nvAlloc malloc
#define nvFree free
typedef struct {NvU8 type,version,length;} NVT_INFOFRAME_HEADER;
typedef struct {NvU8 type,firstLast,sequenceIndex;} NVT_EXTENDED_METADATA_PACKET_INFOFRAME_HEADER;
@@CTRLDEF@@
typedef struct {NvU32 activeRmId;} NVDispHeadStateEvoRec;
typedef struct {struct {void*handle;}hdmiLib;} NVDevEvoRec;
typedef NVDevEvoRec* NVDevEvoPtr;
typedef struct {NVDevEvoPtr pDevEvo;NvU32 displayOwner;NVDispHeadStateEvoRec headState[1];} NVDispEvoRec;
static NvU8 received[40]; static NvU32 received_size;
static NVHDMIPKT_RESULT NvHdmiPkt_PacketWrite(void*handle,NvU32 sub,NvU32 display,
 NvU32 head,NVHDMIPKT_TYPE slot,NVHDMIPKT_TC ctrl,NvU32 length,const NvU8*packet){
 assert(handle==(void*)1 && sub==2 && display==3 && head==0);
 assert(slot==1 || slot==2 || slot==4); assert(ctrl!=0);
 assert(length<=sizeof(received));received_size=length;memcpy(received,packet,length);
 return NVHDMIPKT_SUCCESS;
}
@@NATIVE@@
int main(void){
 NVDevEvoRec dev={.hdmiLib={.handle=(void*)1}};
 NVDispEvoRec disp={.pDevEvo=&dev,.displayOwner=2,.headState={{3}}};
 NvEvoInfoFrameTransmitControl control={NV_EVO_INFOFRAME_TRANSMIT_FREQUENCY_EVERY_FRAME};
 const struct {NvU8 type,version,size,last;NvBool checksum;} cases[]={
  {0x87,1,26,0x12,TRUE}, /* MaxFALL high byte must reach the receiver. */
  {0x81,1,24,0xa5,TRUE},{0x81,1,27,0x5a,TRUE}, /* DV V1/V2 payload ends. */
  {0x81,1,5,4,TRUE}, /* Legacy HDMI-VIC identifier. */
  {0x82,2,13,0xc3,TRUE},{0x7f,0xc0,28,0x77,FALSE}
 };
 for(unsigned i=0;i<sizeof(cases)/sizeof(cases[0]);i++){
  NvU8 input[36]={cases[i].type,cases[i].version,cases[i].size};
  unsigned size=3+cases[i].size;
  for(unsigned k=3;k<size;k++)input[k]=(NvU8)(k*17+3);
  input[size-1]=cases[i].last;
  nvEvo1SendHdmiInfoFrame(&disp,0,@@CONTROL@@,(const void*)input,size,cases[i].checksum);
  unsigned expected=size+(cases[i].checksum?1:0);
  assert(received_size==expected && "inserted checksum must be included in transmitted length");
  assert(received[expected-1]==cases[i].last);
  assert(memcmp(received,input,3)==0);
  assert(memcmp(received+3+(cases[i].checksum?1:0),input+3,size-3)==0);
  if(cases[i].checksum){unsigned sum=0;for(unsigned k=0;k<expected;k++)sum+=received[k];assert((sum&255)==0);}
 }
}
'''.replace('@@NATIVE@@',native)
            modern='src->frequency' in native
            program=program.replace('@@CTRLDEF@@',
                'typedef struct {int frequency;} NvEvoInfoFrameTransmitControl;' if modern else
                'typedef int NvEvoInfoFrameTransmitControl;').replace('@@CONTROL@@','&control' if modern else 'control')
            with self.subTest(stack=str(root)):
                self.compile_run(program)


if __name__=='__main__': unittest.main()
