/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Hades: the GPU programs that libplacebo makes, kept in a file from one session to the next. */
#ifndef DVBRIDGE_CACHE_H
#define DVBRIDGE_CACHE_H
#include <stdbool.h>
#include <stddef.h>
#include <libplacebo/cache.h>

/* A pl_cache for pl_gpu_set_cache(), with a file behind it. On OpenGL libplacebo keeps the binary
 * of each program it links there, by a key made of the GL vendor, renderer and version and the
 * source of the program, and takes it back with glProgramBinary() when the same program is made
 * again: the driver then has nothing to compile. A binary that the driver does not take (another
 * driver, a damaged one) is not used, and the program is compiled from its source as without a
 * cache. The file is meant for one GPU, driver and build: the caller names it by them.
 *
 * Not thread safe beyond what pl_cache is; the cache must outlive every pl_gpu that uses it. */
struct dvbridge_shader_cache;

/* Takes what the file at path holds when it is a whole file of the format that
 * dvbridge_shader_cache_save() writes: its header and the size of every entry are checked
 * against the file before anything of it is taken, and libplacebo checks the checksum of each
 * entry as it takes it (an entry that does not match is left out, with the ones after it).
 * A missing or bad file is no failure: the cache starts empty.
 * max_bytes bounds what the cache holds (the oldest entries make room) and what is read.
 * Returns NULL only when there is no memory. */
struct dvbridge_shader_cache *dvbridge_shader_cache_open(const char *path, size_t max_bytes, pl_log log);
/* Without saving it. The pl_cache goes with it. */
void dvbridge_shader_cache_close(struct dvbridge_shader_cache *cache);
pl_cache dvbridge_shader_cache_get(const struct dvbridge_shader_cache *cache);
/* Entries taken from the file when it was opened. */
int dvbridge_shader_cache_loaded(const struct dvbridge_shader_cache *cache);
/* Writes the file when what the cache holds is not what the file holds (it has been loaded or
 * written with other entries): into a file beside it, which then takes its name, so that a file
 * is whole or not there. 1 written, 0 nothing to write, -1 it could not be written. */
int dvbridge_shader_cache_save(struct dvbridge_shader_cache *cache);
/* What the cache holds: entries and bytes. */
void dvbridge_shader_cache_size(const struct dvbridge_shader_cache *cache, int *entries, size_t *bytes);
#endif
