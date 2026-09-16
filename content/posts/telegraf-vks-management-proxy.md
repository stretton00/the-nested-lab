---
title: "Telegraf on VKS: the dependency that isn't in the README"
date: 2026-09-23T06:10:00+01:00
draft: false
tags: [observability, telegraf, vks, kubernetes, vcf-operations, supervisor-services, coredns]
series: ["Observability on VCF"]
cover:
  image: "/images/post24-hero-telegraf-vks.svg"
  alt: "Telegraf pods stuck in FailedMount until the Supervisor Management Proxy exists; then a domainless service URL until serviceDomain is set"
  hidden: false
summary: "The VKS Telegraf package mounts two secrets that only the Supervisor Management Proxy service propagates into guest clusters. Without it every pod sits in FailedMount forever and nothing says why. Install the proxy and the chain heals itself — then a second trap: a domainless output URL on any cluster created without serviceDomain."
---

The [Windows half of this series](/posts/telegraf-windows-2025/) was a
story about an agent that works on an OS the vendor hasn't listed. This
one is the opposite: a package on a fully supported platform that does
nothing at all, silently, because of a dependency its documentation
doesn't mention.

## The symptom

Install the Telegraf package on a VKS cluster with the metric proxy flag
set — `isMetricProxyConfigured: true`, which is what you want if the
metrics are going to VCF Operations — and every Telegraf pod stays in
`ContainerCreating`. Describe one and the reason is `FailedMount`: two
secrets don't exist.

```
MountVolume.SetUp failed for volume "metrics-proxy-tls-config"  : secret not found
MountVolume.SetUp failed for volume "metrics-proxy-http-config" : secret not found
```

Nothing creates them. The package doesn't. The cluster doesn't. The
PackageInstall reports `ReconcileFailed` and backs off, and that's where
it stays.

## The dependency

Those two secrets are **published by the Supervisor Management Proxy**,
a Supervisor Service you install on the supervisor, not in the guest
cluster. It exports the proxy's TLS and HTTP config into every guest
cluster's `kube-system` as a `SecretExport`; a matching `SecretImport`
in `tanzu-system-telegraf` pulls them across. No proxy on the supervisor,
no export, no secrets, no pods.

```
Supervisor Management Proxy (Supervisor Service)
  └─ SecretExport  (guest kube-system)
       └─ SecretImport  (guest tanzu-system-telegraf)
            └─ metrics-proxy-tls-config + metrics-proxy-http-config
                 └─ Telegraf pods mount them → Running
```

The fix is one install on the supervisor, and it's retroactive: once the
proxy exists the exports appear, the imports follow, and pods that had
been failing to mount for a day come up on their own. The only nudge
needed was an annotation bump on the PackageInstall to clear the stale
`ReconcileFailed` backoff.

## The second trap: a URL with no domain

With pods running, Telegraf still wasn't delivering. Its output URL had
come out as:

```
https://supervisor-management-proxy.default.svc.:10093
```

Note the trailing dot and nothing after `svc`. The package builds that URL
from the cluster's service domain, and this cluster had been created
without `clusterNetwork.serviceDomain` — so the domain was empty. That
field is immutable after create.

Two fixes, both applied:

- **Live cluster:** a CoreDNS `rewrite` rule that maps the domainless name
  onto the real one. Ugly, effective, documented in the cluster's notes.
- **Every new cluster:** `serviceDomain: cluster.local` in the spec. Every
  add-on that constructs a service URL is assuming it's there.

## Why this matters outside the lab

Both traps have the same shape: a platform component that fails with a
generic symptom (`FailedMount`, a name that won't resolve) whose cause is
a decision made somewhere else — a service not installed on the
supervisor, a field left blank at cluster create. For a customer that
means two things. Metrics from Kubernetes workloads into VCF Operations
are a *platform* feature, so the supervisor has to be built for it, not
just the cluster. And cluster specs need a baseline that includes the
fields add-ons assume, because the immutable ones can't be fixed later.
This is exactly the kind of thing a standard cluster class and a
supervisor build checklist exist to encode.

## Rules learned

- On VKS, the Telegraf package **hard-depends on the Supervisor
  Management Proxy** whenever the metric proxy flag is set. `FailedMount`
  on two `metrics-proxy-*` secrets is the tell.
- The dependency heals retroactively: install the proxy, bump the
  PackageInstall annotation, wait.
- Set `serviceDomain` at cluster create. It's immutable, and every add-on
  that builds a service URL will assume it.
- When a package "does nothing", describe the pod, not the package.

*Previously: [Telegraf on Windows Server 2025](/posts/telegraf-windows-2025/).
More in the [Observability on VCF](/series/observability-on-vcf/) series.*

---
*Lab environment; opinions my own.*
