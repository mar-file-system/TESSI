/* MPI native DAOS KV load test. Validation is outside timed regions. */
#include <daos.h>
#include <daos_kv.h>
#include <mpi.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int rank;
static void check(int rc, const char *call) {
    if (rc) { fprintf(stderr, "rank %d: %s failed: %d\n", rank, call, rc); MPI_Abort(MPI_COMM_WORLD, 1); }
}
#define CHECK(call) check((call), #call)
static unsigned long long number(const char *s) {
    char *end; errno = 0;
    unsigned long long n = strtoull(s, &end, 10);
    if (errno || *end || !n) MPI_Abort(MPI_COMM_WORLD, 2);
    return n;
}
static void key(char *out, int writer, unsigned slot) {
    snprintf(out, 80, "rank-%d-slot-%u", writer, slot);
}
static void measure(daos_handle_t kv, unsigned char *buffer, size_t size,
                    unsigned slots, double seconds, int reading, int ranks) {
    char name[80]; unsigned long long ops = 0, total = 0;
    MPI_Barrier(MPI_COMM_WORLD);
    double start = MPI_Wtime(), elapsed;
    do {
        key(name, rank, (unsigned)(ops % slots));
        if (reading) {
            daos_size_t length = size;
            CHECK(daos_kv_get(kv, DAOS_TX_NONE, 0, name, &length, buffer, NULL));
            if (length != size) MPI_Abort(MPI_COMM_WORLD, 3);
        } else {
            CHECK(daos_kv_put(kv, DAOS_TX_NONE, 0, name, size, buffer, NULL));
        }
        ++ops; elapsed = MPI_Wtime() - start;
    } while (elapsed < seconds);
    double maximum;
    MPI_Reduce(&elapsed, &maximum, 1, MPI_DOUBLE, MPI_MAX, 0, MPI_COMM_WORLD);
    MPI_Reduce(&ops, &total, 1, MPI_UNSIGNED_LONG_LONG, MPI_SUM, 0, MPI_COMM_WORLD);
    if (!rank) {
        printf("{\"operation\":\"%s\",\"ranks\":%d,\"value_bytes\":%zu,\"operations\":%llu,\"seconds\":%.6f,\"cluster_iops\":%.3f,\"cluster_bandwidth_Bps\":%.3f,\"cluster_bandwidth_MiBps\":%.3f}\n",
               reading ? "read" : "write", ranks, size, total, maximum,
               total / maximum, (double)total * size / maximum,
               (double)total * size / maximum / 1048576.0);
        fflush(stdout);
    }
}
int main(int argc, char **argv) {
    MPI_Init(&argc, &argv); int ranks;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank); MPI_Comm_size(MPI_COMM_WORLD, &ranks);
    if (argc != 8) {
        if (!rank) fprintf(stderr, "Usage: %s pool container run-id bytes seconds slots results.jsonl\n", argv[0]);
        MPI_Abort(MPI_COMM_WORLD, 2);
    }
    daos_obj_id_t oid = {0}; oid.lo = number(argv[3]);
    size_t size = number(argv[4]); double seconds = (double)number(argv[5]);
    unsigned long long requested_slots = number(argv[6]);
    if (size > 16777216 || requested_slots > 4096) MPI_Abort(MPI_COMM_WORLD, 2);
    unsigned slots = (unsigned)requested_slots;
    unsigned char *buffer = malloc(size);
    if (!buffer) MPI_Abort(MPI_COMM_WORLD, 2);
    memset(buffer, (unsigned char)(rank % 251), size);
    daos_handle_t pool, cont, kv;
    CHECK(daos_init());
    CHECK(daos_pool_connect(argv[1], NULL, DAOS_PC_RW, &pool, NULL, NULL));
    CHECK(daos_cont_open(pool, argv[2], DAOS_COO_RW, &cont, NULL, NULL));
    CHECK(daos_obj_generate_oid(cont, &oid, DAOS_OT_KV_HASHED, OC_UNKNOWN, DAOS_OCH_SHD_MAX, 0));
    CHECK(daos_kv_open(cont, oid, DAOS_OO_RW, &kv, NULL));
    /* Seed the bounded working set before measuring reads or overwrites. */
    char name[80];
    for (unsigned i = 0; i < slots; ++i) {
        key(name, rank, i);
        CHECK(daos_kv_put(kv, DAOS_TX_NONE, 0, name, size, buffer, NULL));
    }
    measure(kv, buffer, size, slots, seconds, 0, ranks);
    measure(kv, buffer, size, slots, seconds, 1, ranks);
    MPI_Barrier(MPI_COMM_WORLD);
    /* Every rank verifies another rank's entire working set, without timing. */
    int writer = (rank + 1) % ranks;
    for (unsigned i = 0; i < slots; ++i) {
        key(name, writer, i); daos_size_t length = size;
        CHECK(daos_kv_get(kv, DAOS_TX_NONE, 0, name, &length, buffer, NULL));
        if (length != size) MPI_Abort(MPI_COMM_WORLD, 3);
        for (size_t b = 0; b < size; ++b)
            if (buffer[b] != (unsigned char)(writer % 251)) MPI_Abort(MPI_COMM_WORLD, 3);
    }
    MPI_Barrier(MPI_COMM_WORLD);
    if (!rank) {
        FILE *f = fopen(argv[7], "w");
        if (!f) MPI_Abort(MPI_COMM_WORLD, 4);
        fprintf(f, "{\"validation\":\"PASS\",\"ranks\":%d,\"value_bytes\":%zu,\"slots_per_rank\":%u}\n", ranks, size, slots);
        if (fclose(f)) MPI_Abort(MPI_COMM_WORLD, 4);
        puts("PASS cross-rank byte verification");
    }
    CHECK(daos_kv_close(kv, NULL)); CHECK(daos_cont_close(cont, NULL));
    CHECK(daos_pool_disconnect(pool, NULL)); CHECK(daos_fini());
    free(buffer); MPI_Finalize(); return 0;
}
