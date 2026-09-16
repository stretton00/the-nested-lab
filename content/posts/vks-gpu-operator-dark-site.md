---
title: "VKS and the GPU Operator in a dark site: the whole airlock"
date: 2026-11-11
draft: false
tags: [air-gap, vks, gpu-operator, nvidia, harbor, imgpkg, cosign, kernel-headers, vcf]
series: ["Dark Site Notes"]
cover:
  image: "/images/post21-hero-darksite.svg"
  alt: "Everything that has to cross the airlock: images, signatures, node OVAs, kernel headers, licences"
  hidden: false
summary: "Upgrading VKS, the Kubernetes release and the NVIDIA GPU Operator with no internet is five supply chains that all have to arrive intact — images, cosign signatures, node OVAs, kernel headers, licences. Each has a trap that passes every check until activation. This is the map."
---

A dark-site upgrade of VKS + Kubernetes release + GPU Operator looks like
one project. It's five supply chains, and every one of them has a failure
mode that **passes every reasonable check and then fails at activation**.
I've now been through all five. This is the long post; the short version
is the table at the end.

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
from a private registry **unless the bundle's cosign signatures are in the
registry**. The `.sig` artifacts are separate tags (`sha256-<digest>.sig`),
and `imgpkg copy` drops them by default at *every* copy — pull and push.

Failure shape: digest matches the vendor's, `imgpkg describe` walks all 39
refs clean, the tag list is complete, activation proceeds… and then every
new pod in `svc-tkg-domain-cXX` is denied by the webhook
`validate.cpvmpod.appplatform.vmware.com`: *running pod in an untrusted
namespace on the control plane VM is not allowed*. The package install
flips `Reconciling`/`failed` forever. Old-version pods keep running —
Deployment surge protects the service — so it isn't an outage, it's a stuck
upgrade.

```
imgpkg copy -b <bundle> --to-tar vks.tar --cosign-signatures
imgpkg copy --tar vks.tar --to-repo harbor02/vks/vsphere-kubernetes-service --cosign-signatures
kubectl rollout restart deployment -n vmware-system-appplatform-operator-system
```

The bundle digest is unchanged by adding signatures, so no re-registration.
And if the content is already in the registry, the signatures alone are
~100 KB — small enough to base64 through email.

Lab tolerance lesson: the 9.1 lab never enforced this. A rehearsal that
can't hit the gate can't prove you're through it.

## 2. Images, and one composed tag

The [tar-format problem](/posts/imgpkg-tar-vs-oci-archive/) has its own
post. The trap unique to the GPU Operator: **the driver image tag is
composed at runtime** as `<driver.version>-<os>`. Values say `580.105.08`;
the pullable artifact is `580.105.08-ubuntu22.04`. Stage the composed tag;
keep the bare version in values. Get it backwards and the driver pod
`ImagePullBackOff`s with a tag that looks right.

Four gates, run before every Helm upgrade, each of which caught something
real:

1. **Values leaf-diff** against the live release — found a phantom
   `driver.nodeSelector` targeting a label the nodes didn't carry, which
   would have matched zero nodes and removed all 14 driver pods.
2. **An assertion script** over the merged values (fails on the presence
   of that selector, checks drain timeout matches live).
3. **An image pull test** — a DaemonSet with every image the new chart
   references, selected on `gpu.deploy.driver=true`. `DESIRED` must equal
   the GPU node count. It read 0 the first time: right context, phantom
   selector.
4. **A render diff** — `helm template` old vs new, eyes on every changed
   line.

Also new in 25.10+: `cdi.enabled` flips default; pin it. And a fleet with
multi-replica LLMs and no PodDisruptionBudgets went fully down mid-roll —
reload slower than drain cadence — and self-healed. Add PDBs *before* the
node roll.

## 3. The version gate is on the running supervisor

VKS service YAMLs carry `kubernetesVersionSelection.constraints`. 3.7.1
says `>=1.32.0`. "VCF 9.0.1 ships Kubernetes 1.32" is a true statement
about what the release *makes available* and a false one about what a
given supervisor is *running* — ours was `1.31.6`, at the ceiling for its
vSphere version, and the build string encodes it (`...-vsc9.0.1.0`). The
real prerequisite for that VKS version was a VCF fleet upgrade, not a
download.

Measure it: `GET /api/vcenter/namespace-management/software/clusters`.
Then pick the highest VKS whose constraint the *running* version satisfies
(3.6.3 for us), and take the Kubernetes release hops that VKS supports.

## 4. Kernel headers: the side repo that vanishes

The NVIDIA driver container compiles against the node kernel and needs
`linux-headers-<ver>` — plus, it turned out, the kernel **image** and
**modules** packages — from an apt source. The dark-site Ubuntu mirror was
`apt-mirror` served by Apache, indexes upstream-verbatim and Ubuntu-signed,
so they **cannot be edited** to add packages. Hence a flat side repo:

```
Alias /nvhdrs /var/www/html/nvhdrs        # OUTSIDE the mirror's DocumentRoot
```

Outside on purpose: apt-mirror's generated `clean.sh` deletes anything
under its spool that isn't in the upstream index. A side repo placed
inside would serve correctly and then silently vanish on the next mirror
run.

The mirror host was Photon — no `dpkg-deb`, no `apt-ftparchive` — so the
`Packages` index was assembled from the upstream stanzas with
`sed 's|^Filename: pool/main/l/linux/|Filename: ./|'`, and a `Release` file
built with `sha256sum`/`stat`/`date -Ru`. apt 2.4 rejects a flat repo
without `Release`, even with `[trusted=yes]`. Verify from a *jammy* host or
the driver pod — never from the Photon server, which has no apt.

One timing fact: the driver container keeps `archive.ubuntu.com` in its own
`sources.list`, so every `apt-get update` times out for ~40 s before
falling back. Serially, per node, that's ~10 minutes per 14-node hop.
Harmless; budget for it.

## 5. Node internals nobody warns you about

Three findings from the node roll:

- **The container toolkit resets containerd's sandbox image.** On
  containerd 2.x nodes, the GPU Operator's toolkit rewrites the config and
  drops the air-gap pin, defaulting to `registry.k8s.io/pause:3.10.1`.
  Every post-toolkit pod fails sandbox creation. A guard DaemonSet
  (nsenter from the driver image, `sed` the pause ref back to the
  node-local registry, never touch `sandboxer`) runs permanently until a
  fresh node's guard log shows no repair.
- **`.local` is mDNS.** A site domain ending `.local` means the node
  resolver multicasts for the registry, the licence server and the vSAN
  file-service endpoints. A per-release hosts-injector DaemonSet (pinned
  to the `run.tanzu.vmware.com/tkr` label, images from the node-local
  `localhost:5000`) writes seven `/etc/hosts` entries every 60 s.
- **Pace by the workloads, not the platform.** Every node replacement is
  fast; the LLM replicas moved off it take 12–20 minutes to pass health
  checks (`:8000/health` refuses while loading). One GPU machine at a
  time, pause the Cluster (`spec.paused`) between, ~25–30 min per node.

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

## Rules learned

- Five supply chains, not one. List them before you start.
- `--cosign-signatures` on **both** ends of every imgpkg copy that feeds a
  trust-checking consumer.
- Stage the **composed** driver tag; keep the bare version in values.
- Gate every values change four ways: leaf-diff, assert, pull-test,
  render-diff. Each caught something.
- The version gate is on the *running* supervisor. Measure; don't infer
  from the release notes.
- Side repos live **outside** the mirror's DocumentRoot.
- On containerd 2.x + GPU Operator, guard the sandbox image. On `.local`
  domains, inject hosts.
- Roll GPU nodes at the pace the *workloads* recover. Add PDBs first.
- A lab that can't hit the prod gate proves nothing about the gate. Know
  which gates your rehearsal *cannot* exercise and say so in the runbook.

---
*Techniques from a real air-gapped engagement, generalised; identifiers
removed. Opinions my own.*
