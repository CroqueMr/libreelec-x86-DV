/* SPDX-License-Identifier: GPL-2.0-or-later */
#include <assert.h>
#include <stdbool.h>
#include <stdio.h>
#include <string.h>
#include "drm_hdr10plus.h"

static void checksum(unsigned char p[31])
{
    p[3] = 0;
    for (unsigned i = 0; i < 31; i++)
        if (i != 3) p[3] -= p[i];
}

int main(void)
{
    unsigned char db[]={0xe5,1,0x8b,0x84,0x90,1};
    assert(drm_hdr10plus_vsvdb_version(db,sizeof(db))==1);
    db[5]=0; assert(drm_hdr10plus_vsvdb_version(db,sizeof(db))==0);
    assert(drm_hdr10plus_vsvdb_version(db,5)==-1);
    db[0]=0x65; assert(drm_hdr10plus_vsvdb_version(db,sizeof(db))==-1);
    db[0]=0xe5; db[2]=0x46;
    assert(drm_hdr10plus_vsvdb_version(db,sizeof(db))==-1);
    assert(drm_hdr10plus_vsvdb_version(NULL,6)==-1);
    unsigned char p[31] = {0x81,1,27,0,0x8b,0x84,0x90,0x7e,
        10,1,0,255,4,8,16,32,64,128,0,0,0,0,0,0,0,0,0,0,0,0,0x40};
    assert(drm_hdr10plus_infoframe_valid(p,31));
    assert(!drm_hdr10plus_infoframe_valid(NULL,31));
    assert(!drm_hdr10plus_infoframe_valid(p,30));
    assert(!drm_hdr10plus_infoframe_valid(p,32));
    for (unsigned i=0; i<7; i++) {
        p[i] ^= 1;
        assert(!drm_hdr10plus_infoframe_valid(p,31));
        p[i] ^= 1;
    }
    p[7]|=1; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[7]=0xbe; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[7]=0x7e; p[10]=1; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[10]=0; p[11]=254; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[11]=255; p[18]=0xa0; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[18]=0x10; p[21]=128; checksum(p); assert(drm_hdr10plus_infoframe_valid(p,31));
    p[22]=128; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[22]=0; p[30]=0; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[30]=0xc0; checksum(p); assert(drm_hdr10plus_infoframe_valid(p,31));
    p[30]|=1; checksum(p); assert(!drm_hdr10plus_infoframe_valid(p,31));
    p[30]=0x40;p[18]=0x30;p[19]=p[20]=0;
    p[21]=255;p[22]=p[23]=0;checksum(p);
    assert(!drm_hdr10plus_infoframe_valid(p,31));
    puts("hdr10plus kernel packet validation: pass");
}
