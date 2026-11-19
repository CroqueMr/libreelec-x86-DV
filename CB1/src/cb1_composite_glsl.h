/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef CB1_COMPOSITE_GLSL_H
#define CB1_COMPOSITE_GLSL_H

/* Source-space alpha composition contract: ST2084, supplied inverse matrices
 * and the existing GUI transfer tables. Movie values bypass colour conversion.
 * Optional black GUI pixels bypass redundant transfer work; movie values
 * never use this shortcut. */
#define CB1_COMPOSITE_HEADER_GLSL \
"#ifdef CB1_NATIVE_OVERLAY\n" \
"vec3 cb1_gui_pq(vec3 v){" \
"\n#ifdef CB1_GUI_QUAD\n" \
"if(all(equal(v,vec3(0))))return vec3(pow(3424.0/4096.0,2523.0/32.0));\n#endif\n" \
"vec3 l=vec3(texture(subtitle_degamma,vec2(v.r,.5)).r,texture(subtitle_degamma,vec2(v.g,.5)).r,texture(subtitle_degamma,vec2(v.b,.5)).r);" \
"l=mat3(.6274,.0691,.0164,.3293,.9195,.0880,.0433,.0114,.8956)*l;" \
"return vec3(texture(subtitle_pq,vec2(l.r,.5)).r,texture(subtitle_pq,vec2(l.g,.5)).r,texture(subtitle_pq,vec2(l.b,.5)).r);}\n" \
"vec3 cb1_matrix_pq(vec3 q){" \
"q=pow(max(q,0.0),vec3(1.0/(2523.0/32.0)));" \
"q=max(q-vec3(3424.0/4096.0),0.0)/(vec3(2413.0/128.0)-vec3(2392.0/128.0)*q);" \
"q=overlay_linear*pow(q,vec3(1.0/(2610.0/16384.0)));" \
"q=pow(max(q,0.0),vec3(2610.0/16384.0));" \
"q=(vec3(3424.0/4096.0)+vec3(2413.0/128.0)*q)/(vec3(1.0)+vec3(2392.0/128.0)*q);" \
"return pow(q,vec3(2523.0/32.0));}\n" \
"vec3 cb1_gui_value(vec4 layer){" \
"vec3 v=clamp(layer.rgb/layer.a,0.0,1.0);\n" \
"#ifdef CB1_GUI_QUAD\n" \
"if(all(equal(v,vec3(0))))return overlay_decode*(vec3(pow(3424.0/4096.0,2523.0/32.0))-overlay_offset)*layer.a;\n#endif\n" \
"#if defined(CB1_REFERENCE_TRANSPORT) && defined(CB1_OVERLAY_PQ)\n" \
"vec3 q=v;\n#else\nvec3 q=cb1_gui_pq(v);\n#endif\n" \
"q=cb1_matrix_pq(q);" \
"return overlay_decode*(q-overlay_offset)*layer.a;}\n" \
"vec3 cb1_gui_source(vec4 layer,vec3 base){" \
"return clamp(cb1_gui_value(layer)+base*(1.0-layer.a),0.0,1.0);}\n" \
"#endif\n"

#define CB1_COMPOSITE_BODY_GLSL \
"ivec2 p=ivec2(gl_FragCoord.xy);if(flip_y!=0u)p.y=raster_size.y-1-p.y;\n" \
"#ifdef CB1_SCALED_REFERENCE\n" \
"color=texelFetch(scaled_reference,ivec2(scaled_rect.xy+(vec2(p)+.5)*scaled_rect.zw),0);\n#endif\n" \
"bool inactive=float(p.x)<active_area.x || float(p.x)>=active_area.z || float(p.y)<active_area.y || float(p.y)>=active_area.w;" \
"bool compose=false;vec4 gui=vec4(0);vec3 rgb=vec3(0);\n" \
"#ifdef CB1_SOURCE_DOMAIN\n" \
"if(inactive)color=vec4(CB1_SOURCE_NEUTRAL,1.0);" \
"vec3 own=clamp(color.rgb,0.0,1.0),peer;\n" \
"#ifdef CB1_SCALED_REFERENCE\n" \
"vec2 neighbor=vec2(p^ivec2(1,0))+.5;" \
"peer=clamp(texelFetch(scaled_reference,ivec2(scaled_rect.xy+neighbor*scaled_rect.zw),0).rgb,0.0,1.0);" \
"if(neighbor.x<active_area.x || neighbor.x>=active_area.z || neighbor.y<active_area.y || neighbor.y>=active_area.w)peer=CB1_SOURCE_NEUTRAL;\n" \
"#elif defined(CB1_SCALED_QUAD)\npeer=subgroupQuadSwapHorizontal(own);\n" \
"#elif defined(CB1_REFERENCE_TRANSPORT)\npeer=own;\n" \
"#elif !defined(CB1_SOURCE_OVERLAY)\npeer=subgroupQuadSwapHorizontal(own);\n#endif\n" \
"#else\nrgb=inactive?vec3(0):clamp(color.rgb,0.0,1.0);\n#endif\n" \
"#ifdef CB1_NATIVE_OVERLAY\n" \
"compose=float(p.x)>=overlay_area.x && float(p.x)<overlay_area.z && float(p.y)>=overlay_area.y && float(p.y)<overlay_area.w;" \
"if(compose)gui=texture(subtitle_gui,vec2((float(p.x)+.5)/float(raster_size.x),(float(raster_size.y-1-p.y)+.5)/float(raster_size.y)));\n" \
"#if defined(CB1_REFERENCE_TRANSPORT) && !defined(CB1_GUI_QUAD)\n" \
"vec4 adjacent=texture(subtitle_gui,vec2((float(p.x^1)+.5)/float(raster_size.x),(float(raster_size.y-1-p.y)+.5)/float(raster_size.y)));" \
"float alpha=adjacent.a;\n#else\nfloat alpha=subgroupQuadSwapHorizontal(gui.a);\n#endif\n" \
"compose=compose && (gui.a>0.0 || alpha>0.0);\n#endif\n" \
"#ifdef CB1_SOURCE_DOMAIN\n#ifdef CB1_SOURCE_OVERLAY\n" \
"#ifdef CB1_GUI_QUAD\n" \
"vec3 gui_value=gui.a>0.0?cb1_gui_value(gui):vec3(0);" \
"if(compose && gui.a>0.0)own=clamp(gui_value+own*(1.0-gui.a),0.0,1.0);" \
"\n#ifdef CB1_REFERENCE_TRANSPORT\n" \
"vec3 adjacent_value=subgroupQuadSwapHorizontal(gui_value);" \
"if(compose && alpha>0.0)peer=clamp(adjacent_value+peer*(1.0-alpha),0.0,1.0);\n" \
"#else\npeer=subgroupQuadSwapHorizontal(own);\n#endif\n" \
"#else\n" \
"if(compose && gui.a>0.0)own=cb1_gui_source(gui,own);\n" \
"#ifdef CB1_REFERENCE_TRANSPORT\n" \
"if(compose && adjacent.a>0.0)peer=cb1_gui_source(adjacent,peer);\n" \
"#else\npeer=subgroupQuadSwapHorizontal(own);\n#endif\n#endif\n" \
"compose=false;\n#endif\n" \
"if(!compose)return cb1_carrier(cb1_packet(cb1_source_codes(own,peer,(p.x&1)!=0),uint(p.y*raster_size.x+p.x)));\n#endif\n" \
"#ifndef CB1_REFERENCE_TRANSPORT\n#ifdef CB1_NATIVE_OVERLAY\nif(compose){\n" \
"#ifdef CB1_SOURCE_DOMAIN\n" \
"if(!inactive)rgb=cb1_matrix_pq(overlay_decode*color.rgb+overlay_offset);\n#endif\n" \
"#ifdef CB1_OVERLAY_PQ\nrgb=clamp(gui.rgb+rgb*(1.0-gui.a),0.0,1.0);\n#else\n" \
"#ifdef CB1_STRAIGHT_OVERLAY\ngui.rgb=gui.a>0.0?clamp(gui.rgb/gui.a,0.0,1.0):vec3(0);\n#endif\n" \
"rgb=clamp(cb1_gui_pq(gui.rgb)*gui.a+rgb*(1.0-gui.a),0.0,1.0);\n#endif\n}\n#endif\n" \
"vec3 neighbor_rgb=subgroupQuadSwapHorizontal(rgb);" \
"vec3 first=(p.x&1)==0?rgb:neighbor_rgb,second=(p.x&1)==0?neighbor_rgb:rgb;" \
"color=cb1_carrier(cb1_packet(cb1_rgb_pixel(first,second,(p.x&1)!=0),uint(p.y*raster_size.x+p.x)));\n#endif\n"

#endif
