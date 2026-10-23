#version 300 es
// SPDX-License-Identifier: GPL-2.0-or-later
// ETSI GS CCM 001 V1.1.1 clause 6.4 transport-bit placement and scrambling.
precision highp float;
precision highp int;
uniform highp sampler2D pq_input;
uniform uvec4 metadata_words[160];
uniform uint packet_count;
uniform uint flip_y;
out vec4 color;

uint embed(uint luma,uint chroma,uint raster)
{
    uint packet=raster/3072u;
    if(packet>=packet_count)return chroma;
    uint bit=raster%1024u;
    uint address=packet*128u+bit/8u;
    uint data=metadata_words[address/4u][int(address%4u)];
    data=(data>>(7u-bit%8u))&1u;
    uint parity=(chroma>>1u)^luma;
    parity^=parity>>8u;
    parity^=parity>>4u;
    parity=(0x6996u>>(parity&15u))&1u;
    return (chroma&0xffeu)|(data^parity);
}

void main()
{
    ivec2 pixel=ivec2(gl_FragCoord.xy);
    if(flip_y!=0u)pixel.y=2159-pixel.y;
    ivec2 first=ivec2(pixel.x&~1,pixel.y);
    vec3 rgb0=clamp(texelFetch(pq_input,first,0).rgb,0.0,1.0);
    vec3 rgb1=clamp(texelFetch(pq_input,first+ivec2(1,0),0).rgb,0.0,1.0);
    float luma0=dot(rgb0,vec3(.2627,.6780,.0593));
    float luma1=dot(rgb1,vec3(.2627,.6780,.0593));
    bool second=(pixel.x&1)!=0;
    uint y=uint(floor(256.0+3504.0*(second?luma1:luma0)+.5));
    float cb=2048.0+3584.0*((rgb0.b-luma0)+(rgb1.b-luma1))/(2.0*1.8814);
    float cr=2048.0+3584.0*((rgb0.r-luma0)+(rgb1.r-luma1))/(2.0*1.4746);
    uint c=embed(y,uint(floor((second?cr:cb)+.5)),uint(pixel.y*3840+pixel.x));
    uvec3 bytes=uvec3(c>>4u,y>>4u,((c&15u)<<4u)|(y&15u));
    color=vec4(vec3(bytes),255.0)/255.0;
}
