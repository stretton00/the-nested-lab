---
title: "imgpkg tar vs OCI archive: why your air-gap tarballs won't load"
date: 2026-10-14
draft: false
tags: [air-gap, harbor, imgpkg, crane, oci, vks, gpu-operator]
products: ["VKS", "Private AI"]
series: ["Dark Site Notes"]
seriesPart: 1
tldr:
  - "The VKS bundle loaded into Harbor first time, while the GPU Operator images, same tool and same command, failed."
  - "imgpkg reads only its own tar layout, so an OCI archive needs `crane push`, skopeo or a re-pull with imgpkg."
  - "Run `tar -tf` first, and stage both `imgpkg` and `crane`: one of them will be the wrong tool for something."
cover:
  image: "/images/post12-hero-imgpkg.svg"
  alt: "Two tarballs that look the same: manifest.json vs oci-layout"
  hidden: false
summary: "Two tarballs, both '.tar', both full of container images, both destined for the same Harbor. One loads with imgpkg; the other is rejected. The layout difference nobody explains, what actually survives a copy (tags, digests, platforms), and the three tools that can bridge the gap."
---

You've staged 40 container images for a dark site. The VKS bundle loads
into Harbor first time with `imgpkg copy --tar`. The GPU Operator images,
same tool and same command, fail. Both are tarballs. Both contain the
images. What's different?

```
$ tar -tf images/nvidia_gpu-operator__v26.3.3.tar | grep -v ^blobs/
oci-layout
index.json

$ tar -tf supervisor/vks-3.7.1.tar | head -2
manifest.json
sha256-05e0b744....tar.gz
```

That's the whole answer. It took me an afternoon to find, which is a
generous amount of afternoon for a couple of filenames.

## Two layouts that look the same from the outside

| Archive | Layout | `imgpkg copy --tar`? |
|---|---|---|
| Written by a registry-API puller / `crane pull --format=oci` / skopeo | **OCI image layout**: `oci-layout`, `index.json`, `blobs/sha256/*` | **No** |
| Written by `imgpkg copy --to-tar` | **imgpkg tar**: `manifest.json`, `sha256-*.tar.gz` | Yes |

imgpkg reads *only* the tar format imgpkg itself writes. There's no
converter: `imgpkg push -f <dir>` would wrap the OCI directory as a new
image *layer*, not replicate the original image. If your staging pipeline
pulled with anything other than imgpkg, imgpkg won't load it. Full stop.

## Three ways out

**1. Re-pull with imgpkg** (chosen, when you still have internet somewhere):

```
imgpkg copy -i nvcr.io/nvidia/gpu-operator:v26.3.3 --to-tar gpu-operator.tar
# at the dark site:
imgpkg copy --tar gpu-operator.tar --to-repo harbor02/nvidia/gpu-operator
```

The cost: a second download, and it's **bigger**. `imgpkg copy` has no
platform filter, so you get every architecture in the manifest list
(amd64 and arm64, sometimes s390x and ppc64le). For the GPU Operator set,
1.1 GiB became 2.3 GiB. The upside: your arm64 node pool, if you ever have
one, won't send you back to the internet.

**2. crane, no re-pull.** `crane` is a static Go binary (no install, no
root), and it reads OCI layouts natively:

```
crane push images/nvidia_gpu-operator__v26.3.3.tar harbor02/nvidia/gpu-operator:v26.3.3
```

It's the cheapest in bytes. It does mean getting one more binary through
the airlock.

**3. skopeo**, if it happens to be there. `skopeo copy oci-archive:... docker://...`.
Usually it isn't.

(There's a fourth: stand up a local `registry:2`, crane-push into it, then
`imgpkg copy -i localhost:5000/... --to-repo harbor02/...`. It's strictly
more work than 1 or 2. Don't.)

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

That settles three things:

1. **The human tag survives.** The destination gets `:v0.13.1` *and*
   imgpkg's `:sha256-<hex>.imgpkg`. This matters, because Helm values
   reference images by tag. (Only `--repo-based-tags` changes the tag
   shape; don't pass it.)
2. **Digests survive** at both the manifest-list and per-platform level.
3. **The amd64 bits are identical** to the OCI archive. A re-pull is a
   re-packaging, not different content.

One trap: pinning by digest (`imgpkg copy -i repo@sha256:...`) *would*
keep it single-arch and small. But then there's no tag to carry across.
The destination only gets `:sha256-<hex>.imgpkg`, and your Helm values
break. Don't do that either.

## The one that bites later: signatures

imgpkg **drops cosign signatures by default** at every copy. That matters
when the thing you're loading is a platform bundle whose consumer checks
signatures. VKS supervisor services on VCF 9.0.1+ do, for versions above
3.4.0 from a private registry.

Every content check passes and the activation proceeds, so for a while
everyone is happy. Then every new control-plane pod is denied by a
webhook, for running "in an untrusted namespace".

Pull and push both need `--cosign-signatures`. The `.sig` artifacts are
separate tags (`sha256-<digest>.sig`), about 100 KB for a whole bundle. So
if the content is already in the registry, you can ship just the
signatures.

That one gets [its own post](/series/dark-site-notes/).

## Why this matters outside the lab

Air-gapped customers pay for every failed transfer twice: once in the
change window that slipped, and once in the import/export cycle to try
again.

Staging discipline is the whole game. Know which tool wrote each archive,
and what survives a copy. Prove the load against a throwaway registry
*before* anything crosses the airlock. That rehearsal is a fixed part of
how we prepare dark-site deliveries, and it's why the loading step is the
boring part on the day. Boring is underrated at a dark site.

## Rules learned

- Run `tar -tf x.tar | head` before anything else. `manifest.json` means
  imgpkg; `oci-layout` means an OCI archive. They are not interchangeable.
- imgpkg loads **only** imgpkg tars. No converter exists.
- OCI archives load with `crane push` (static binary) or skopeo.
- `imgpkg copy` copies **all platforms** (bigger) and preserves tags and
  digests (verified). Pin by tag, never by digest, when Helm values
  reference tags.
- Add `--cosign-signatures` on both ends when the consumer verifies
  bundles.
- Stage `imgpkg` *and* `crane` binaries with the tarballs. One of them
  will be the wrong tool for something.

## Broadcom documentation

- [Push Standard Packages to a Private Harbor Registry](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kuberenetes-service-clusters-and-workloads/using-private-registries-with-tkg-service-clusters/push-standard-packages-to-a-private-harbor-registry.html): `imgpkg copy --to-tar` on the connected side, `--tar ... --to-repo` into Harbor
- [Supporting Private Registries](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/vcf-services-development-guide/supervisor-services-carvel-private-registry.html): relocating Carvel bundles, and why omitting `--cosign-signatures` leaves a bundle untrusted
- [Upgrade VKS from a Private Registry](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kubernetes-service/installing-and-upgrading-the-tkg-service/upgrade-tkg-service-from-a-private-registry.html): the VKS bundle copied with `--cosign-signatures` on both copies
- [vSphere kubernetes service upgrade failed with "kapp: error waiting on reconcile packageinstall"](https://knowledge.broadcom.com/external/article/431379/vsphere-kubernetes-service-upgrade-faile.html): the untrusted-namespace denial when the signatures were dropped
- [Script to mirror resources for VPAIF-N AI workloads in air-gapped environment](https://knowledge.broadcom.com/external/article/388470): Broadcom's Docker-based script for mirroring Private AI container images, Helm charts and models into Harbor

---
*Lab environment; opinions my own. Verified against a local registry with
real multi-arch images; digests shown are truncated.*
