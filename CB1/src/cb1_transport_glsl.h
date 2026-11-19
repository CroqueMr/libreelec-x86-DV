/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_TRANSPORT_GLSL_H
#define CB1_TRANSPORT_GLSL_H

/* ETSI GS CCM 001 clause 6.4: two 12-bit words in three carrier bytes. */
#define CB1_CARRIER_GLSL \
"vec4 cb1_carrier(uvec2 code){" \
"uvec3 bytes=uvec3(code.y>>4u,code.x>>4u,((code.y&15u)<<4u)|(code.x&15u));" \
"return vec4(vec3(bytes),255.0)/255.0;}\n"

#define CB1_PACKET_GLSL \
"uvec2 cb1_packet(uvec2 code,uint raster){" \
"uint packet=raster/3072u;if(packet>=packet_count)return code;" \
"uint bit=raster%1024u,address=packet*128u+bit/8u;" \
"uint data=(metadata_words[address/4u][int(address%4u)]>>(7u-bit%8u))&1u;" \
"uint parity=(code.y>>1u)^code.x;parity^=parity>>8u;parity^=parity>>4u;" \
"parity=(0x6996u>>(parity&15u))&1u;" \
"code.y=(code.y&0xffeu)|(data^parity);return code;}\n"

/* Numerical code-value contract. Keep operation order before quantization. */
#define CB1_SOURCE_CODES_GLSL \
"uvec2 cb1_source_codes(vec3 self,vec3 peer,bool second){" \
"uint y=uint(floor(4095.0*self.x+.5));" \
"float c=second?self.z+peer.z:self.y+peer.y;" \
"return uvec2(y,uint(floor(2047.5*c+.5)));}\n"

#define CB1_RGB_CODES_GLSL \
"void cb1_rgb_codes(vec3 first,vec3 second,out uvec2 luma,out uvec2 chroma){" \
"float y0=dot(first,vec3(.2627,.6780,.0593)),y1=dot(second,vec3(.2627,.6780,.0593));" \
"luma=uvec2(uint(floor(256.0+3504.0*y0+.5)),uint(floor(256.0+3504.0*y1+.5)));" \
"float cb=2048.0+3584.0*((first.b-y0)+(second.b-y1))/(2.0*1.8814);" \
"float cr=2048.0+3584.0*((first.r-y0)+(second.r-y1))/(2.0*1.4746);" \
"chroma=uvec2(uint(floor(cb+.5)),uint(floor(cr+.5)));}\n"

/* Fragment variant quantizes only the current pixel's two words. */
#define CB1_RGB_PIXEL_GLSL \
"uvec2 cb1_rgb_pixel(vec3 first,vec3 second,bool odd){" \
"float y0=dot(first,vec3(.2627,.6780,.0593)),y1=dot(second,vec3(.2627,.6780,.0593));" \
"uint y=uint(floor(256.0+3504.0*(odd?y1:y0)+.5));" \
"float cb=2048.0+3584.0*((first.b-y0)+(second.b-y1))/(2.0*1.8814);" \
"float cr=2048.0+3584.0*((first.r-y0)+(second.r-y1))/(2.0*1.4746);" \
"return uvec2(y,uint(floor((odd?cr:cb)+.5)));}\n"

#endif
