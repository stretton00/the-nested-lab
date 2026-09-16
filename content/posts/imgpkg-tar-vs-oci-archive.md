---
title: "imgpkg tar vs OCI archive: why your air-gap tarballs won't load"
date: 2026-10-28
draft: false
tags: [air-gap, harbor, imgpkg, crane, oci, vks, gpu-operator]
series: ["Dark Site Notes"]
cover:
  image: "/images/post12-hero-imgpkg.svg"
  alt: "Two tarballs that look the same: manifest.json vs oci-layout"
  hidden: false
summary: "Two tarballs, both '.tar', both full of container images, both destined for the same Harbor. One loads with imgpkg; the other is rejected. The layout difference nobody explains, what actually survives a copy (tags, digests, platforms), and the three tools that can bridge the gap."
---

You staged 40 container images for a dark site. The VKS bundle loads
into Harbor first time with `imgpkg copy --tar`. The GPU Operator images —
same tool, same command — fail. Both are tarballs. Both contain the images.
What's different?

```
$ tar -tf images/nvidia_gpu-operator__v26.3.3.tar | grep -v ^blobs/
oci-layout
index.json

$ tar -tf supervisor/vks-3.7.1.tar | head -2
manifest.json
sha256-05e0b744....tar.gz
```

That's the whole answer, and it took an afternoon to find.

## Two layouts that look the same from the outside

| Archive | Layout | `imgpkg copy --tar`? |
|---|---|---|
| Written by a registry-API puller / `crane pull --format=oci` / skopeo | **OCI image layout**: `oci-layout`, `index.json`, `blobs/sha256/*` | **No** |
| Written by `imgpkg copy --to-tar` | **imgpkg tar**: `manifest.json`, `sha256-*.tar.gz` | Yes |

imgpkg reads *only* the tar format imgpkg itself writes. There is no
converter — `imgpkg push -f <dir>` would wrap the OCI directory as a new
image *layer*, not replicate the original image. If your staging pipeline
pulled with anything other than imgpkg, imgpkg will not load it, full stop.

## Three ways out

**1. Re-pull with imgpkg** (chosen, when you still have internet somewhere):

```
imgpkg copy -i nvcr.io/nvidia/gpu-operator:v26.3.3 --to-tar gpu-operator.tar
# at the dark site:
imgpkg copy --tar gpu-operator.tar --to-repo harbor02/nvidia/gpu-operator
```

Cost: a second download, and it's **bigger** — `imgpkg copy` has no
platform filter, so you get every architecture in the manifest list
(amd64 + arm64, sometimes s390x/ppc64le). 1.1 GiB became 2.3 GiB for the
GPU Operator set. The upside: your arm64 node pool, if you ever have one,
won't send you back to the internet.

**2. crane, no re-pull.** `crane` is a static Go binary — no install, no
root — and it reads OCI layouts natively:

```
crane push images/nvidia_gpu-operator__v26.3.3.tar harbor02/nvidia/gpu-operator:v26.3.3
```

Cheapest in bytes. Requires getting one more binary through the airlock.

**3. skopeo**, if it happens to be there. `skopeo copy oci-archive:... docker://...`.
Usually it isn't.

(There's a fourth — stand up a local `registry:2`, crane-push into it, then
`imgpkg copy -i localhost:5000/... --to-repo harbor02/...` — which is
strictly more work than 1 or 2. Don't.)

## What survives the copy (verified, not assumed)

I tested this against a throwaway `crane registry serve` with a real
multi-arch image, because "the digest should be preserved" is the kind of
sentence that precedes a bad week.

```
imgpkg copy -i nvcr.io/nvidia/cloud-native/k8s-mig-manager:v0.13.1 --to-tar probe.tar
imgpkg copy --tar probe.tar --to-repo 127.0.0.1:5099/real/k8s-mig-manager

imgpkg tag list -i 127.0.0.1:5099/real/k8s-mig-manager --digests
  v0.13.1   sha256:8e0803d2...           # manifest-list digest

crane digest nvcr.io/nvidia/cloud-native/k8s-mig-manager:v0.13.1
  sha256:8e0803d2...                     # identical
crane digest --platform linux/amd64 127.0.0.1:5099/real/k8s-mig-manager:v0.13.1
  sha256:69250353...                     # identical to the OCI-archive .digest sidecar
```

Three things that settles:

1. **The human tag survives.** The destination gets `:v0.13.1` *and*
   imgpkg's `:sha256-<hex>.imgpkg`. This matters — Helm values reference
   images by tag. (Only `--repo-based-tags` changes the tag shape; don't
   pass it.)
2. **Digests survive** at both the manifest-list and per-platform level.
3. **The amd64 bits are identical** to the OCI archive. A re-pull is a
   re-packaging, not different content.

One trap: pinning by digest (`imgpkg copy -i repo@sha256:...`) *would*
keep it single-arch and small — but then there's no tag to carry across,
the destination only gets `:sha256-<hex>.imgpkg`, and your Helm values
break. Don't do that either.

## The one that bites later: signatures

imgpkg **drops cosign signatures by default** at every copy. If the thing
you're loading is a platform bundle whose consumer checks signatures —
and VKS supervisor services on VCF 9.0.1+ do, for versions above 3.4.0
from a private registry — every content check passes, the activation
proceeds, and then every new control-plane pod is denied by a webhook for
running "in an untrusted namespace". Pull and push both need
`--cosign-signatures`. The `.sig` artifacts are separate tags
(`sha256-<digest>.sig`), ~100 KB for a whole bundle, so if the content is
already in the registry you can ship just the signatures.

That one gets [its own post](/series/dark-site-notes/).

## Rules learned

- `tar -tf x.tar | head` before anything else. `manifest.json` = imgpkg;
  `oci-layout` = OCI archive. They are not interchangeable.
- imgpkg loads **only** imgpkg tars. No converter exists.
- OCI archives load with `crane push` (static binary) or skopeo.
- `imgpkg copy` copies **all platforms** (bigger) and preserves tags and
  digests (verified). Pin by tag, never by digest, when Helm values
  reference tags.
- Add `--cosign-signatures` on both ends when the consumer verifies
  bundles.
- Stage `imgpkg` *and* `crane` binaries with the tarballs. One of them
  will be the wrong tool for something.

---
*Lab environment; opinions my own. Verified against a local registry with
real multi-arch images; digests shown are truncated.*
