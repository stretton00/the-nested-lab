---
title: "Telegraf on Windows Server 2025: unsupported, works anyway"
date: 2027-05-12
draft: true
tags: [observability, telegraf, windows, vcf-operations, metrics, support-matrix]
series: ["Observability on VCF"]
cover:
  image: "/images/post20-hero-telegraf.svg"
  alt: "The support matrix says no; the metrics say yes"
  hidden: false
summary: "The VCF Operations agent support matrix doesn't list Windows Server 2025. The Telegraf agent installs, runs and reports anyway. What 'unsupported' really means, how to deploy it deliberately, what to watch because of it — and the same Telegraf on VKS, where a hidden proxy dependency bit me."
---

> **DRAFT STATUS:** VKS half and the Ops-side Windows evidence (agent running, product-managed, W2025 object) are captured. Still to do on the box itself: the canary `inputs.exec` and a perf-counter chart. Marked **[CAPTURE]**.

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

**[CAPTURE]** — the section below is the plan; fill in with the live run.

On the [pipeline-built W2025 server](/posts/windows-2025-aria-part-1/),
via Ops: *Environment → Applications → Manage Telegraf Agents → Install*.
The bootstrap uses WinRM or a downloaded installer; the agent registers
against the Ops cloud proxy and appears under the VM object.

Then the two things that make it *yours*:

1. **Record the exact versions** — agent build, Telegraf version, OS build
   — in whatever you use for a CMDB. When the matrix catches up, you want
   to know whether you're on the version they tested.
2. **Add a canary metric.** `inputs.exec` running something trivially
   OS-dependent (`Get-ComputerInfo | select OsBuildNumber`) — if a future
   Windows update changes an API and the input silently breaks, this is
   the series that goes flat first. Alert on absence.

This is the same host that runs the [vLLM metrics
collector](/posts/vllm-metrics-vcf-ops-part-2/) as an `inputs.exec`
plugin, so the agent is already doing custom work; the canary is one more
stanza.

![Manage Telegraf Agents: Test-2025 — Agent Running, Product Managed Agent, 9.1.0.0.3033](/images/ui/o3-ops-manage-telegraf-agents-w2025.jpg)
*The agent list. One Windows Server 2025 VM, agent running, product-managed — and a `Last Operation Status` of "Start Failed" sitting next to a green "Agent Running". That contradiction is the first thing you own on an unsupported OS: the start operation's status check didn't recognise the platform, the service came up anyway.*

![Expanded: Custom Monitoring on the W2025 agent — a Ping Check and a Services check already configured](/images/ui/o4-ops-telegraf-w2025-custom-monitoring.jpg)
*Expand the row and the agent is doing real work: a ping check and a Windows service check, both product-managed plugins, on an OS the matrix doesn't list.*

![The VM object in Ops: Microsoft Windows Server 2025 (64-bit), tools running](/images/ui/o2-ops-w2025-vm-summary.jpg)

![Windows OS on Windows 2025: AgentManagedType = Product Managed, Tags|source = Windows_2025](/images/ui/o1-ops-w2025-agent-metrics.jpg)
*The "Windows OS on Windows 2025" child object the agent created, with `Telegraf Availability` in the metric tree and the `AgentManagedType` property reading Product Managed.*

> **[SHOT]** still wanted: a `win_perf_counters` CPU chart and the canary series once it's configured; the support-matrix page/KB for the "says no" half.

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

> **[SHOT]** `kubectl get pods -n tanzu-system-telegraf` before (FailedMount)
> and after (Running); the CoreDNS rewrite stanza.

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
