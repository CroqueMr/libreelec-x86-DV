/* SPDX-License-Identifier: GPL-3.0-or-later */
/* Hades: the GPU programs that libplacebo makes, kept in a file from one session to the next. */
#include "dvbridge_cache.h"
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

struct dvbridge_shader_cache {
    pl_cache cache;
    char *path;
    size_t max_bytes;
    int loaded;
    /* What the file holds (nothing: 0, 0, 0): pl_cache_signature() (the keys xored), the number of
     * entries and their bytes. The three, since keys that are xored can come to the same. */
    struct state {
        uint64_t signature;
        int entries;
        size_t bytes;
    } on_disk;
};

static struct state state_of(pl_cache cache)
{
    return (struct state){pl_cache_signature(cache), pl_cache_objects(cache), pl_cache_size(cache)};
}

static bool same_state(struct state a, struct state b)
{
    return a.signature == b.signature && a.entries == b.entries && a.bytes == b.bytes;
}

/* The format of pl_cache_save(), libplacebo's src/cache.c (CACHE_VERSION 1): a header of 16
 * bytes ("pl_cache", the version, the number of entries), then for each entry its key, size and
 * checksum (three 64-bit values) and its bytes, padded to 4. Host byte order. */
#define FILE_MAGIC "pl_cache"
#define FILE_VERSION 1
#define HEADER_BYTES 16
#define ENTRY_BYTES 24

static uint32_t read_u32(const unsigned char *p)
{
    uint32_t v;
    memcpy(&v, p, sizeof(v));
    return v;
}

static uint64_t read_u64(const unsigned char *p)
{
    uint64_t v;
    memcpy(&v, p, sizeof(v));
    return v;
}

/* Whether the bytes are a whole file of that format, every entry within it and of at most
 * max_bytes. libplacebo allocates the size an entry says before it reads it: a size that the
 * file does not hold must not reach it. */
static bool well_formed(const unsigned char *data, size_t length, size_t max_bytes)
{
    if (length < HEADER_BYTES || memcmp(data, FILE_MAGIC, 8) != 0 ||
        read_u32(data + 8) != FILE_VERSION)
        return false;
    const uint32_t entries = read_u32(data + 12);
    size_t at = HEADER_BYTES;
    for (uint32_t i = 0; i < entries; ++i) {
        if (length - at < ENTRY_BYTES)
            return false;
        const uint64_t key = read_u64(data + at);
        const uint64_t size = read_u64(data + at + 8);
        at += ENTRY_BYTES;
        if (!key || !size || size > max_bytes || size > length - at)
            return false;
        const uint64_t padded = (size + 3) & ~(uint64_t)3;
        if (padded > length - at)
            return false;
        at += (size_t)padded;
    }
    return at == length;
}

struct dvbridge_shader_cache *dvbridge_shader_cache_open(const char *path, size_t max_bytes, pl_log log)
{
    struct dvbridge_shader_cache *c = calloc(1, sizeof(*c));
    if (!c)
        return NULL;
    c->path = strdup(path ? path : "");
    c->max_bytes = max_bytes;
    c->cache = pl_cache_create(pl_cache_params(.log = log, .max_total_size = max_bytes,
                                               .max_object_size = max_bytes));
    if (!c->path || !c->cache) {
        dvbridge_shader_cache_close(c);
        return NULL;
    }
    if (!c->path[0])
        return c;
    FILE *f = fopen(c->path, "rb");
    if (!f)
        return c;
    /* The whole file, of what the cache may hold and its headers at most */
    const size_t most = max_bytes <= 32 * 1024 * 1024 ?
        max_bytes + max_bytes / 2 + 65536 : 64 * 1024 * 1024;
    unsigned char *data = malloc(most + 1);
    size_t length = data ? fread(data, 1, most + 1, f) : 0;
    const bool read_whole = data && !ferror(f) && length <= most;
    fclose(f);
    if (read_whole && well_formed(data, length, max_bytes)) {
        const int taken = pl_cache_load(c->cache, data, length);
        c->loaded = taken > 0 ? taken : 0;
        /* (what was not taken, with a checksum that does not match, makes the file differ from
         * the cache: it is written anew without it the next time) */
        if (c->loaded == (int)read_u32(data + 12))
            c->on_disk = state_of(c->cache);
        else
            c->on_disk = (struct state){0, -1, 0};
    }
    free(data);
    return c;
}

void dvbridge_shader_cache_close(struct dvbridge_shader_cache *c)
{
    if (!c)
        return;
    pl_cache_destroy(&c->cache);
    free(c->path);
    free(c);
}

pl_cache dvbridge_shader_cache_get(const struct dvbridge_shader_cache *c)
{
    return c ? c->cache : NULL;
}

int dvbridge_shader_cache_loaded(const struct dvbridge_shader_cache *c)
{
    return c ? c->loaded : 0;
}

void dvbridge_shader_cache_size(const struct dvbridge_shader_cache *c, int *entries, size_t *bytes)
{
    if (entries)
        *entries = c ? pl_cache_objects(c->cache) : 0;
    if (bytes)
        *bytes = c ? pl_cache_size(c->cache) : 0;
}

int dvbridge_shader_cache_save(struct dvbridge_shader_cache *c)
{
    if (!c || !c->path[0])
        return -1;
    const struct state now = state_of(c->cache);
    if (same_state(now, c->on_disk))
        return 0;
    /* What would be written, then written: the cache is not changed meanwhile by this thread,
     * and a change by another one makes the sizes differ, which is tried again next time */
    const size_t length = pl_cache_save(c->cache, NULL, 0);
    unsigned char *data = length ? malloc(length) : NULL;
    if (!data || pl_cache_save(c->cache, data, length) != length) {
        free(data);
        return -1;
    }
    const size_t name = strlen(c->path) + 32;
    char *temporary = malloc(name);
    if (!temporary) {
        free(data);
        return -1;
    }
    snprintf(temporary, name, "%s.XXXXXX", c->path);
    int fd = mkstemp(temporary);
    FILE *f = fd >= 0 ? fdopen(fd, "wb") : NULL;
    if (!f && fd >= 0)
        close(fd);
    bool written = f && fwrite(data, 1, length, f) == length;
    if (f)
        written = fclose(f) == 0 && written;
    free(data);
    if (written && rename(temporary, c->path) == 0) {
        free(temporary);
        c->on_disk = now;
        return 1;
    }
    remove(temporary);
    free(temporary);
    return -1;
}
