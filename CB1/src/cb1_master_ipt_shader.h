/* SPDX-License-Identifier: GPL-2.0-or-later */
#define CB1_MASTER_IPT_GLSL \
    "#define CB1_IPT_TRANSPORT 1\n" \
    "float cb1_pq_read(highp sampler2D table,float x){\n" \
    "float f=clamp(x,0.0,1.0)*65536.0; int i=int(f);\n" \
    "vec2 samples=texelFetch(table,ivec2(i&255,i>>8),0).rg;\n" \
    "return mix(samples.x,samples.y,f-float(i));}\n" \
    "vec3 cb1_ipt(vec3 ycc){\n" \
    "vec3 q=clamp(ipt_decode*(ycc*(4095.0/4096.0)-ipt_offset),0.0,1.0);\n" \
    "q=vec3(cb1_pq_read(ipt_eotf,q.r),cb1_pq_read(ipt_eotf,q.g),cb1_pq_read(ipt_eotf,q.b));\n" \
    "q=sqrt(sqrt(clamp(ipt_linear*q,0.0,1.0)));\n" \
    "q=vec3(cb1_pq_read(ipt_oetf,q.r),cb1_pq_read(ipt_oetf,q.g),cb1_pq_read(ipt_oetf,q.b));\n" \
    "return ipt_encode*q+vec3(0.0,.5,.5);}\n"

#define CB1_IPT_CODES_GLSL \
    "uvec2 cb1_source_codes(vec3 self,vec3 peer,bool second){" \
    "vec3 ipt=cb1_ipt(self);\n" \
    "#ifdef CB1_IPT_QUAD\n" \
    "float t=subgroupQuadSwapHorizontal(ipt.z);float c=second?t:ipt.y;\n" \
    "#else\n" \
    "vec3 even_ipt=second?cb1_ipt(peer):ipt;float c=second?even_ipt.z:even_ipt.y;\n" \
    "#endif\n" \
    "return uvec2(clamp(floor(4096.0*vec2(ipt.x,c)+.5),0.0,4095.0));}\n"
