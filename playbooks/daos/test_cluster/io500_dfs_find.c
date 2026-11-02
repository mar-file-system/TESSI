/* IO500 external find: direct DFS traversal, one process, no dfuse or MPI. */
#define _GNU_SOURCE
#include <daos.h>
#include <daos_fs.h>
#include <dirent.h>
#include <fcntl.h>
#include <fnmatch.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>

static dfs_t *fs;
static const char *pattern = "*";
static off_t wanted_size = -1;
static struct timespec newer;
static int use_newer;
static uint64_t matched, total;
static void check(int rc, const char *call) {
    if (rc) { fprintf(stderr, "%s failed: %d\n", call, rc); exit(1); }
}
#define CHECK(call) check((call), #call)
static void walk(dfs_obj_t *dir) {
    daos_anchor_t anchor = {0};
    do {
        struct dirent entries[64]; struct stat stats[64]; uint32_t nr = 64;
        CHECK(dfs_readdirplus(fs, dir, &anchor, &nr, entries, stats));
        for (uint32_t i = 0; i < nr; ++i) {
            const char *name = entries[i].d_name;
            if (!strcmp(name, ".") || !strcmp(name, "..")) continue;
            if (S_ISDIR(stats[i].st_mode)) {
                dfs_obj_t *child;
                CHECK(dfs_lookup_rel(fs, dir, name, O_RDONLY, &child, NULL, NULL));
                walk(child); CHECK(dfs_release(child));
            } else if (S_ISREG(stats[i].st_mode)) {
                ++total;
                if (fnmatch(pattern, name, 0)) continue;
                if (wanted_size >= 0 && stats[i].st_size != wanted_size) continue;
                struct timespec t = stats[i].st_mtim;
                if (use_newer && (t.tv_sec < newer.tv_sec ||
                    (t.tv_sec == newer.tv_sec && t.tv_nsec <= newer.tv_nsec))) continue;
                ++matched;
            }
        }
    } while (!daos_anchor_is_eof(&anchor));
}
int main(int argc, char **argv) {
    if (argc < 4) {
        fprintf(stderr, "Usage: %s pool container path [-name glob] [-size Nc] [-newer local-file]\n", argv[0]);
        return 2;
    }
    for (int i = 4; i < argc; i += 2) {
        if (i + 1 >= argc) return 2;
        if (!strcmp(argv[i], "-name")) pattern = argv[i + 1];
        else if (!strcmp(argv[i], "-size")) {
            char *end; long long n = strtoll(argv[i + 1], &end, 10);
            if (n < 0 || strcmp(end, "c")) return 2;
            wanted_size = n;
        } else if (!strcmp(argv[i], "-newer")) {
            struct stat st;
            if (stat(argv[i + 1], &st)) { perror(argv[i + 1]); return 1; }
            newer = st.st_mtim; use_newer = 1;
        } else return 2;
    }
    CHECK(daos_init());
    CHECK(dfs_connect(argv[1], NULL, argv[2], O_RDONLY, NULL, &fs));
    dfs_obj_t *root; mode_t mode;
    CHECK(dfs_lookup(fs, argv[3], O_RDONLY, &root, &mode, NULL));
    if (!S_ISDIR(mode)) { fprintf(stderr, "Find root must be a directory\n"); return 1; }
    walk(root); CHECK(dfs_release(root)); CHECK(dfs_disconnect(fs)); CHECK(daos_fini());
    printf("MATCHED %" PRIu64 "/%" PRIu64 "\n", matched, total);
    return 0;
}
