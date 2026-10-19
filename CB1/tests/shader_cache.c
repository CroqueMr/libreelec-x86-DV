/* SPDX-License-Identifier: GPL-3.0-or-later */
#include "dvbridge_cache.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <sys/resource.h>
#include <signal.h>

static void insert(struct dvbridge_shader_cache *cache)
{
    pl_cache_obj object = {.key = 42, .data = (void *)"program", .size = 8};
    pl_cache_set(dvbridge_shader_cache_get(cache), &object);
}

int main(void)
{
    char directory[] = "/tmp/cb1-cache-XXXXXX", path[256], other[256];
    assert(mkdtemp(directory));
    snprintf(path, sizeof(path), "%s/gpu-build-a.cache", directory);
    snprintf(other, sizeof(other), "%s/gpu-build-b.cache", directory);
    struct dvbridge_shader_cache *cache = dvbridge_shader_cache_open(path, 4096, NULL);
    assert(cache && !dvbridge_shader_cache_loaded(cache));
    insert(cache);
    assert(dvbridge_shader_cache_save(cache) == 1);
    assert(dvbridge_shader_cache_save(cache) == 0);
    dvbridge_shader_cache_close(cache);
    cache = dvbridge_shader_cache_open(path, 4096, NULL);
    assert(cache && dvbridge_shader_cache_loaded(cache) == 1);
    pl_cache_obj object = {.key = 42};
    assert(pl_cache_get(dvbridge_shader_cache_get(cache), &object));
    assert(object.size == 8 && memcmp(object.data, "program", 8) == 0);
    pl_cache_obj_free(&object);
    dvbridge_shader_cache_close(cache);
    cache = dvbridge_shader_cache_open(other, 4096, NULL);
    assert(cache && !dvbridge_shader_cache_loaded(cache));
    dvbridge_shader_cache_close(cache);

    /* A failed flush preserves the last valid cache, including on a full filesystem. */
    cache = dvbridge_shader_cache_open(path, 4096, NULL);
    pl_cache_obj extra = {.key=99,.data=(void*)"second",.size=7};
    pl_cache_set(dvbridge_shader_cache_get(cache),&extra);
    struct rlimit before,limited;
    assert(getrlimit(RLIMIT_FSIZE,&before)==0);
    limited=before; limited.rlim_cur=4;
    void (*handler)(int)=signal(SIGXFSZ,SIG_IGN);
    assert(setrlimit(RLIMIT_FSIZE,&limited)==0);
    assert(dvbridge_shader_cache_save(cache)==-1);
    assert(setrlimit(RLIMIT_FSIZE,&before)==0);
    signal(SIGXFSZ,handler);
    dvbridge_shader_cache_close(cache);
    cache = dvbridge_shader_cache_open(path,4096,NULL);
    assert(cache && dvbridge_shader_cache_loaded(cache)==1);
    dvbridge_shader_cache_close(cache);

    FILE *oversized=fopen(other,"wb"); assert(oversized);
    assert(ftruncate(fileno(oversized),1024*1024)==0);
    assert(fclose(oversized)==0);
    cache=dvbridge_shader_cache_open(other,4096,NULL);
    assert(cache && !dvbridge_shader_cache_loaded(cache));
    dvbridge_shader_cache_close(cache);
    assert(unlink(other)==0);

    for (int kind = 0; kind < 5; ++kind) {
        FILE *file = fopen(path, "wb"); assert(file);
        uint8_t bad[48] = "pl_cache";
        uint32_t version = kind == 2 ? 2 : 1, count = 1;
        memcpy(bad + 8, &version, 4); memcpy(bad + 12, &count, 4);
        uint64_t key = 42, size = kind == 3 ? UINT64_MAX : 8;
        memcpy(bad + 16, &key, 8); memcpy(bad + 24, &size, 8);
        size_t bytes = kind == 0 ? 0 : kind == 1 ? 12 : sizeof(bad);
        assert(fwrite(bad, 1, bytes, file) == bytes);
        assert(fclose(file) == 0);
        cache = dvbridge_shader_cache_open(path, 4096, NULL);
        assert(cache && !dvbridge_shader_cache_loaded(cache));
        insert(cache);
        assert(dvbridge_shader_cache_save(cache) == 1);
        dvbridge_shader_cache_close(cache);
    }
    /* A failed replacement cannot remove a previously valid target directory. */
    assert(unlink(path) == 0 && mkdir(path, 0700) == 0);
    cache = dvbridge_shader_cache_open(path, 4096, NULL);
    assert(cache); insert(cache);
    assert(dvbridge_shader_cache_save(cache) == -1);
    struct stat status; assert(stat(path, &status) == 0 && S_ISDIR(status.st_mode));
    dvbridge_shader_cache_close(cache);
    assert(rmdir(path) == 0);
    snprintf(path, sizeof(path), "%s/missing/cache", directory);
    cache = dvbridge_shader_cache_open(path, 4096, NULL);
    assert(cache); insert(cache);
    assert(dvbridge_shader_cache_save(cache) == -1);
    dvbridge_shader_cache_close(cache);
    assert(rmdir(directory) == 0);
    puts("shader cache: roundtrip, keys, malformed input and write failures passed");
}
