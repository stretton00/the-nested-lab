---
title: "Telegraf on Windows Server 2025: unsupported, works anyway"
date: 2026-09-16T12:20:00+01:00
draft: false
tags: [observability, telegraf, windows, vcf-operations, metrics, support-matrix, wmic]
series: ["Observability on VCF"]
cover:
  image: "/images/post20-hero-telegraf.svg"
  alt: "The support matrix says no; the agent status says Install Success"
  hidden: false
summary: "The VCF Operations agent support matrix doesn't list Windows Server 2025. Add one missing Windows component (WMIC) and the ordinary UI-driven install works: agent running, checks green, metrics flowing. What 'unsupported' really means, the one prerequisite, and what to watch because of it."
---

Two facts, both true:

1. The VCF Operations application-monitoring agent (Telegraf, packaged by
   Broadcom) does not list Windows Server 2025 as a supported OS.
2. It installs from the VCF Operations UI, runs, and reports on Windows
   Server 2025 — once one missing Windows component is put back.

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

## The one prerequisite: put WMIC back

Windows Server 2025 no longer ships the WMI command-line tool, `wmic`.
It's been deprecated for years and is now a Feature on Demand rather
than part of the base install. The agent's install bootstrap still calls
it, so on a stock Server 2025 build the install from Ops does not
complete.

Add the capability first, then install:

```powershell
DISM /Online /Add-Capability /CapabilityName:WMIC~~~~
wmic os get caption   # should now answer
```

(Settings → System → Optional features → Add → "WMIC" does the same thing
through the UI.) That is the whole workaround. Note it in whatever you use
for build standards for Server 2025 — it's a one-line prerequisite for the
agent, and it will keep being one until the bootstrap stops needing it.

## The normal install, from the UI

With WMIC present the install path is exactly the supported-OS one, no
scripts, no manual `telegraf.conf`:

*Operate → Workloads → Applications → Manage Telegraf Agents*, tick the
VM, *Agent Actions → Install*, supply guest credentials, wait. On the
[pipeline-built W2025 server](/series/the-windows-build-pipeline/) it
registered as a **Product Managed Agent**, version 9.1.0.0.3033, with
`Last Operation Status` reading `Install Success`.

![Manage Telegraf Agents: Test-2025 - Agent Running, Product Managed Agent, Install Success, version 9.1.0.0.3033, both collection ticks green, with a Ping Check receiving data under Custom Monitoring](/images/ui/o3-ops-manage-telegraf-agents-w2025.jpg)
*The agent list with the Windows Server 2025 row expanded. Agent Running, product-managed, Install Success, both collection ticks green — and under Custom Monitoring a Ping Check, configured from the same screen and already receiving data, no config file touched.*

![The Windows OS on Windows 2025 object: one object, Normal, no alerts, with Custom Script, Ping Check and Services children and live CPU/memory properties](/images/ui/o9-ops-w2025-windows-os-summary.jpg)
*The object the agent created, as Ops sees it: green, no alerts, CPU and memory properties populated. This is the picture that matters — not the install dialog.*

![Ping Check metrics for the W2025 agent: Availability flat at 100 and Average Response Time in a steady band across a three-hour window](/images/ui/o10-ops-w2025-ping-check-availability.jpg)
*And the proof it's doing work rather than just existing: a Ping Check run from the Server 2025 guest, availability flat at 100 across the morning, response time steady at a couple of milliseconds.*

![The VM object in Ops: Microsoft Windows Server 2025 (64-bit), tools running](/images/ui/o2-ops-w2025-vm-summary.jpg)

![Windows OS on Windows 2025: AgentManagedType = Product Managed, Tags|source = Windows_2025](/images/ui/o1-ops-w2025-agent-metrics.jpg)
*The "Windows OS on Windows 2025" child object, with `Telegraf Availability` in the metric tree and `AgentManagedType` reading Product Managed.*

## Then make it yours

Two small things turn "it happens to work" into something you can run:

**Record exactly what you're running.** Agent build, Telegraf version, OS
build, and the WMIC prerequisite — in whatever you use for a CMDB. When the
support matrix catches up you want to know whether you're on the version
they tested.

**Give it a check that will go flat first.** The Ping Check above is
configured from the agent row in Ops (*Custom Monitoring*); HTTP, TCP and
UDP checks live there too, and a *Custom Script* entry on the same screen
can run anything on the box.
Point one at something trivially OS-dependent and alert on its *absence*:
if a Windows update changes an API under the agent, that line stops before
anything else does.

## What to watch, *because* it's unsupported

- **Agent upgrades from Ops.** The upgrade path is tested on supported OSes.
  Take a snapshot before pushing an agent upgrade to the W2025 fleet;
  upgrade one first.
- **Windows cumulative updates.** Performance counter names are stable;
  provider GUIDs occasionally aren't. Watch your canary check after Patch
  Tuesday.
- **WMIC on new builds.** Any image or pipeline that produces Server 2025
  needs the capability added, or the next install will fail the way the
  first one did.
- **Service account and WinRM hardening.** W2025 tightens defaults; if the
  install bootstrap fails and WMIC is present, it's almost always WinRM/TLS,
  not the agent.
- **Don't file cases on it.** Reproduce on a supported OS first. That's
  the deal you made.

## Why this matters outside the lab

The practical lesson for customers is about **how** to adopt something the
vendor hasn't blessed yet. New operating systems arrive before support
matrices catch up, and "wait" is often not an option. The approach here —
find the real blocker (one missing Windows component, not the agent), use
the standard install path, record exactly what you're running, add a check
that detects breakage early, upgrade one node first — is how an operations
team gets Windows Server 2025 monitored on day one without taking on
hidden risk. The same discipline applies to any unsupported-but-working
combination.

## Rules learned

- "Unsupported" = *you* own the fix path. Decide that consciously, record
  versions, add a canary check, upgrade one node first.
- Server 2025 ships without WMIC; the agent bootstrap needs it. Add the
  capability first and the ordinary UI install works.
- The Windows inputs aren't version-gated; W2025 runs the agent fine.
  Alert on metric **absence**, not just thresholds.
- Configure checks from the agent row in Ops; leave `telegraf.conf` alone
  so upgrades from Ops stay clean.

*Previously: [fluent-bit two ways](/posts/fluent-bit-two-ways/). Next in
the [Observability on VCF](/series/observability-on-vcf/) series: the
same Telegraf on VKS, and the dependency that isn't in its README.*

---
*Lab environment; opinions my own. Support status as observed at time of
writing — check the current matrix.*
