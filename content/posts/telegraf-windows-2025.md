---
title: "Telegraf on Windows Server 2025: unsupported, works anyway"
date: 2026-09-16T12:20:00+01:00
draft: false
tags: [observability, telegraf, windows, vcf-operations, metrics, support-matrix]
series: ["Observability on VCF"]
cover:
  image: "/images/post20-hero-telegraf.svg"
  alt: "The support matrix says no; the metrics say yes"
  hidden: false
summary: "The VCF Operations agent support matrix doesn't list Windows Server 2025. The Telegraf agent installs, runs and reports anyway. What 'unsupported' really means, how to deploy it deliberately, what to watch because of it — and the same Telegraf on VKS, where a hidden proxy dependency bit me."
---

Two facts, both true:

1. The VCF Operations application-monitoring agent (Telegraf, packaged by
   Broadcom) does not list Windows Server 2025 as a supported OS.
2. It installs, runs, and reports on Windows Server 2025.

This post is about the gap between those, because "unsupported" is a
statement about *who fixes it when it breaks*, not about whether it works
— and there is a right way to run unsupported software in production,
which starts with knowing exactly what you're relying on.

## What "unsupported" means here

The matrix is a promise: Broadcom has tested this combination and will
take a support case on it. Server 2025 wasn't in the test set at release.
Nothing in the agent is OS-version-gated; it's Telegraf with Windows
inputs (`win_perf_counters`, `win_services`, `win_eventlog`) and an output
to Ops. The Windows APIs those inputs use haven't changed in a decade.

So: it works. You just own it.

## Deploying it deliberately

On the [pipeline-built W2025 server](/series/the-windows-build-pipeline/)
the agent went on from VCF Operations itself — *Applications → Manage
Telegraf Agents → Install* — and registered as a **Product Managed Agent**,
version 9.1.0.0.3033. Then the two things that make it *yours*:

**1. Record exactly what you're running.** Agent build, Telegraf version,
OS build — in whatever you use for a CMDB. When the support matrix catches
up you want to know whether you're on the version they tested.

**2. Add a canary.** Something trivially OS-dependent that will go flat
first if a Windows update changes an API under the agent. Ops makes this a
two-minute job with no editing of `telegraf.conf`: *Custom Monitoring →
Custom Script → Add*, pointing at a script that already exists on the box.
Mine reads the build number from the registry and prints it as a
key/value pair:

```powershell
# C:\temp\canary.ps1
$b = (Get-ItemProperty "HKLM:\SOFTWARE\Microsoft\Windows NT\CurrentVersion").CurrentBuildNumber
"osbuild=$b"        # -> osbuild=26100
```

Prefix `powershell -NoProfile -ExecutionPolicy Bypass -File`, five-minute
timeout. (Registry, not `Get-ComputerInfo` — that cmdlet takes 20–30
seconds on Server 2025 and would trip the plugin's own timeout, which is a
very unhelpful way for a canary to die.)

![Manage Telegraf Agents: Test-2025 — Agent Running, Product Managed Agent, 9.1.0.0.3033](/images/ui/o3-ops-manage-telegraf-agents-w2025.jpg)
*The agent list. One Windows Server 2025 VM, agent running, product-managed — and a `Last Operation Status` of "Start Failed" sitting next to a green "Agent Running". That contradiction is the first thing you own on an unsupported OS: the start operation's status check didn't recognise the platform; the service came up anyway.*

![Custom Monitoring on the W2025 agent: Ping Check, Services, and the w2025-canary custom script](/images/ui/o8-ops-telegraf-w2025-canary.jpg)
*Expand the row and the agent is doing real work on an OS the matrix doesn't list: a ping check, a service check, and the canary.*

![The VM object in Ops: Microsoft Windows Server 2025 (64-bit), tools running](/images/ui/o2-ops-w2025-vm-summary.jpg)

![Windows OS on Windows 2025: AgentManagedType = Product Managed, Tags|source = Windows_2025](/images/ui/o1-ops-w2025-agent-metrics.jpg)
*The "Windows OS on Windows 2025" child object the agent created, with `Telegraf Availability` in the metric tree and `AgentManagedType` reading Product Managed.*

## What to watch, *because* it's unsupported

- **Agent upgrades from Ops.** The upgrade path is tested on supported OSes.
  Take a snapshot before pushing an agent upgrade to the W2025 fleet;
  upgrade one first.
- **Windows cumulative updates.** Performance counter names are stable;
  provider GUIDs occasionally aren't. Watch the canary after Patch Tuesday.
- **Service account and WinRM hardening.** W2025 tightens defaults; if the
  install bootstrap fails it's almost always WinRM/TLS, not the agent.
- **Don't file cases on it.** Reproduce on a supported OS first. That's
  the deal you made.

## The same Telegraf on VKS — and its hidden dependency

On VKS the Telegraf package has a dependency that isn't in its README:
with `isMetricProxyConfigured: true` it mounts two secrets
(`metrics-proxy-tls-config`, `metrics-proxy-http-config`) that **only the
Supervisor Management Proxy service propagates** into guest clusters. Without
the proxy installed on the supervisor, every Telegraf pod sits in
`ContainerCreating` / `FailedMount` forever, and nothing says why.

Install the proxy supervisor service, and the chain is retroactive:
`SecretExport` in the guest's `kube-system` → `SecretImport` into
`tanzu-system-telegraf` → pods Running. (The `PackageInstall` needed an
annotation bump to clear a stale `ReconcileFailed` backoff.)

Then the second trap: Telegraf's output URL came out as
`https://supervisor-management-proxy.default.svc.:10093` — domainless and
unresolvable — because the cluster was created without
`clusterNetwork.serviceDomain`. Immutable. A CoreDNS `rewrite` rule
patched the live cluster; every new cluster gets `serviceDomain:
cluster.local` in its spec.


## Why this matters outside the lab

The practical lesson for customers is about **how** to adopt something the
vendor hasn't blessed yet. New operating systems arrive before support
matrices catch up, and "wait" is often not an option. The approach here —
run it, record exactly what you're running, add a canary that detects
breakage early, upgrade one node first — is how an operations team gets
Windows Server 2025 monitored on day one without taking on hidden risk.
The same discipline applies to any unsupported-but-working combination.

## Rules learned

- "Unsupported" = *you* own the fix path. Decide that consciously, record
  versions, add a canary, upgrade one node first.
- The Windows inputs aren't version-gated; W2025 runs the agent fine.
  Alert on metric **absence**, not just thresholds.
- On VKS, Telegraf **hard-depends on the Supervisor Management Proxy**
  when the metric proxy flag is set; `FailedMount` on two secrets is the
  tell.
- Set `serviceDomain` at cluster create. Every add-on that builds a
  service URL will thank you.

*Previously: [fluent-bit two ways](/posts/fluent-bit-two-ways/).*

---
*Lab environment; opinions my own. Support status as observed at time of
writing — check the current matrix.*
