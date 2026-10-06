/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Host-only opt-in. Preserve the original numerical probe's assertions. */
#include <libplacebo/opengl.h>
static pl_opengl task3_opengl_create(pl_log log, const struct pl_opengl_params *params)
{
    struct pl_opengl_params local = *params;
    local.allow_software = true;
    return pl_opengl_create(log, &local);
}
#define pl_opengl_create task3_opengl_create
