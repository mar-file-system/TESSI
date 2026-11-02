# Official Mercury packages for the DAOS-18988 fix

Phase1 now uses the published DAOS 2.8.1 repository and installs a matched
set of official `mercury`, `mercury-ucx`, and `mercury-devel` RPMs at
`2.4.1-5.el9`. Mercury 2.4.1-4 added the deserialized-worker-address cache
fix; 2.4.1-5 rebuilt those packages with restored runtime dependencies.
DAOS runtime/development/admin packages are selected at version 2.8.1.

The earlier local 3.1.tessi.daos18988 build is no longer invoked. Its recipe
is retained only as historical source; no local build or artifact distribution
is needed. The official -5 release upgrades all local -3.1 packages and
avoids mixing the local core/devel packages with an official UCX plugin.

Phase1 stops running DAOS services when replacing the Mercury libraries.
Phase5 starts them with the replacement libraries. Existing DAOS storage is
preserved. Repository signature checking stays enabled.

If phase1 failed, retry the requested target, for example:

```sh
make phase6
```

To verify on any allocated node:

```sh
rpm -q mercury mercury-ucx mercury-devel
```

All three packages must report `2.4.1-5.el9`. Phase1 checks this explicitly.
