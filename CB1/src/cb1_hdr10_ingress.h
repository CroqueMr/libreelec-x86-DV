/* SPDX-License-Identifier: GPL-3.0-or-later */
#ifndef CB1_HDR10_INGRESS_H
#define CB1_HDR10_INGRESS_H
#include <libplacebo/renderer.h>
#include "cb1_l1l3_model.h"
#ifdef __cplusplus
extern "C" {
#endif
struct cb1_hdr10_ingress;
/* Shared RGB48 integer decoder for analysis, never movie rendering. */
#define CB1_HDR10_SOURCE_GLSL \
    "int sample_y(ivec2 p){return int(roundEven(texelFetch(Y_input,p+origin,0).r*65535.0))>>bit_shift;}" \
    "ivec2 sample_uv(ivec2 p){vec2 q;" \
    "p+=subsampled!=0u?origin/2:origin;if(source_packed!=0u)q=texelFetch(U_input,p,0).rg;" \
    "else q=vec2(texelFetch(U_input,p,0).r,texelFetch(V_input,p,0).r);" \
    "return ivec2(roundEven(q*65535.0))>>ivec2(bit_shift);}" \
    "ivec3 analysis_code(int code_y,ivec2 chroma){" \
    "int y=4*code_y-16*(1<<depth_shift)*4;ivec2 uv=chroma-ivec2(128*(1<<depth_shift)*4);" \
    "int bias=1<<(depth_shift+6),shift=depth_shift+7;" \
    "ivec3 value=ivec3(y*9539+uv.y*13752,y*9539-uv.x*1535-uv.y*5328,y*9539+uv.x*17545);" \
    "return clamp((value+ivec3(bias))>>ivec3(shift),ivec3(0),ivec3(65535));}" \
    "vec4 analysis_rgb(ivec2 p){ivec2 uv;" \
    "if(subsampled!=0u){int row=p.y/2;" \
    "int other=(p.y&1)!=0?min(row+1,int(height)/2-1):max(row-1,0);" \
    "uv=3*sample_uv(ivec2(p.x/2,row))+sample_uv(ivec2(p.x/2,other));}" \
    "else uv=4*sample_uv(p);" \
    "return vec4(vec3(analysis_code(sample_y(p),uv))/65535.0,1.0);}"
enum cb1_ai_status cb1_hdr10_ingress_validate(const struct pl_frame *source);
bool cb1_hdr10_ingress_source_shader(pl_shader shader,const struct pl_frame *source);
struct cb1_hdr10_ingress *cb1_hdr10_ingress_create(pl_gpu gpu);
void cb1_hdr10_ingress_destroy(struct cb1_hdr10_ingress **ctx);
/* Analysis-only RGB48 representation matching the frozen swscale producer.
 * Never use this texture as the film's rendering source. Borrowed until next
 * call/destruction; the caller retains decoded planes during submission. */
enum cb1_ai_status cb1_hdr10_ingress_rgb(struct cb1_hdr10_ingress *ctx,
    const struct pl_frame *source,pl_tex *out);
/* Direct source-plane downsampling, quantized through binary16 for the model. */
enum cb1_ai_status cb1_hdr10_ingress_small(struct cb1_hdr10_ingress *ctx,
    const struct pl_frame *source,pl_tex *out);
#ifdef __cplusplus
}
#endif
#endif
