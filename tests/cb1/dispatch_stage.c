/* SPDX-License-Identifier: MIT */
/* Inspect shaders emitted by the real dispatcher before driver compilation. */
#include "gpu.h"
#include <libplacebo/dummy.h>
#include <libplacebo/shaders/custom.h>
#include <assert.h>
#include <stdio.h>
#include <string.h>

static unsigned captured;
static pl_pass inspect_stage(pl_gpu gpu, const struct pl_pass_params *p)
{
    (void)gpu;
    captured++;
    assert(strstr(p->glsl_shader, "CB1_FRAGMENT_COMPUTE_ONLY"));
    assert(strstr(p->glsl_shader, "GL_KHR_shader_subgroup_quad"));
    assert(!!strstr(p->glsl_shader, "GL_KHR_shader_subgroup_basic") == !!gpu->glsl.subgroup_size);
    const char *precision = strstr(p->glsl_shader, "precision ");
    const char *custom = strstr(p->glsl_shader, "#extension GL_KHR_shader_subgroup_quad : require");
    assert(precision && custom && custom < precision);
    assert(strstr(p->glsl_shader, "#define CB1_FRAGMENT_COMPUTE_ONLY") < precision);
    if (p->type == PL_PASS_RASTER) {
        assert(p->vertex_shader && strstr(p->vertex_shader, "#version"));
        assert(!strstr(p->vertex_shader, "CB1_FRAGMENT_COMPUTE_ONLY"));
        assert(!strstr(p->vertex_shader, "GL_KHR_shader_subgroup"));
    }
    /* Capture only: dummy devices deliberately do not compile or execute passes. */
    return NULL;
}

int main(void)
{
    for (int compute = 0; compute < 2; compute++) for (int subgroup = 0; subgroup < 2; subgroup++) {
        struct pl_gpu_dummy_params params = pl_gpu_dummy_default_params;
        params.glsl.version = 310;
        params.glsl.gles = true;
        params.glsl.subgroup_size = subgroup ? 32 : 0;
        pl_gpu gpu = pl_gpu_dummy_create(NULL, &params);
        assert(gpu);
        ((struct pl_gpu_fns *)PL_PRIV(gpu))->pass_create = inspect_stage;
        pl_dispatch dp = pl_dispatch_create(NULL, gpu);
        pl_shader sh = pl_dispatch_begin(dp);
        assert(pl_shader_custom(sh, &(struct pl_custom_shader){
            .prelude = "#extension GL_KHR_shader_subgroup_quad : require\n"
                       "#define CB1_FRAGMENT_COMPUTE_ONLY 1\n",
            .body = "color = vec4(0.25, 0.5, 0.75, 1.0);",
            .input = PL_SHADER_SIG_NONE, .output = PL_SHADER_SIG_COLOR,
            .compute = compute, .compute_group_size = {8, 8},
        }));
        unsigned before = captured;
        if (compute) {
            assert(!pl_dispatch_compute(dp, pl_dispatch_compute_params(
                .shader = &sh, .dispatch_size = {1, 1, 1})));
        } else {
            pl_tex target = pl_tex_create(gpu, pl_tex_params(.w = 16, .h = 16,
                .format = pl_find_named_fmt(gpu, "rgba8"), .renderable = true));
            assert(target);
            assert(!pl_dispatch_finish(dp, pl_dispatch_params(.shader = &sh, .target = target)));
            pl_tex_destroy(gpu, &target);
        }
        assert(captured == before + 1);
        pl_dispatch_destroy(&dp);
        pl_gpu_dummy_destroy(&gpu);
    }
    printf("PASS %u real raster/compute shader-stage captures\n", captured);
}
