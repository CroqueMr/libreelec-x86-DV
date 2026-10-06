/* SPDX-License-Identifier: MIT */
/* Post-reconstruction fixture seam. Exercise canonical policy scaling,
 * mapping, container and resolve using the unchanged frozen linear inputs.
 * Actual AV/DV ingress is covered separately by reference_images/expert.
 */
#include "reference_test.h"
static bool source_fixture_render(pl_renderer r,const struct pl_frame *image,
    const struct pl_frame *target,const struct pl_render_params *params)
{
    struct pl_frame source=*image;
    if(params->color_map_params && params->color_map_params->cb1_fp32_tone_lut)
        source.repr=pl_color_repr_rgb; /* Input texture is independent BT2020 PQ. */
    return pl_render_image(r,&source,target,params);
}
#define pl_render_image source_fixture_render
#include "../src/dvbridge_render.c"
#undef pl_render_image
#include "reference_images.c"
