# Vendored: s6-overlay 3.2.1.0

Process supervisor (PID 1 / init) used by the Hermes container image.

## Why these files are committed here

The Dockerfile used to download these three tarballs from GitHub's release CDN at
build time. That failed **five consecutive deploys**:

```
curl: (22) The requested URL returned error: 504
```

Adding `--retry 5 --retry-all-errors` did **not** fix it. A later build logged six
consecutive 504s, with every retry exhausted. The CDN is not reliably reachable
from Railway's build environment, so it is not something a build may depend on.

These tarballs are therefore vendored into the repo. The build now needs no
network for this step, and any future CDN outage cannot break a deploy.

## Provenance

| Field | Value |
|---|---|
| Upstream | https://github.com/just-containers/s6-overlay |
| Version | `v3.2.1.0` |
| Download URL | `https://github.com/just-containers/s6-overlay/releases/download/v3.2.1.0/<file>` |
| Retrieved | 2026-09-21 |
| Licence | ISC (see upstream `COPYING`) |
| Files | `s6-overlay-noarch.tar.xz`, `s6-overlay-x86_64.tar.xz`, `s6-overlay-aarch64.tar.xz`, `s6-overlay-symlinks-noarch.tar.xz` |

Copied verbatim, unmodified. `SHA256SUMS` is generated from the exact bytes on
disk and is verified by the Dockerfile at build time with `sha256sum -c`, so a
corrupted or substituted file fails the build loudly rather than silently.

Both `x86_64` and `aarch64` are vendored because the Dockerfile selects on
`TARGETARCH`; shipping only one would leave the other branch failing at build
time. Railway builds amd64 today, but a latent arm64 break is not worth keeping.

## Updating

1. Download the new version's tarballs into this directory.
2. Regenerate: `sha256sum *.tar.xz > SHA256SUMS`
3. Bump `ARG S6_OVERLAY_VERSION` in `Dockerfile.railway`.
4. Verify locally: `sha256sum -c SHA256SUMS`

Note: `.gitattributes` marks `*.tar.xz` as binary so git does not attempt text
diffing on them.
