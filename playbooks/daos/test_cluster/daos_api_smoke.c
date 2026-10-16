/* Native DAOS KV write/read verification; no POSIX, FUSE, or MPI dependency. */
#include <daos.h>
#include <daos_kv.h>
#include <errno.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned char pattern(unsigned client, size_t offset)
{
    return (unsigned char)(client * 17 + offset % 251);
}

int main(int argc, char **argv)
{
    daos_handle_t pool = DAOS_HDL_INVAL, cont = DAOS_HDL_INVAL, kv = DAOS_HDL_INVAL;
    daos_obj_id_t oid = {0};
    const size_t sizes[] = {65536, 2097152};
    int rc, initialized = 0, result = EXIT_FAILURE;
    unsigned client, count;
    char *end;
    unsigned char *buffer = NULL;
    if (argc != 7 || (strcmp(argv[3], "write") && strcmp(argv[3], "read"))) {
        fprintf(stderr, "Usage: %s pool container write|read client-index client-count run-id\n", argv[0]);
        return EXIT_FAILURE;
    }
    client = (unsigned)strtoul(argv[4], &end, 10);
    if (*end) return EXIT_FAILURE;
    count = (unsigned)strtoul(argv[5], &end, 10);
    if (*end || !count || count > 1024 || client >= count) return EXIT_FAILURE;
    errno = 0;
    oid.lo = strtoull(argv[6], &end, 10);
    if (errno || *end || !oid.lo) return EXIT_FAILURE;
#define CHECK(call) do { rc = (call); if (rc) { fprintf(stderr, "%s failed: %d\n", #call, rc); goto out; } } while (0)
    CHECK(daos_init());
    initialized = 1;
    CHECK(daos_pool_connect(argv[1], NULL, DAOS_PC_RW, &pool, NULL, NULL));
    CHECK(daos_cont_open(pool, argv[2], DAOS_COO_RW, &cont, NULL, NULL));
    CHECK(daos_obj_generate_oid(cont, &oid, DAOS_OT_KV_HASHED, OC_UNKNOWN, 0, 0));
    CHECK(daos_kv_open(cont, oid, DAOS_OO_RW, &kv, NULL));
    buffer = malloc(sizes[1]);
    if (!buffer) goto out;
    for (size_t s = 0; s < sizeof(sizes) / sizeof(sizes[0]); ++s) {
        unsigned first = !strcmp(argv[3], "write") ? client : 0;
        unsigned last = !strcmp(argv[3], "write") ? client + 1 : count;
        for (unsigned writer = first; writer < last; ++writer) {
            char key[64];
            snprintf(key, sizeof(key), "client-%u-size-%zu", writer, sizes[s]);
            if (!strcmp(argv[3], "write")) {
                for (size_t i = 0; i < sizes[s]; ++i) buffer[i] = pattern(writer, i);
                CHECK(daos_kv_put(kv, DAOS_TX_NONE, 0, key, sizes[s], buffer, NULL));
            } else {
                daos_size_t length = sizes[s];
                memset(buffer, 0, sizes[s]);
                CHECK(daos_kv_get(kv, DAOS_TX_NONE, 0, key, &length, buffer, NULL));
                if (length != sizes[s]) {
                    fprintf(stderr, "%s size mismatch: %llu != %zu\n", key, (unsigned long long)length, sizes[s]);
                    goto out;
                }
                for (size_t i = 0; i < sizes[s]; ++i) {
                    if (buffer[i] != pattern(writer, i)) {
                        fprintf(stderr, "%s data mismatch at byte %zu\n", key, i);
                        goto out;
                    }
                }
            }
            printf("PASS %s %s bytes=%zu\n", argv[3], key, sizes[s]);
            fflush(stdout);
        }
    }
    result = EXIT_SUCCESS;
out:
    free(buffer);
    if (daos_handle_is_valid(kv)) { rc = daos_kv_close(kv, NULL); if (rc) result = EXIT_FAILURE; }
    if (daos_handle_is_valid(cont)) { rc = daos_cont_close(cont, NULL); if (rc) result = EXIT_FAILURE; }
    if (daos_handle_is_valid(pool)) { rc = daos_pool_disconnect(pool, NULL); if (rc) result = EXIT_FAILURE; }
    if (initialized) { rc = daos_fini(); if (rc) result = EXIT_FAILURE; }
    return result;
}
