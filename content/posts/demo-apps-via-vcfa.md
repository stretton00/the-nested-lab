---
title: "Seven demo apps, one request: deploying a showcase stack via VCF Automation"
date: 2027-01-06
draft: true
tags: [vcf, vks, vcf-automation, all-apps, demo, kubernetes, pacman]
series: ["All Apps in Practice"]
cover:
  image: "/images/post11-hero-demo-apps.svg"
  alt: "Seven demo apps behind seven VIPs on one VCFA-deployed VKS cluster"
  hidden: false
summary: "KubeDoom, KubeInvaders, kube-ops-view, Pac-Man with persistent MongoDB, podinfo, Goldpinger and a Prometheus stack — deployed onto a VCFA-provisioned VKS cluster in a tenant VPC, each behind its own NSX VIP. The proper tenanted path (not the supervisor shortcut), what the platform does for free, and the traps."
---

Every platform needs a demo stack — something that looks alive on a
projector and quietly exercises every layer underneath. This is the lab's:
seven apps on a VKS cluster that VCF Automation provisioned, in a tenant
VPC, each app behind its own load-balancer VIP.

```
kubedoom       192.168.144.20:5900   (VNC — yes, it kills pods)
kubeinvaders   192.168.144.21
kube-ops-view  192.168.144.22
pacman         192.168.144.23        (+ MongoDB on a PVC — persistent high scores)
podinfo        192.168.144.24
goldpinger     192.168.144.25        (DaemonSet incl. control plane)
prometheus     (in-cluster: KSM + node-exporter, 11/11 targets up)
```

> **[SHOT]** Browser grid GIF: four tabs cycling — KubeDoom (VNC), KubeInvaders,
> kube-ops-view, Pac-Man. No login needed; grab any time.

## The path that matters: tenanted, not shortcut

The first version of this stack was deployed *against the supervisor* —
an admin kubeconfig, a vSphere namespace, `kubectl apply`. It worked and
it was wrong, for the reason the [previous
post](/posts/vks-kubectl-vs-vcfa-all-apps/) spells out: nothing about it
was *provided* to anyone. So it was torn down (seven apps, cluster, VPC and
VIPs gone in about seven minutes) and rebuilt the proper way:

```
dev-01 org → default-project → SupervisorNamespace (class large, region f06, VPC default-f06)
          → VKS cluster vks-demo01 → seven apps
```

All created **through VCF Automation** — the CCI API for the namespace and
cluster, then the apps via the cluster's own kubeconfig. Two auth facts
worth writing down, because they cost a cycle each:

- A **provider** service account reaches the cloud API only. CCI
  (`/cci/kubernetes/apis/...`) rejects provider tokens with 401 — it needs
  an **org-scoped** service account.
- Device-flow login uses the service account's own UUID as `client_id`
  (not its software ID), against the tenant endpoint
  `/oauth/tenant/<org>/device_authorization`.

![VCF Operations topology: the cluster with its apps named](/images/ui/u9-ops-vks-topology.jpg)

## What the platform does for free

Each app is an ordinary Deployment + `Service` of type `LoadBalancer`. The
supervisor turns each service into an NSX VPC LB virtual server and hands
back a VIP from the org's external block. No ingress controller, no
MetalLB, no port-forwarding — seven services, seven VIPs, done. Pac-Man's
MongoDB asks for a PVC and gets a vSAN-backed volume through the CSI the
supervisor already installed. Goldpinger runs as a DaemonSet across every
node including the control plane and draws the node-to-node mesh live.

That's three platform services (LB, storage, networking) exercised by apps
that know nothing about VCF.

## The traps

**Supervisor refuses cluster-scoped RBAC — even to admin.** Demo apps
that need ClusterRoles (kube-ops-view, Goldpinger, KubeDoom) *must* live
on a guest cluster. You cannot run them as vSphere Pods on the supervisor.

**PodSecurity `restricted` is the VKS 1.35 default.** Half the demo set
runs as root. Symptom: Deployment shows `0 UP-TO-DATE`, ReplicaSet exists,
zero pods, events say `FailedCreate`. Fix: label the namespace
`pod-security.kubernetes.io/enforce=privileged` — and mention in the demo
that you did, because it's a teaching moment.

**node-exporter without `hostNetwork`.** The VPC fabric blocks pod → node
IP scrapes, so the stock DaemonSet's `hostNetwork: true` doesn't help;
run it as a normal pod and let Prometheus scrape it in-cluster.

**Docker Hub is flaky from behind a proxy.** TLS handshake timeouts put
pods into kubelet's image-pull backoff. Deleting the stuck pods bypasses
the backoff; a Harbor proxy-cache project fixes it properly.

**Pod CIDR shadowing.** The stock `192.168.0.0/16` pod range hid the
org's `192.168.144.0/21` external block *from inside the cluster* — apps
couldn't reach their neighbours' VIPs. Pod CIDR is now `172.16.0.0/16`.

## Automation notes

The whole stack is a checkbox on the lab's catalog item that deploys a
supervisor: `installDemoApps` creates the cluster (newest compatible
Kubernetes release, newest built-in ClusterClass, auto-detected), applies
the seven apps, and reports their URLs in the deployment summary. Run
integrated on a fresh environment: 16.7 minutes to `CREATE_SUCCESSFUL`.
An immediate re-run: 3.3 minutes, all steps idempotent — which is the
number I actually care about, because it means a broken demo is a re-run,
not a rebuild.

## Rules learned

- Demo apps that need cluster-scoped RBAC **must** run on a guest cluster;
  the supervisor won't grant it, even to admin.
- Build the stack through the **tenanted path** (org SA → CCI → namespace
  → cluster → apps). Same apps, but now they're provided, quota'd and
  visible in Ops.
- VKS 1.35: `restricted` PodSecurity by default. Label the namespace and
  say why.
- `LoadBalancer` per app = NSX VIP per app. No ingress needed for a demo.
- Pick a pod CIDR that doesn't overlap the VPC external block.
- Make the deploy idempotent; a demo that re-runs in 3 minutes is one you
  can afford to break on stage.

*Previously: [one VKS cluster, two ways](/posts/vks-kubectl-vs-vcfa-all-apps/).
The Pac-Man instance here is the one from [What's a VPC?](/posts/whats-a-vpc-with-pacman/).*

---
*Lab environment; opinions my own.*
