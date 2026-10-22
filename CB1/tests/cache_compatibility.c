/* SPDX-License-Identifier: MIT */
#include "dvbridge_cache.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* The runner compares this public-API transcript and saved bytes across builds. */
int main(int argc, char **argv)
{
    assert(argc == 3);
    size_t limit = strtoull(argv[2], NULL, 10);
    struct dvbridge_shader_cache *c = dvbridge_shader_cache_open(argv[1], limit, NULL);
    assert(c);
    int count;
    size_t bytes;
    dvbridge_shader_cache_size(c, &count, &bytes);
    printf("open %d %d %zu\n", dvbridge_shader_cache_loaded(c), count, bytes);
    printf("initial-save %d\n", dvbridge_shader_cache_save(c));
    unsigned char data[4096];
    for (unsigned i = 1; i <= 300; ++i) {
        size_t size = i * 13 % sizeof(data) + 1;
        for (size_t j = 0; j < size; ++j)
            data[j] = (unsigned char)(i * 31 + j * 17);
        pl_cache_obj obj = {.key = i * 7919, .data = data, .size = size};
        pl_cache_set(dvbridge_shader_cache_get(c), &obj);
    }
    dvbridge_shader_cache_size(c, &count, &bytes);
    printf("insert %d %zu\n", count, bytes);
    printf("save %d\n", dvbridge_shader_cache_save(c));
    printf("unchanged-save %d\n", dvbridge_shader_cache_save(c));
    dvbridge_shader_cache_close(c);
    c = dvbridge_shader_cache_open(argv[1], limit, NULL);
    assert(c);
    printf("reopen %d\n", dvbridge_shader_cache_loaded(c));
    for (unsigned i = 1; i <= 300; ++i) {
        pl_cache_obj obj = {.key = i * 7919};
        if (pl_cache_get(dvbridge_shader_cache_get(c), &obj)) {
            uint64_t hash = 14695981039346656037ULL;
            for (size_t j = 0; j < obj.size; ++j)
                hash = (hash ^ ((unsigned char *)obj.data)[j]) * 1099511628211ULL;
            printf("object %u %zu %016llx\n", i, obj.size, (unsigned long long)hash);
            pl_cache_set(dvbridge_shader_cache_get(c), &obj);
        }
    }
    printf("read-save %d\n", dvbridge_shader_cache_save(c));
    dvbridge_shader_cache_close(c);
    return 0;
}
