/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "dvbridge_cache.h"
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

struct dvbridge_shader_cache {
    pl_cache objects;
    char *filename;
    uint64_t saved_key;
    size_t saved_bytes;
    int saved_count;
    int loaded_count;
};

static void remember(struct dvbridge_shader_cache *store)
{
    store->saved_key = pl_cache_signature(store->objects);
    store->saved_bytes = pl_cache_size(store->objects);
    store->saved_count = pl_cache_objects(store->objects);
}

/* libplacebo cache.c version 1: native-endian header and padded object records.
 * Validate storage before its loader allocates memory from an object length. */
static int checked_entries(const unsigned char *buffer, size_t size, size_t limit)
{
    uint32_t header[4];
    if (size < sizeof(header))
        return -1;
    memcpy(header, buffer, sizeof(header));
    if (memcmp(buffer, "pl_cache", 8) || header[2] != 1 || header[3] > INT_MAX)
        return -1;
    size_t remaining = size - sizeof(header);
    buffer += sizeof(header);
    for (uint32_t i = 0; i < header[3]; ++i) {
        uint64_t record[3];
        if (remaining < sizeof(record))
            return -1;
        memcpy(record, buffer, sizeof(record));
        buffer += sizeof(record);
        remaining -= sizeof(record);
        if (!record[0] || !record[1] || record[1] > limit || record[1] > remaining)
            return -1;
        size_t payload = (size_t)record[1];
        size_t padding = (4 - payload % 4) % 4;
        if (padding > remaining - payload)
            return -1;
        buffer += payload + padding;
        remaining -= payload + padding;
    }
    return remaining ? -1 : (int)header[3];
}

struct dvbridge_shader_cache *dvbridge_shader_cache_open(const char *path, size_t max_bytes, pl_log log)
{
    struct dvbridge_shader_cache *store = calloc(1, sizeof(*store));
    if (!store)
        return NULL;
    store->filename = strdup(path ? path : "");
    store->objects = pl_cache_create(pl_cache_params(.log = log,
        .max_object_size = max_bytes, .max_total_size = max_bytes));
    if (!store->filename || !store->objects) {
        dvbridge_shader_cache_close(store);
        return NULL;
    }
    FILE *file = store->filename[0] ? fopen(store->filename, "rb") : NULL;
    if (!file)
        return store;
    struct stat info;
    size_t bound = max_bytes > 32U * 1024 * 1024 ? 64U * 1024 * 1024 :
                   max_bytes + max_bytes / 2 + 65536;
    unsigned char *buffer = NULL;
    if (fstat(fileno(file), &info) == 0 && S_ISREG(info.st_mode) &&
        info.st_size >= 16 && (uintmax_t)info.st_size <= bound) {
        size_t length = (size_t)info.st_size;
        buffer = malloc(length);
        if (buffer && fread(buffer, 1, length, file) == length &&
            fgetc(file) == EOF && !ferror(file)) {
            int entries = checked_entries(buffer, length, max_bytes);
            if (entries >= 0) {
                int loaded = pl_cache_load(store->objects, buffer, length);
                store->loaded_count = loaded > 0 ? loaded : 0;
                if (store->loaded_count == entries)
                    remember(store);
                else
                    store->saved_count = -1;
            }
        }
    }
    free(buffer);
    fclose(file);
    return store;
}

void dvbridge_shader_cache_close(struct dvbridge_shader_cache *store)
{
    if (store) {
        pl_cache_destroy(&store->objects);
        free(store->filename);
        free(store);
    }
}

pl_cache dvbridge_shader_cache_get(const struct dvbridge_shader_cache *store)
{
    return store ? store->objects : NULL;
}

int dvbridge_shader_cache_loaded(const struct dvbridge_shader_cache *store)
{
    return store ? store->loaded_count : 0;
}

void dvbridge_shader_cache_size(const struct dvbridge_shader_cache *store, int *entries, size_t *bytes)
{
    if (entries)
        *entries = pl_cache_objects(dvbridge_shader_cache_get(store));
    if (bytes)
        *bytes = pl_cache_size(dvbridge_shader_cache_get(store));
}

int dvbridge_shader_cache_save(struct dvbridge_shader_cache *store)
{
    if (!store || !store->filename[0])
        return -1;
    uint64_t key = pl_cache_signature(store->objects);
    size_t bytes = pl_cache_size(store->objects);
    int count = pl_cache_objects(store->objects);
    if (key == store->saved_key && bytes == store->saved_bytes && count == store->saved_count)
        return 0;

    size_t length = strlen(store->filename);
    char *name = malloc(length + sizeof(".XXXXXX"));
    if (!name)
        return -1;
    memcpy(name, store->filename, length);
    memcpy(name + length, ".XXXXXX", sizeof(".XXXXXX"));
    int descriptor = mkstemp(name);
    if (descriptor < 0) {
        free(name);
        return -1;
    }
    FILE *file = fdopen(descriptor, "wb");
    int result = -1;
    if (file) {
        pl_cache_save_file(store->objects, file);
        bool complete = !ferror(file);
        if (fclose(file) != 0)
            complete = false;
        if (complete && rename(name, store->filename) == 0) {
            store->saved_key = key;
            store->saved_bytes = bytes;
            store->saved_count = count;
            result = 1;
        }
    } else {
        close(descriptor);
    }
    if (result < 0)
        unlink(name);
    free(name);
    return result;
}
