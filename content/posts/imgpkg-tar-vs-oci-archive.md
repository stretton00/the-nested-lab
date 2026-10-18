---
title: "imgpkg tar vs OCI archive: why your air-gap tarballs won't load"
date: 2026-10-14
lastmod: 2026-10-18
draft: false
tags: [air-gap, harbor, imgpkg, crane, oci, vks, gpu-operator]
products: ["VKS", "Private AI"]
series: ["Dark Site Notes"]
seriesPart: 1
tldr:
  - "The VKS bundle loaded into Harbor first time, while the GPU Operator images, same tool and same command, failed."
  - "imgpkg reads only its own tar layout, so an OCI archive needs `crane push` (unpacked first), skopeo or a re-pull with imgpkg."
  - "Run `tar -tf` first, and stage both `imgpkg` and `crane`: one of them will be the wrong tool for something."
cover:
  image: "/images/post12-hero-imgpkg.svg"
  alt: "Two tarballs that look the same: manifest.json vs oci-layout"
  hidden: false
summary: "Two tarballs full of container images, both bound for the same Harbor. imgpkg loads one and rejects the other. The layout difference nobody explains, what survives a copy, and three ways across."
---

You've staged about 40 container images for a dark site: 14 for the GPU
Operator (seven components, two versions of each), and the rest inside
the VKS bundle. The VKS bundle loads into Harbor first time with
`imgpkg copy --tar`. The GPU Operator images, same tool and same command,
fail (this is imgpkg 0.48.1):

```
$ imgpkg copy --tar images/nvidia_gpu-operator__v26.3.3.tar --to-repo supHarbor.example.com/nvidia/gpu-operator
imgpkg: Error: file manifest.json not found in tar (hint: This may be because when copying to a tarball, the --include-non-distributable-layers flag should have been provided.)
```

Both are tarballs. Both contain the images. What's different?

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

The hint in the error points at the wrong flag. Non-distributable layers
have nothing to do with it: `manifest.json` is missing because imgpkg
didn't write this tar.

## Two layouts that look the same from the outside

| Archive | Layout | `imgpkg copy --tar`? |
|---|---|---|
| Written by a registry-API puller / `crane pull --format=oci` / skopeo | **OCI image layout**: `oci-layout`, `index.json`, `blobs/sha256/*` | **No** |
| Written by `imgpkg copy --to-tar` | **imgpkg tar**: `manifest.json`, `sha256-*.tar.gz` | Yes |

imgpkg reads *only* the tar format imgpkg itself writes. There's no
converter: `imgpkg push -f <dir>` would wrap the OCI directory as a new
image *layer*, not replicate the original image. If your staging pipeline
pulled with anything other than imgpkg, imgpkg won't load it. Full stop.

Ours did. The staging host had no running Docker, no skopeo and no
imgpkg, and I'm not a local admin there, so installing them was off the
table. A small Python script pulled the images anonymously over the
registry API (v2) and wrote OCI layouts. Every digest checked out. It was
the right content in the wrong wrapper.

![Two tarballs: an imgpkg tar (manifest.json, sha256-*.tar.gz) loads with imgpkg copy --tar; an OCI image layout (oci-layout, index.json, blobs) does not, and loads with crane push once unpacked to a directory, or with skopeo. imgpkg's copy keeps tags, digests and platforms, and drops cosign signatures unless both ends ask for them](/images/diagrams/imgpkg-which-tool.svg)
*Same tool, same command, different archive. `tar -tf` tells you which one you've got.*

## Three ways out

**1. Re-pull with imgpkg** (chosen, when you still have internet somewhere):

```
imgpkg copy -i nvcr.io/nvidia/gpu-operator:v26.3.3 --to-tar gpu-operator.tar --registry-anon --resume
# at the dark site:
imgpkg copy --tar gpu-operator.tar --to-repo supHarbor.example.com/nvidia/gpu-operator
```

`--registry-anon` works because nvcr.io and registry.k8s.io serve these
images anonymously, so no NGC (NVIDIA GPU Cloud) key is involved.
`--resume` picks up an interrupted `--to-tar` where it stopped, instead
of starting again.

The cost: a second download, and it's **bigger**. `imgpkg copy` has no
platform filter, so you get every architecture in the manifest list
(amd64 and arm64, sometimes s390x and ppc64le). For the GPU Operator set,
1.1 GiB became 2.3 GiB.

In fairness to imgpkg, the small number was ours. Our script kept only
linux/amd64 from each image index; staging with `skopeo copy --all` would
have brought every architecture too. Per image, the gpu-operator v26.3.3
archive went from 132 MB to 256 MB. node-feature-discovery v0.18.3, with
four architectures, went from 80 MB to 300 MB. The upside: your arm64
node pool, if you ever have one, won't send you back to the internet.

**2. crane, no re-pull.** `crane` is a static Go binary (no install, no
root). `crane push` takes either a Docker-style tarball (one with a
`manifest.json`) or an OCI layout *directory*. An OCI archive is neither
until you unpack it, so hand it the `.tar` and it makes the same complaint
as imgpkg:

```
$ crane push images/nvidia_gpu-operator__v26.3.3.tar supHarbor.example.com/nvidia/gpu-operator:v26.3.3
Error: loading images/nvidia_gpu-operator__v26.3.3.tar as tarball: file manifest.json not found in tar
```

Unpack it, then push the directory:

```
mkdir gpu-operator && tar -xf images/nvidia_gpu-operator__v26.3.3.tar -C gpu-operator
crane push gpu-operator supHarbor.example.com/nvidia/gpu-operator:v26.3.3
```

Give crane the tag: push to a repository with no tag and the image lands
as `:latest`. If you stage with crane in the first place,
`crane pull --format=oci` writes a directory rather than a tarball, which
is exactly what `crane push` wants at the other end.

It's the cheapest in bytes. It does mean getting one more binary through
the airlock. And the tag lands on a different digest. Our archives held
only the amd64 image, so on this path the tag points at the amd64
manifest, not at upstream's manifest-list digest. Anything pinned to the
upstream `@sha256:` won't match.

**3. skopeo**, if it happens to be there. It reads the archive as it is:

```
skopeo copy --all oci-archive:<file>.tar docker://supHarbor.example.com/<path>:<tag>
```

Usually it isn't there.

(There's a fourth: stand up a local `registry:2`, crane-push into it, then
`imgpkg copy -i localhost:5000/... --to-repo supHarbor.example.com/...`. It's strictly
more work than 1 or 2. Don't.)

imgpkg is a static Go binary too, so neither tool needs installing or
root on a locked-down loading host. We carried imgpkg v0.48.1 and crane
v0.21.9, each checked against the SHA-256 checksums its project
publishes. You need imgpkg at the dark site whichever path you take,
because the VKS bundle is a real imgpkg bundle.

## What survives the copy (verified, not assumed)

I tested this against a throwaway `crane registry serve` with a real
multi-arch image, because "the digest should be preserved" is the kind of
sentence that precedes a bad week. `crane registry serve --address 127.0.0.1:5099`
is a whole registry in one command. It keeps everything in memory, so
add `--disk <dir>` for a big set.

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

The `.digest` sidecar in that last comment is a small text file our
staging script wrote beside each archive, holding the digest it pulled.
It's how you prove later that what landed is what left.

That settles three things:

1. **The human tag survives.** The destination gets `:v0.13.1` *and*
   imgpkg's `:sha256-<hex>.imgpkg`. The tar's `manifest.json` records the
   tag, and imgpkg re-applies it at the destination. This matters,
   because Helm values reference images by tag. (Only `--repo-based-tags`
   changes the tag shape; don't pass it.)
2. **Digests survive** at both the manifest-list and per-platform level.
3. **The amd64 bits are identical** to the OCI archive. A re-pull is a
   re-packaging, not different content. That held for all 14 images:
   every amd64 digest matched the original archive's.

Then the whole hand-over pack went through its own loader script into a
disk-backed local registry: 1 bundle and 14 images, every tag and digest
verified.

One trap: pinning by digest (`imgpkg copy -i repo@sha256:...`) *would*
keep it single-arch and small. But then there's no tag to carry across.
The destination only gets `:sha256-<hex>.imgpkg`, and your Helm values
break. Don't do that either.

## Loading into Harbor

Harbor has a few rules of its own, whichever tool you use. Here they are
in the order you'll meet them.

**Check the transfer first.** Ship a SHA-256 manifest with the pack, and
check it before you load anything:

```
sha256sum -c MANIFEST.sha256 --quiet && echo "PACK OK"
```

A bad copy found now costs a re-copy. Found halfway through a push, it
looks like a registry problem.

**Create the projects.** Harbor rejects a push into a project that
doesn't exist. Create them first, in the UI or through the API:

```
curl -u '<admin-user>' -X POST https://supHarbor.example.com/api/v2.0/projects \
  -H 'Content-Type: application/json' \
  -d '{"project_name": "nvidia", "metadata": {"public": "true"}}'
```

Public matters in this design. The Supervisor fetches the VKS bundle and
the nodes pull their images anonymously, with no pull secret anywhere. A
private project fails those pulls with a misleading `repository not found`.

**Push by FQDN, never by IP.** Harbor's certificate lists DNS names only,
as Subject Alternative Names (SANs). Address it by IP and TLS fails, even
after you've trusted the CA:

```
x509: cannot validate certificate for <ip> because it doesn't contain any IP SANs
```

(`supHarbor.example.com` in these examples stands in for your registry's
own DNS name.)

**Trust the CA, each tool its own way.** imgpkg takes the CA file
directly with `--registry-ca-cert-path`. crane has no such flag: it uses
the operating system's trust store, or `--insecure`, which switches
verification off. Put the CA in the trust store rather than reach for
`--insecure`.

**Credentials.** imgpkg reads `IMGPKG_USERNAME` and `IMGPKG_PASSWORD`, or
`~/.docker/config.json`. Single-quote the password, so the shell leaves
any `$` or `!` in it alone. Pushing needs a Harbor admin, or a robot
account with the Developer role or above on the project.

```
export IMGPKG_USERNAME='<user>'
export IMGPKG_PASSWORD='<password>'
imgpkg copy --tar gpu-operator.tar --to-repo supHarbor.example.com/nvidia/gpu-operator \
  --registry-ca-cert-path /path/to/harbor-ca.crt
```

**No tag on the destination, and the path is yours.** `--to-repo` takes
a repository, not a tag, because the tag travels in the tar. Add
`:v26.3.3` and imgpkg refuses the reference. The destination path needn't
match the source either. We kept the registry's existing layout, so
`nvcr.io/nvidia/k8s/container-toolkit` landed as `nvidia/container-toolkit`:

```
imgpkg copy --tar nvidia_k8s_container-toolkit__v1.19.1.tar \
  --to-repo supHarbor.example.com/nvidia/container-toolkit
```

**Expect a push to drop, and retry.** In our rehearsal, roughly half the
large pushes dropped at least once. That rate was specific to our lab,
whose network later turned out to have a fault of its own. The lesson
stands anyway. imgpkg skips blobs already in the registry, so a re-run
resumes rather than starting again. Wrap each copy in a retry loop (ours
tries six times), and treat a re-run as normal, not as a failure:

```
for i in 1 2 3 4 5 6; do
  imgpkg copy --tar gpu-operator.tar --to-repo supHarbor.example.com/nvidia/gpu-operator && break
  echo "retry $i of 6"
done
```

**Verify against what you recorded.** Compare every tag and digest with
the sidecars you wrote at staging:

```
imgpkg tag list -i supHarbor.example.com/nvidia/gpu-operator --digests
```

For the imgpkg tars we keep two sidecars. `.digest` holds the
manifest-list digest, which is what the tag points at after an imgpkg
load. `.amd64.digest` holds the amd64 child, which matches the old OCI
archive's sidecar. crane is the better tool for poking at what landed:

```
crane ls supHarbor.example.com/nvidia/gpu-operator
crane digest supHarbor.example.com/nvidia/gpu-operator:v26.3.3
crane manifest supHarbor.example.com/nvidia/gpu-operator:v26.3.3
crane digest --platform linux/amd64 supHarbor.example.com/nvidia/gpu-operator:v26.3.3
```

**Check repository names through the API, not by eye.** The UI is a good
place to look and a poor place to check. Ask Harbor's API, and grep for
the exact name you expect:

```
curl -s 'https://supHarbor.example.com/api/v2.0/projects/nvidia/repositories?page_size=100' | grep -o '"name":"[^"]*"'
```

## The one that bites later: signatures

imgpkg **drops cosign signatures by default** at every copy. That matters
when the thing you're loading is a platform bundle whose consumer checks
signatures. The VKS Supervisor Service on VCF 9.0.1 and 9.0.2 does, for
VKS versions above 3.4.0 from a private registry
([KB 429547](https://knowledge.broadcom.com/external/article/429547/supervisor-upgrade-stuck-after-upgrading.html)).
Our 9.1 lab never enforced it, so the rehearsal couldn't catch it.

Pull and push both need `--cosign-signatures`. The VKS bundle also needs
`-b`, which copies the bundle and every image it references:

```
imgpkg copy -b projects.packages.broadcom.com/vsphere/iaas/vsphere-kubernetes-service/3.6.3/vsphere-kubernetes-service:3.6.3 \
  --to-tar vks.tar --cosign-signatures
# at the dark site:
imgpkg copy --tar vks.tar --to-repo supHarbor.example.com/vks/vsphere-kubernetes-service --cosign-signatures
```

The registry tag is plain `3.6.3`. The `+v1.35` in the service's version
isn't legal in a tag.

Leave the flag off and every content check still passes. The digest
equals the vendor's, `imgpkg describe -b` walks all 39 refs, and the tag
list is complete. The activation proceeds, so for a while everyone is
happy. Then every new VKS service pod on the Supervisor's control-plane
VMs (namespace `svc-tkg-domain-cXX`) is denied by the webhook
`validate.cpvmpod.appplatform.vmware.com`:

```
running pod in an untrusted namespace on the control plane VM is not allowed
```

The appplatform logs add `Package bundle is not trusted`. Old-version
pods keep running throughout, so it's a stuck upgrade rather than an
outage.
[KB 431379](https://knowledge.broadcom.com/external/article/431379/vsphere-kubernetes-service-upgrade-faile.html)
covers the same denial.

**Count the signatures before you activate.** They're separate tags,
`sha256-<digest>.sig`, and VKS 3.6.3 has 27:

```
$ imgpkg tag list -i supHarbor.example.com/vks/vsphere-kubernetes-service | grep -c '\.sig$'
27
```

Harbor shows them as accessories of the bundle, with a "signed" mark.
They're small: 27 signatures come to about 96 KB gzipped (about 20 KB
each unpacked). The signed bundle tar is only about 0.5 MB bigger than the
unsigned one.

So if the content is already in the registry, you can ship just the
signatures. Each per-signature tar carries its own `sha256-<digest>.sig`
tag, which `imgpkg copy --tar` re-applies. The gzipped set survives
base64 through email; check its SHA-256 at the far end before you
unpack it.

Adding signatures doesn't change the bundle digest, so there's no
re-registration. The fix order is: push the signatures, then restart the
appplatform operator with
`kubectl rollout restart deployment -n vmware-system-appplatform-operator-system`.
The rest of the recovery gets [its own post](/series/dark-site-notes/).

One more timing trap. Signature verification runs after you register the
new service version, so activating straight after the upload can fail
with `signature verification result not found`. Wait a few minutes and
retry. And don't read anything into `trust_verified`: it can say `False`
even on versions that work.

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
- imgpkg loads **only** imgpkg tars. No converter exists, and the error's
  hint about `--include-non-distributable-layers` is a red herring.
- OCI archives load with `crane push` or skopeo. crane wants the archive
  unpacked to a directory, not the `.tar`, and a tag on the destination.
- `imgpkg copy` copies **all platforms** (bigger) and preserves tags and
  digests (verified). Pin by tag, never by digest, when Helm values
  reference tags.
- `--to-repo` takes a repository with no `:tag`. The tag travels in the
  imgpkg tar.
- Push by FQDN, and create the Harbor projects first. imgpkg takes the CA
  with `--registry-ca-cert-path`; crane has no CA flag and uses the OS
  trust store.
- Add `--cosign-signatures` on both ends when the consumer verifies
  bundles, and count the `.sig` tags before you activate.
- Stage `imgpkg` *and* `crane` binaries with the tarballs. The VKS bundle
  needs imgpkg whichever way the images go, and one of the two will be the
  wrong tool for something.

## Broadcom documentation

- [Push Standard Packages to a Private Harbor Registry](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kuberenetes-service-clusters-and-workloads/using-private-registries-with-tkg-service-clusters/push-standard-packages-to-a-private-harbor-registry.html): `imgpkg copy --to-tar` on the connected side, `--tar ... --to-repo` into Harbor
- [Supporting Private Registries](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/vcf-services-development-guide/supervisor-services-carvel-private-registry.html): relocating Carvel bundles, and why omitting `--cosign-signatures` leaves a bundle untrusted
- [Upgrade VKS from a Private Registry](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kubernetes-service/installing-and-upgrading-the-tkg-service/upgrade-tkg-service-from-a-private-registry.html): the VKS bundle copied with `--cosign-signatures` on both copies
- [vSphere kubernetes service upgrade failed with "kapp: error waiting on reconcile packageinstall"](https://knowledge.broadcom.com/external/article/431379/vsphere-kubernetes-service-upgrade-faile.html): the untrusted-namespace denial when the signatures were dropped
- [Supervisor upgrade stuck after upgrading to 9.0.2 error "vmware-system-vks-public user=system:serviceaccount:svc-tkg-domain-:runtime-extension- pkg-sa: prohibited operation on system namespace"](https://knowledge.broadcom.com/external/article/429547/supervisor-upgrade-stuck-after-upgrading.html): on VCF 9.0.1 and 9.0.2, VKS above 3.4.0 needs signed packages in the private registry
- [Script to mirror resources for VPAIF-N AI workloads in air-gapped environment](https://knowledge.broadcom.com/external/article/388470): Broadcom's Docker-based script for mirroring Private AI container images, Helm charts and models into Harbor

---
*Lab environment; opinions my own. Verified against a local registry with
real multi-arch images; digests shown are truncated.*
