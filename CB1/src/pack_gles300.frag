#version 300 es
// SPDX-License-Identifier: GPL-3.0-or-later
// Adapted from intel-dv-linux mpv_dvbridge_dv.h transport packing.
precision highp float;
precision highp int;
uniform highp sampler2D pq_input;
uniform uvec4 metadata_words[128];
uniform uint packet_count;
uniform uint flip_y;
out vec4 color;

uint parity(uint value)
{
    value ^= value >> 16u;
    value ^= value >> 8u;
    value ^= value >> 4u;
    value ^= value >> 2u;
    value ^= value >> 1u;
    return value & 1u;
}

void main()
{
    ivec2 p = ivec2(gl_FragCoord.xy);
    if (flip_y != 0u) p.y = 2159 - p.y;
    ivec2 q = ivec2(p.x & ~1, p.y);
    vec3 a = clamp(texelFetch(pq_input, q, 0).rgb, 0.0, 1.0);
    vec3 b = clamp(texelFetch(pq_input, q + ivec2(1, 0), 0).rgb, 0.0, 1.0);
    float ya = dot(a, vec3(.2627, .6780, .0593));
    float yb = dot(b, vec3(.2627, .6780, .0593));
    uint y = uint(floor(256.0 + 3504.0 * ((p.x & 1) == 0 ? ya : yb) + .5));
    float cb = 2048.0 + 3584.0 * ((a.b - ya) + (b.b - yb)) / (2.0 * 1.8814);
    float cr = 2048.0 + 3584.0 * ((a.r - ya) + (b.r - yb)) / (2.0 * 1.4746);
    uint c = uint(floor(((p.x & 1) == 0 ? cb : cr) + .5));
    uint index = uint(p.y * 3840 + p.x);
    uint packet = index / 3072u;
    if (packet < packet_count)
    {
        uint bit = index % 1024u;
        uint byte_index = packet * 128u + bit / 8u;
        uint value = (metadata_words[byte_index / 4u][int(byte_index % 4u)] >> (7u - bit % 8u)) & 1u;
        c = (c & 4094u) | (value ^ parity(c >> 1u) ^ parity(y));
    }
    color = vec4(float(c >> 4u), float(y >> 4u), float((y & 15u) | ((c & 15u) << 4u)), 255.0) / 255.0;
}
