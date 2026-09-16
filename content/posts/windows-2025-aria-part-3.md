---
title: "Windows Server 2025 via Aria Automation, part 3: validation as a product, and the details that hurt"
date: 2027-03-31
draft: true
tags: [aria-automation, windows, powershell, validation, reporting, session-0]
series: ["The Windows Build Pipeline"]
cover:
  image: "/images/post17-hero-report.svg"
  alt: "A build report: scorecard, software cards, network table, provisioning Gantt with a shaded reboot"
  hidden: false
summary: "A self-contained HTML build report — scorecard, per-agent checks, network and storage audits, vCenter placement, an SVG Gantt with reboots detected. Plus the Session-0 traps — vmtoolsd argument mangling, ISO ejection with no Explorer — that cost real hours."
---

Most provisioning pipelines end with "Deployment completed". This one ends
with a document a human can read, and it changed how the platform team and
the server team talk to each other: instead of "it's built, go check it",
the requester gets a page that says *what* was built, *where* it landed,
*what passed*, and *how long each step took*.

[Part 1](/posts/windows-2025-aria-part-1/) was the architecture; [part
2](/posts/windows-2025-aria-part-2/) the state machine. This is the payoff
— and then the details that were nowhere in any documentation.

## The report

`06-validate-build.ps1` is a pure transformation: `data-validation.json`
in, one self-contained HTML file out. No server, no external assets — CSS,
SVG icons and the timeline chart are all inline — so it opens from the file
share or as an email attachment as-is.

> **[SHOT]** The report, anonymised: header + banner + scorecard (top),
> then the Gantt (bottom). This is the hero image for the whole series.

Header: VM, execution time, project, deployment, requester. Banner:
**BUILD SUCCESSFUL / BUILD FAILED** per the strict rule from part 2. A
sticky status bar keeps hostname and verdict visible while scrolling. Then:

| Section | Contents |
|---|---|
| System | hostname, OS, latest patch, CPU, RAM, uptime, time zone, pending reboot |
| Security & AD | domain, trust status, OU, NTP source; WinRM/RDP/UAC status cards; local admins |
| Software | one card per agent: pass/fail badge + the individual checks (flag, service, path) |
| Network | per adapter: alias, MAC, IP, mask (converted from prefix), gateway — **joined to the vSphere portgroup** via the guestinfo NIC/MAC map |
| Storage | per volume: capacity bars (warn < 20 % free, critical < 10 %) + backing datastore chips |
| Tags | every deployment tag as a colour chip (palette chosen deterministically by key hash, so the same tag is always the same colour) |
| Placement | vCenter → datacenter → cluster → host chain, VM folder; "metadata pending" if guestinfo was never readable |
| **Timeline** | SVG Gantt of every step at true wall-clock position; phase colours; **automatic REBOOT detection** (gaps > 30 s shaded and labelled) |
| Installed apps | collapsible full inventory |

The network table is the one that gets the "oh" reaction: the guest knows
its adapters, vCenter knows the portgroups, and the guestinfo bridge from
part 1 lets one table show both, joined on MAC, with no credentials
crossing the boundary.

The Gantt is the one operations teams use. When a build takes 90 minutes
instead of 40, the chart shows whether it was the updates step, a slow
installer, or a 20-minute gap where the machine sat at a boot prompt.

## The details that hurt

Every one of these cost hours and none of them is in a manual.

### vmtoolsd mangles arguments under SYSTEM in Session 0

Reading `guestinfo.vra.infrastructure` via
`& vmtoolsd.exe --cmd "info-get guestinfo.vra.infrastructure"` works
interactively and **fails silently as SYSTEM in a startup task**: the
argument quoting gets mangled on the way through. Fix: build the process
explicitly with `System.Diagnostics.Process`, set `Arguments` as one
string, redirect stdout, and read it yourself. Also: retry — 15 × 10 s —
because the vRO subscription that writes the value can land *after* the
guest starts looking.

### Ejecting an ISO with no Explorer

Session 0 has no shell, so `Shell.Application` ejection does nothing. A
P/Invoke to `winmm.dll`:

```powershell
[mciSend]::mciSendString("set cdaudio door open", $null, 0, [IntPtr]::Zero)
```

opens the tray. It feels like 1998. It works.

### Exit 1003 is the only reboot you should ever request from cloudbase-init

Call `Restart-Computer` from a cloudbase-init script and you race the
plugin's own state tracking. Exit **1003** instead: cloudbase-init reboots,
re-runs the part on next boot, and your flag file short-circuits it.
Installers' **3010** is a different animal — that's "success, reboot
wanted" and the build master decides when.

### cloudbase-init has to remove itself

Leaving cloudbase-init installed on a delivered server is an unattended
execution surface: anyone who can present a config drive owns the box.
The cleanup phase stops the service, kills the processes, runs the
uninstaller silently and deletes the directory — and does it *before*
validation, so the report can confirm it's gone.

### UAC was off. Turn it back on.

The base image relaxes `EnableLUA` and `FilterAdministratorToken` so the
build runs without prompts. If the cleanup forgets to restore them you
ship a server with UAC disabled and a report that says SUCCESS. The
"UAC enabled" card in the security section exists so this can never be
silent.

### Secrets: encrypt to the machine, then scrub

The two share passwords are the only secrets that ever touch guest disk.
They're AES-encrypted with a key derived from the BIOS UUID
(`Win32_ComputerSystemProduct.UUID`) — useless off-box — decrypted only in
memory, and overwritten with `*** SCRUBBED ***` before the final reboot.
That's containment appropriate to a *transient* build secret; it's not a
vault, and shouldn't be described as one.

### The requester is told too early

The "your deployment completed" email fires at Compute Post Provision —
when vCenter has finished, not when the guest has. Users open a server
that's mid-Windows-Updates. Move it to a deployment-completion topic, or at
minimum include the report's future share path.

### Hostname allocation has a race

Read-then-allocate against AD is unsynchronised: two concurrent
deployments can observe the same highest suffix and pick the same name.
Within one multi-machine deployment the count-based batch is safe; across
deployments, wrap the search-and-generate in a vRO `LockingSystem` lock.

## What I'd carry to any build pipeline

Strip the Windows specifics and five ideas survive:

1. **The report is the deliverable.** Build it from a single JSON document
   so it's testable without a build.
2. **Join guest facts to platform facts** via a one-way metadata channel.
3. **Detect reboots from timing gaps**, not from logging "rebooting now".
4. **Health is three checks**, never the installer's exit code.
5. **Clean up before you validate**, so "clean" is a checkable claim.

## Why this matters outside the lab

The report is the part customers remember. It replaces "your server is
ready" with evidence: what was installed and whether it's healthy, where
the server landed in vCenter, how the network was configured, how long each
step took and where the reboots were. Service desks use it to close the
request, security teams use it to confirm the controls, and platform teams
use the timeline to spot regressions. The same idea — validate, then
publish proof — transfers to any provisioning pipeline, Windows or not.

## Rules learned

- Ship a **report**, not a status. Self-contained HTML, one JSON source.
- Under SYSTEM in Session 0: build processes explicitly, eject media via
  `mciSendString`, expect no shell.
- **Exit 1003** for cloudbase-init reboots; **3010** is the installer's
  word for "later".
- Remove cloudbase-init and restore UAC — and make both *checks* in the
  report.
- Machine-keyed encryption + scrub is right for transient secrets. Say
  what it is.
- Fix the two timing bugs: the early requester email, and the hostname
  race under parallel deployments.

*Previously: [the state machine](/posts/windows-2025-aria-part-2/). This VM
is also where the [Telegraf](/posts/telegraf-windows-2025/) and
[fluent-bit](/posts/fluent-bit-two-ways/) Windows agents land.*

---
*Lab write-up of a production pattern; customer specifics removed. Opinions
my own.*
