/* SPDX-License-Identifier: GPL-3.0-or-later
 * Bounded conversion of original CM metadata block bytes to HDMI extensions.
 * Grammar cross-checked with doppingkoala/dovi_tool d4ad4ba7 (MIT).
 * No inference of optional L8 fields from zeros; no omitted artistic trims.
 * This is not a claim of Dolby conformance or TV interoperability.
 */
#ifndef MPV_DVBRIDGE_CM4_H
#define MPV_DVBRIDGE_CM4_H
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>
#include <string.h>
struct dvbridge_cm4_reader { const uint8_t *p; unsigned bits,pos; bool ok; };
static unsigned dvbridge_cm4_bits(struct dvbridge_cm4_reader *r,unsigned n)
{
    if(n>16 || r->pos+n>r->bits) { r->ok=false;return 0; }
    unsigned value=0;
    while(n--) { value=(value<<1)|((r->p[r->pos/8]>>(7-r->pos%8))&1);r->pos++; }
    return value;
}
/* Return payload length, or -1. Caller must have at least 32 bytes of output.
 * On failure output is unspecified and MUST NOT be used. */
static int dvbridge_cm4_wire(unsigned level,const uint8_t *raw,size_t length,uint8_t out[32])
{
    if(!raw || !out || length>32) return -1;
    struct dvbridge_cm4_reader r={raw,(unsigned)length*8,0,true};
    unsigned n=0,v;
#define BYTE() do { out[n++]=dvbridge_cm4_bits(&r,8); } while(0)
#define WORD(bits) do { v=dvbridge_cm4_bits(&r,bits);out[n++]=v>>8;out[n++]=v; } while(0)
    switch(level) {
    case 3:
        if(length!=5)return -1;
        for(int j=0;j<3;j++) WORD(12);
        break;
    case 4:
        if(length!=3)return -1;
        WORD(12);WORD(12);break;
    case 8:
        if(length!=10 && length!=12 && length!=13 && length!=19 && length!=25)return -1;
        BYTE();
        for(int j=0;j<6;j++)WORD(12);
        if(length>=12)WORD(12);
        if(length>=13)WORD(12);
        if(length>=19)for(int j=0;j<6;j++)BYTE();
        if(length>=25)for(int j=0;j<6;j++)BYTE();
        break;
    case 9:
        if(length!=1 && length!=17)return -1;
        BYTE();
        if((out[0]==255)!=(length==17))return -1;
        if(length==17)for(int j=0;j<8;j++)WORD(16);
        break;
    case 10:
        if(length!=5 && length!=21)return -1;
        BYTE();WORD(12);WORD(12);BYTE();
        if((out[5]==255)!=(length==21))return -1;
        if(length==21)for(int j=0;j<8;j++)WORD(16);
        break;
    case 11:
        /* Both grammars transport four byte-aligned bytes. Preserve the raw
         * packed whitepoint/reference byte rather than reinterpreting the
         * conflicting bitfield declarations of old public parsers.
         * Nonzero reserved bits are not qualified; fail closed. */
        if(length!=4 || raw[0]>15 || (raw[1]&7) || raw[2] || raw[3])return -1;
        for(int j=0;j<4;j++)BYTE();
        break;
    case 254:
        if(length!=2)return -1;
        BYTE();BYTE();break;
    default:return -1;
    }
    while(r.ok && r.pos<r.bits)if(dvbridge_cm4_bits(&r,1))return -1;
#undef BYTE
#undef WORD
    return r.ok && n<=32?(int)n:-1;
}
#endif
