/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_TRIM_GLSL_H
#define CB1_TRIM_GLSL_H
/* GPU form of the scalar SOP/chroma contract in cb1_trim_math.h. */
#define CB1_TRIM_SOP_GLSL \
"{vec3 normalized=clamp(color.rgb/creative_sop.w*creative_sop.x+creative_sop.y,0.0,1.0);" \
"color.rgb=creative_sop.w*pow(normalized,vec3(creative_sop.z));}\n"

#define CB1_TRIM_CHROMA_GLSL \
"{vec3 rgb=color.rgb;float luma=dot(rgb,vec3(.22897,.69174,.07929));" \
"if(luma>0.0 && creative_color.y!=0.0){" \
"for(int channel=0;channel<3;channel++){if(rgb[channel]>0.0){" \
"float ratio=(1.0+creative_color.x)*rgb[channel]/luma;" \
"rgb[channel]*=pow(ratio,creative_color.y);}}}color.rgb=rgb;}\n"
#endif
