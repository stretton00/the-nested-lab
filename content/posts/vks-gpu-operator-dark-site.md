---
title: "VKS and the GPU Operator in a dark site: the whole airlock"
date: 2026-10-21
draft: false
tags: [air-gap, vks, gpu-operator, nvidia, harbor, imgpkg, cosign, kernel-headers, vcf]
products: ["VKS", "Private AI"]
series: ["Dark Site Notes"]
seriesPart: 2
tldr:
  - "With no internet, upgrading VKS, the Kubernetes release and the GPU Operator is not one project but five supply chains."
  - "Each one has a trap that passes every reasonable check and saves its failure for activation, like missing cosign signatures."
  - "List all five before you start, and know which gates your rehearsal lab cannot reach, because it proves nothing about them."
cover:
  image: "/images/post21-hero-darksite.svg"
  alt: "Everything that has to cross the airlock: images, signatures, node OVAs, kernel headers, licences"
  hidden: false
summary: "Upgrading VKS, the Kubernetes release and the NVIDIA GPU Operator with no internet is five supply chains that all have to arrive intact — images, cosign signatures, node OVAs, kernel headers, licences. Each has a trap that passes every check until activation. This is the map."
---

A dark-site upgrade of VKS, a Kubernetes release and the GPU Operator looks
like one project. It's actually five supply chains. Every one of them has a
failure mode that **passes every reasonable check and then fails at
activation**.

I've now been through all five. This is the long post; the short version
is the table at the end. I'd recommend the table over the experience.

## The five things that cross the airlock

| # | Payload | Format | Consumer | The trap |
|---|---|---|---|---|
| 1 | VKS supervisor-service bundle | imgpkg tar | Supervisor Service framework | **cosign signatures dropped** by default |
| 2 | GPU Operator + driver images | OCI archive / imgpkg tar | Helm on the workload cluster | [tar layout mismatch](/posts/imgpkg-tar-vs-oci-archive/); driver **tag composition** |
| 3 | Kubernetes release node OVAs | OVA → Content Library | VKS | version gate on the *running* supervisor, not the release |
| 4 | Kernel headers (+ image + modules) | .deb → side repo | driver container's `apt` | apt-mirror's `clean.sh` **deletes side repos** |
| 5 | vGPU licences | DLS appliance | driver | `.local` site domain → **mDNS**; needs a hosts injector |

## 1. The signatures you didn't know you dropped

VCF 9.0.1+ withholds control-plane-VM trust for VKS versions above 3.4.0
from a private registry, **unless the bundle's cosign signatures are in the
registry**. The `.sig` artifacts are separate tags (`sha256-<digest>.sig`).
And `imgpkg copy` drops them by default at *every* copy, pull and push
alike.

The failure looks like this. Everything checks out:

- the digest matches the vendor's;
- `imgpkg describe` walks all 39 refs clean;
- the tag list is complete;
- activation proceeds.

And then every new pod in `svc-tkg-domain-cXX` is denied by the webhook
`validate.cpvmpod.appplatform.vmware.com`: *running pod in an untrusted
namespace on the control plane VM is not allowed*. The package install
flips `Reconciling`/`failed` forever.

Old-version pods keep running, because Deployment surge protects the
service. So it isn't an outage. It's a stuck upgrade.

```
imgpkg copy -b <bundle> --to-tar vks.tar --cosign-signatures
imgpkg copy --tar vks.tar --to-repo harbor02/vks/vsphere-kubernetes-service --cosign-signatures
kubectl rollout restart deployment -n vmware-system-appplatform-operator-system
# then force a fresh attempt, now the signatures are in
kubectl -n svc-tkg-domain-<cluster> get deploy -o name | xargs -I{} kubectl -n svc-tkg-domain-<cluster> rollout restart {}
```

The operator-namespace restart cycles that namespace's Deployments.
[KB 431379](https://knowledge.broadcom.com/external/article/431379/vsphere-kubernetes-service-upgrade-faile.html)
restarts the operator's StatefulSet instead:
`kubectl rollout restart sts -n vmware-system-appplatform-operator-system vmware-system-appplatform-operator-mgr`.

Adding signatures doesn't change the bundle digest, so there's no
re-registration. And if the content is already in the registry, the
signatures alone are about 100 KB: small enough to base64 through email.

Lab tolerance lesson: the 9.1 lab never enforced this, which was very kind
of it, and no use whatsoever. A rehearsal that can't hit the gate can't
prove you're through it.

## 2. Images, and one composed tag

The [tar-format problem](/posts/imgpkg-tar-vs-oci-archive/) has its own
post. The trap unique to the GPU Operator is that **the driver image tag is
composed at runtime**, as `<driver.version>-<os>`. Values say `580.105.08`;
the pullable artifact is `580.105.08-ubuntu22.04`.

Stage the composed tag, and keep the bare version in values. Get it
backwards and the driver pod `ImagePullBackOff`s with a tag that looks
right, which is the most irritating way for a tag to be wrong.

Four gates run before every Helm upgrade, and each one caught something
real:

1. **Values leaf-diff** against the live release. It found a phantom
   `driver.nodeSelector` targeting a label the nodes didn't carry. That
   would have matched zero nodes and removed all 14 driver pods.
2. **An assertion script** over the merged values. It fails on the
   presence of that selector, and checks the drain timeout matches live.
3. **An image pull test**: a DaemonSet with every image the new chart
   references, selected on `gpu.deploy.driver=true`. `DESIRED` must equal
   the GPU node count. It read 0 the first time: right context, phantom
   selector.
4. **A render diff**: `helm template` old versus new, with eyes on every
   changed line.

Also new in 25.10+: `cdi.enabled` flips its default, so pin it.

And a fleet with multi-replica LLMs and no PodDisruptionBudgets (PDBs) went
fully down mid-roll, because the reload was slower than the drain cadence.
It self-healed. Add PDBs *before* the node roll.

## 3. The version gate is on the running supervisor

VKS service YAMLs carry `kubernetesVersionSelection.constraints`, and 3.7.1
says `>=1.32.0`. The statement "VCF 9.0.1 ships Kubernetes 1.32" is true
about what the release *makes available*. It's false about what a given
supervisor is *running*.

Ours was `1.31.6`, at the ceiling for its vSphere version, and the build
string encodes it (`...-vsc9.0.1.0`). So the real prerequisite for that VKS
version was a VCF fleet upgrade, not a download. A slightly larger job,
then.

Measure it: `GET /api/vcenter/namespace-management/software/clusters`.
Then pick the highest VKS whose constraint the *running* version satisfies
(3.6.3 for us), and take the Kubernetes release hops that VKS supports.

## 4. Kernel headers: the side repo that vanishes

The NVIDIA driver container compiles against the node kernel. It needs
`linux-headers-<ver>` from an apt source, plus, it turned out, the kernel
**image** and **modules** packages.

The dark-site Ubuntu mirror was `apt-mirror` served by Apache. Its indexes
are upstream-verbatim and Ubuntu-signed, so they **cannot be edited** to
add packages. Hence a flat side repo:

```
Alias /nvhdrs /var/www/html/nvhdrs        # OUTSIDE the mirror's DocumentRoot
```

Outside on purpose: apt-mirror's generated `clean.sh` deletes anything
under its spool that isn't in the upstream index. A side repo placed
inside would serve correctly, then silently vanish on the next mirror run,
tidied away by a script that was only trying to help.

The mirror host was Photon, with no `dpkg-deb` and no `apt-ftparchive`.
So we assembled the `Packages` index from the upstream stanzas with
`sed 's|^Filename: pool/main/l/linux/|Filename: ./|'`. We built a `Release`
file with `sha256sum`, `stat` and `date -Ru`. It has to exist: apt 2.4
rejects a flat repo without `Release`, even with `[trusted=yes]`.

Verify from a *jammy* host or the driver pod. Never verify from the Photon
server, which has no apt.

One timing fact: the driver container keeps `archive.ubuntu.com` in its own
`sources.list`. So every `apt-get update` times out for about 40 s before
falling back. Serially, per node, that's about 10 minutes per 14-node hop.
Harmless, but budget for it.

## 5. Node internals nobody warns you about

Three findings from the node roll:

- **The container toolkit resets containerd's sandbox image.** On
  containerd 2.x nodes, the GPU Operator's toolkit rewrites the config and
  drops the air-gap pin, defaulting to `registry.k8s.io/pause:3.10.1`.
  Every post-toolkit pod then fails sandbox creation. A guard DaemonSet
  runs permanently, until a fresh node's guard log shows no repair. It
  uses nsenter from the driver image, puts the pause ref back to the
  node-local registry with `sed`, and never touches `sandboxer`.
  [KB 429604](https://knowledge.broadcom.com/external/article/429604/nvidia-gpuoperator-pods-not-starting-in.html)
  fixes the same problem at install time instead, with a Helm setting we
  haven't tried: `RUNTIME_CONFIG_SOURCE=file=/etc/containerd/config.toml`
  in `toolkit.env`.
- **`.local` is mDNS.** With a site domain ending `.local`, the node
  resolver multicasts for the registry, the licence server and the vSAN
  file-service endpoints. A per-release hosts-injector DaemonSet writes
  seven `/etc/hosts` entries every 60 s. It's pinned to the
  `run.tanzu.vmware.com/tkr` label, and pulls its images from the
  node-local `localhost:5000`.
- **Pace by the workloads, not the platform.** Every node replacement is
  fast. The LLM replicas moved off it take 12–20 minutes to pass health
  checks (`:8000/health` refuses while loading). Do one GPU machine at a
  time, and pause the Cluster (`spec.paused`) in between: about 25–30 min
  per node.

## The map, compressed

| Check that passes | Failure it hides | Prove it with |
|---|---|---|
| bundle digest = vendor | signatures missing | `imgpkg tag list` shows `.sig` tags |
| tag list complete | driver tag composed differently | pull-test DS with the *composed* tag |
| `DESIRED 0` looks like "no work" | nodeSelector matches nothing | expect `DESIRED` = GPU node count |
| "9.0.1 ships 1.32" | supervisor runs 1.31 | `GET .../software/clusters` |
| side repo serves 200 | `clean.sh` will delete it | put it outside DocumentRoot |
| toolkit pod Running | containerd pause ref reset | guard DS log |
| DNS "works" | `.local` → mDNS | hosts injector |

## Why this matters outside the lab

For regulated and disconnected estates, the takeaway is that air-gapped
platform upgrades are entirely achievable. But they're a supply-chain
exercise, not a software one.

Every dependency has to be identified, staged, verified and rehearsed
before the change window. The gates that catch problems have to be built
in advance, because there's no internet to fall back on.

Organisations running GPU and AI workloads in these environments are
exactly who this is for. The platform can be kept current without ever
opening the network, provided the preparation is treated as the real work.

## Rules learned

- Five supply chains, not one. List them before you start.
- Use `--cosign-signatures` on **both** ends of every imgpkg copy that
  feeds a trust-checking consumer.
- Stage the **composed** driver tag; keep the bare version in values.
- Gate every values change four ways: leaf-diff, assert, pull-test,
  render-diff. Each caught something.
- The version gate is on the *running* supervisor. Measure; don't infer
  from the release notes.
- Side repos live **outside** the mirror's DocumentRoot.
- On containerd 2.x with the GPU Operator, guard the sandbox image. On
  `.local` domains, inject hosts.
- Roll GPU nodes at the pace the *workloads* recover. Add PDBs first.
- A lab that can't hit the prod gate proves nothing about the gate. Know
  which gates your rehearsal *cannot* exercise, and say so in the runbook.

## Broadcom documentation

- [Upgrade VKS from a Private Registry](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kubernetes-service/installing-and-upgrading-the-tkg-service/upgrade-tkg-service-from-a-private-registry.html): `imgpkg copy` with `--cosign-signatures` on both copies, then register the new version
- [Supervisor upgrade stuck after upgrading to 9.0.2 error "vmware-system-vks-public user=system:serviceaccount:svc-tkg-domain-:runtime-extension- pkg-sa: prohibited operation on system namespace"](https://knowledge.broadcom.com/external/article/429547/supervisor-upgrade-stuck-after-upgrading.html): on VCF 9.0.1 and 9.0.2, VKS above 3.4.0 needs signed packages in the private registry
- [vSphere kubernetes service upgrade failed with "kapp: error waiting on reconcile packageinstall"](https://knowledge.broadcom.com/external/article/431379/vsphere-kubernetes-service-upgrade-faile.html): the untrusted-namespace webhook denial, and re-copying with signatures
- [VMware vSphere Kubernetes Service 3.7 Release Notes](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/release-notes/vks-release-notes/vmware-tanzu-kubernetes-grid-service-37-release-notes.html): VKS 3.7 needs Supervisor Kubernetes 1.32 or later
- [Provide an Ubuntu Package Repository Mirror and vGPU Drivers for Deep Learning VMs and VKS Clusters with GPU in a Disconnected Environment](https://techdocs.broadcom.com/us/en/vmware-cis/private-ai/foundation-with-nvidia/9-0/private-ai-foundation-9-x/deploying-private-ai-foundation-with-nvidia/finalizing-the-setup-for-deep-learning-vms-and-vks-cluster-with-gpu/provide-an-ubuntu-package-repository--mirror-and-vgpu-drivers-for---deep-learning-vms-and-vks-clusters-with-gpu-in-a-disconnected-environment.html): the local Ubuntu repository the driver build compiles against
- [NVIDIA gpu-operator pods not starting in air-gapped environment with VKr 1.33 (or higher) showing error "failed to get sandbox image "registry.k8s.io/pause:3.10": failed to pull image "registry.k8s.io/pause:3.10": "](https://knowledge.broadcom.com/external/article/429604/nvidia-gpuoperator-pods-not-starting-in.html): the GPU Operator's containerd drop-in losing the air-gapped sandbox image, and a toolkit setting that avoids it

---
*Techniques from a real air-gapped engagement, generalised; identifiers
removed. Opinions my own.*
