---
title: "Windows Server 2025 via Aria Automation, part 2: a state machine that survives four reboots"
date: 2027-03-17
draft: true
tags: [aria-automation, windows, powershell, state-machine, cloudbase-init]
series: ["The Windows Build Pipeline"]
cover:
  image: "/images/post16-hero-statemachine.svg"
  alt: "Boot → check kill switch → skip flagged steps → run next step → reboot if required → repeat"
  hidden: false
summary: "05-build-master.ps1 runs at every startup until the build is done. Flag files make each step run once; a persisted state file keeps true timings across reboots; a kill-switch flag makes a stray run a no-op. Then it cleans up, validates, publishes — and deletes itself."
---

[Part 1](/posts/windows-2025-aria-part-1/) ended with a startup scheduled
task registered and `05-build-master.ps1` staged locally. From this point
the machine will reboot at least twice more — Windows Updates insists, and
the build ends with a clean reboot — and every one of those boots runs the
same script. The script has to *converge* on a finished build no matter how
many times it's invoked.

That's a state machine, and it's built from three very boring mechanisms.

## The three mechanisms

**1. Master kill switch.** If `100_build_complete.flag` exists, exit
immediately. A stray task run after completion does nothing.

**2. Per-step flags.** Every install step writes
`NN_<Step>_installed.flag` on success and is skipped on subsequent runs.

**3. Persisted state.** `data-state.json` holds the provisioning start
time and per-step timings, re-loaded on every boot. So the final report
shows the *true* duration of every step across the whole build, not just
the last boot — and a step re-observed as SKIPPED after a reboot never
overwrites its real recorded duration.

```
every boot:
  if 100_build_complete.flag → exit
  load data-state.json
  for step in $softwarePayload:
      if NN_step_installed.flag → SKIP (keep recorded timing)
      run installer from local Staging (timeout ceiling)
      exit 0 or 3010 → write flag, record timing
      if step.RebootAfter → Restart-Computer; exit      ← next boot resumes here
  cleanup → validate → publish → self-destruct → final reboot
```

## Phase 1: software, declaratively

The stack is a single array — the designed extension point:

```powershell
$softwarePayload = @(
  @{ Name='MonitoringAgent'; Folder=$p.monPath;  File=$p.monInstallFile;  Timeout=20; Reboot=$false;
     Service='HealthService';       Path='...\Monitoring Agent\HealthService.exe' },
  @{ Name='InventoryAgent';  Folder=$p.invPath;  File=$p.invInstallFile;  Timeout=15; Reboot=$false;
     Service='InventoryAgent';      Path='...\Inventory\agent.exe' },
  @{ Name='EndpointSecurity';Folder=$p.epsPath;  File=$p.epsInstallFile;  Timeout=30; Reboot=$false;
     Service='masvc';               Path='...\Agent\masvc.exe' },
  @{ Name='LogAgent';        Folder=$p.logPath;  File=$p.logInstallFile;  Timeout=15; Reboot=$false;
     Service='LogAgentService';     Path='...\Log Agent\liwinsvc.exe' },
  @{ Name='WindowsUpdates';  Folder=$p.updPath;  File=$p.updInstallFile;  Timeout=45; Reboot=$true }
)
```

Adding a product is adding an element. Each installer runs from the local
staging copy with a hung-installer timeout; exit codes 0 and **3010**
(success, reboot required) count as success. When a `Reboot=$true` step
succeeds, the script restarts the machine and exits; on the next boot the
task re-runs it, completed steps skip via their flags, execution resumes at
the next step.

Post-install health isn't "installer said OK" — it's **flag present AND
service running AND install path exists**, with a 120-second wait for
delayed-start services. Windows Updates is flag-only; there's no service
to check.

## Phase 2: cleanup — leave nothing behind

- **Eject the config-drive ISO.** In Session 0 there's no Explorer, so
  the usual shell ejection doesn't work. A P/Invoke to `winmm`'s
  `mciSendString("set cdaudio door open")` does.
- **Restore UAC.** `EnableLUA` and `FilterAdministratorToken` were relaxed
  in the base image so the build could run unattended; re-enable both.
- **Uninstall cloudbase-init.** Stop and delete the service, kill its
  processes, run the uninstaller silently, remove the directory. Guarded
  by `99_cleanup_complete.flag`.

The startup task is deleted *before* validation, so the health check can
truthfully report "no automation task remains".

## Phase 3: collect the evidence

The script assembles `data-validation.json` — the single input to the
report in [part 3](/posts/windows-2025-aria-part-3/):

| Collector | Captures |
|---|---|
| Network | per active adapter: alias, IPv4, prefix, gateway, MAC, DNS |
| Infrastructure | `guestinfo.vra.infrastructure` via `vmtoolsd`, **15 attempts × 10 s** (the vRO subscription can land late) |
| OS / hardware | domain, CPUs, RAM, caption, uptime, time zone, pending reboot, latest hotfix |
| AD / security | local Administrators, secure-channel test, machine OU |
| Disks | per volume: letter, label, size, free |
| Post-build health | WinRM, RDP, UAC enabled, startup task gone, domain DNS resolves, NTP source |
| Software | per app: flag + service + path |
| Installed apps | both uninstall hives (64-bit and WOW6432) |

The verdict is strict: **`GuestStatus = Success` only if every software
item is healthy *and* the machine is domain-joined.** Anything else renders
the report banner red.

## Phases 4 and 5: publish, then self-destruct

Remap the share with the **write** account (5 × 10 s retries — a
different account from the read-only one used for pulls; a compromised
build guest can't tamper with the engine). Render the HTML report locally.
Write `100_build_complete.flag` — kill switch armed. Copy the report plus
`Data\`, `Flags\`, `Logs\` to `\\share\Builds\<image>\<HOSTNAME>\`. Stop the
transcript *before* copying logs so the final log is complete and unlocked.

Then: delete the startup task; overwrite both share passwords in the
on-disk payload with `*** SCRUBBED ***`; delete `Data\` and `Staging\`
(and `Flags\`/`Logs\` if the share copy succeeded); delete the sibling
scripts and itself; remove `Scripts\`; reboot one final time.

The delivered server boots clean, domain-joined, agents running, and
carries **no credentials, payloads or tooling**.

## The reboot sequence of a nominal build

1. After static networking (`00`, exit 1003)
2. After engine pull (`03`, exit 1003) — ends the cloudbase-init phase
3. After Windows Updates (`05`, `Reboot=$true`)
4. Final, after publish and self-destruct

The report's timeline chart finds the update reboot automatically: any gap
over 30 seconds between steps is shaded and labelled REBOOT.

> **[SHOT]** The `Flags\` folder listing at completion + the Gantt from the
> report with the reboot gap shaded (part 3 has the full report shot).

## Why this matters outside the lab

What customers get from a reboot-safe build is predictability: every
server takes the same steps in the same order, survives the reboots
Windows insists on, and finishes clean — with no tooling, no credentials
and no leftover tasks on the delivered machine. That last part matters to
security reviewers as much as the first part matters to operations. And
because every step's timing is recorded, "why did this build take twice as
long?" has an answer instead of a guess.

## Rules learned

- A reboot-safe build is **kill switch + per-step flags + persisted
  timings**. Nothing cleverer is needed.
- Treat exit **3010** as success. Let the *step* declare whether to
  reboot; the loop handles it.
- Health = flag **and** service **and** path. Installer exit codes lie.
- Read platform-injected metadata with **retries** — the injecting
  workflow may land after the guest starts looking.
- Two share accounts: read-only for pulls, write-only for publishing.
- Delete the task before validating, so "no task remains" is checkable.
- Stop the transcript before you copy the logs.
- Scrub, delete yourself, reboot. The customer gets a server, not a
  build environment.

*Part 3: [validation as a product, and the details that hurt](/posts/windows-2025-aria-part-3/).*

---
*Lab write-up of a production pattern; customer specifics removed. Opinions
my own.*
