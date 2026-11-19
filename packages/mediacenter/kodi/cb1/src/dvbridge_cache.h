/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef DVBRIDGE_CACHE_H
#define DVBRIDGE_CACHE_H
#include <stdbool.h>
#include <stddef.h>
#include <libplacebo/cache.h>

/* Persistent libplacebo program cache. The caller owns the GPU/build-specific
 * pathname, serializes open/save/close, and keeps this object alive until its
 * GPU has been destroyed. GPU cache operations retain libplacebo's locking. */
struct dvbridge_shader_cache;

/* Read a bounded, validated libplacebo cache file. Invalid/missing files yield
 * an empty cache; NULL indicates allocation failure. No parent directory is
 * created. max_bytes limits cached objects and their combined payload. */
struct dvbridge_shader_cache *dvbridge_shader_cache_open(const char *path, size_t max_bytes, pl_log log);
/* Destroy without implicitly saving. */
void dvbridge_shader_cache_close(struct dvbridge_shader_cache *cache);
pl_cache dvbridge_shader_cache_get(const struct dvbridge_shader_cache *cache);
int dvbridge_shader_cache_loaded(const struct dvbridge_shader_cache *cache);
/* Atomic replacement: 1 saved, 0 unchanged, -1 failure. A failed save preserves
 * the existing file. Do not mutate the cache while saving. */
int dvbridge_shader_cache_save(struct dvbridge_shader_cache *cache);
void dvbridge_shader_cache_size(const struct dvbridge_shader_cache *cache, int *entries, size_t *bytes);
#endif
