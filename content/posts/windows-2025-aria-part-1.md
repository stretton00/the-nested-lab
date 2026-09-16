---
title: "Windows Server 2025 via Aria Automation, part 1: the pipeline"
date: 2026-09-17T06:10:00+01:00
draft: false
tags: [aria-automation, vcf-automation, vm-apps, windows, cloudbase-init, vro, powershell]
series: ["The Windows Build Pipeline"]
cover:
  image: "/images/post15-hero-winpipe.svg"
  alt: "Three layers: Aria control plane, cloudbase-init first boot, file-share build engine"
  hidden: false
summary: "One catalog request, one fully-built domain-joined Windows Server 2025 with a standard agent stack, a validation report, and no trace of the tooling that built it. The three-layer design — Aria/vRO control plane, cloudbase-init first boot, a pulled build engine — and the reasoning behind each seam."
---

A user fills in a form: environment, size, disks, networks, tags. Some time
later there's a Windows Server 2025 VM that has a sequential hostname
allocated from Active Directory, static IPs on up to four NICs, its data
disks laid out and lettered, domain membership, the standard agent stack
installed and healthy, a pixel-perfect HTML build report on a file share —
and **none of the automation tooling left on the box**.

This three-part series is how that works. It's a VM Apps build (classic
Aria Automation cloud template plus vRO), and it's a good example of the
pattern: the platform does the allocation and the metadata; the guest does
the guest. Part 1 is the architecture. [Part 2](/posts/windows-2025-aria-part-2/)
is the state machine that survives four reboots. [Part 3](/posts/windows-2025-aria-part-3/)
is the validation report and the details that hurt.

> Customer-specific names, products and policies are generalised throughout.
> The patterns are the point.

## Three layers, three reasons

```
┌──────────────────────────────────────────────────────────────────────┐
│ 1. Aria Automation + Orchestrator         (control plane)            │
│    cloud template · Event Broker → vRO at Allocation / Post-Provision │
│    hostname from AD · placement metadata → guestinfo · notifications  │
├──────────────────────────────────────────────────────────────────────┤
│ 2. cloudbase-init                          (first boot, template-owned)│
│    multipart userdata: network · disks · domain join · pull engine    │
├──────────────────────────────────────────────────────────────────────┤
│ 3. File-share build engine                 (guest state machine)      │
│    stage payloads · install across reboots · validate · report · self-│
│    destruct                                                           │
└──────────────────────────────────────────────────────────────────────┘
```

Each seam exists for a reason you can state in one sentence:

- **Aria/vRO owns what needs platform credentials** — querying AD for the
  next hostname, reading vCenter for where the VM landed. The guest never
  holds a vCenter or AD-admin credential.
- **cloudbase-init owns what must happen before anything else** — the
  network has to work before the share can be reached; the disk layout
  has to exist before installers land on it; the domain join changes the
  security context everything after it runs in.
- **The engine is pulled, not embedded** — because installers change,
  agents get new versions, and re-releasing a cloud template for every
  payload update is how automation dies. Update a script on the share;
  every subsequent build gets it.

vCenter guest customization is **disabled** (`customizeGuestOs: false`).
One code path owns hostname, networking, disks and join; two would fight.

## The control plane: two vRO hooks that matter

**Compute Allocation → sequential hostname.** The template composes a
prefix from location/classification/environment/application inputs. A vRO
workflow queries AD computer objects with that prefix and allocates
*highest existing suffix + 1*. Gaps are never reused: with `-001`, `-002`,
`-003` and `-005` present, the next is `-006`. A gap usually means a deleted
machine whose name may still live in DNS, a backup catalogue or the CMDB;
reusing it is how you restore the wrong server.

**Compute Post Provision → placement metadata into the guest.** A second
workflow asks vCenter where the VM actually landed — vCenter, datacenter,
cluster, host, folder, datastores, NIC→portgroup map — and writes it as
JSON into the VM's `extraConfig` as `guestinfo.vra.infrastructure`. Later,
inside the guest, `vmtoolsd.exe --cmd "info-get guestinfo.vra.infrastructure"`
reads it back. That's the bridge that lets the build report say "this VM is
on host X, datastore Y" with **zero vCenter credentials in the guest**.

Three more Post Provision workflows email the backup team, the SOC and the
requester. (One observation for part 3: the requester's "your deployment
has completed" fires here — before the in-guest build has even started.)

## First boot: cloudbase-init, four scripts, two reboots

The template's `cloudConfig` is a MIME multipart: one `cloud-config` part
(hostname + write the tags to disk) and four `#ps1_sysnative` scripts,
executed in order. Three conventions make them idempotent:

- **Flag files** under `Flags\` — a script exits immediately if its flag
  exists, so re-runs after a reboot are no-ops.
- **Transcripts** under `Logs\`, one per script.
- **Exit 1003** = "reboot me and run this part again on next boot" (the
  flag then short-circuits it). Exit 0 = done. Exit 1 = failure.

| Script | Does | Exit |
|---|---|---|
| `00-config-network` | pairs adapters (by ifIndex) with `to_json(self.networks)` (by deviceIndex); static IP/gateway/DNS per NIC | **1003** — reboot 1 |
| `01-config-disks` | extends C:, onlines/initialises/partitions/formats each extra disk from the request array | 0 |
| `02-join-domain` | runs the join script via a one-shot scheduled task as local admin; verifies `CsDomain ≠ WORKGROUP` | 0 |
| `03-init-puller` | writes `data-payload.json`, encrypts the share secrets, pulls 04/05/06 from the share, launches staging | **1003** — reboot 2 |

The network script is the one with an assumption worth writing on the
wall: it pairs OS adapters with the request's NICs **positionally**, which
is valid for freshly cloned VMs where NICs were added in PCI order. If
anyone ever customises NIC order post-clone, revisit it.

## Why everything runs in a scheduled task

The recurring oddity in this design: OS commands aren't run *by*
cloudbase-init, they're delegated to **Windows Scheduled Tasks under an
explicit identity** — local admin for the join and the pull, SYSTEM for the
build master. That's not incidental complexity. Once the machine joins the
domain, Group Policy applies, and in this environment it blocks script
execution in the context cloudbase-init runs in natively. Anything at or
after the join boundary can't rely on that context surviving.

A task under a named identity at highest run level, with
`-ExecutionPolicy Bypass` per invocation, runs in a context policy
permits. It also brings two things the design *depends on*: a per-task
execution ceiling (1 h pull, 2 h build) that contains hung runs, and —
critically — an **at-startup trigger**, which is what makes a multi-reboot
state machine possible after cloudbase-init has been uninstalled. Even if
the GPO were relaxed, don't simplify the wrappers away.

## The hand-off: `03-init-puller`

This is where template-embedded code stops and the centrally managed
engine starts:

1. Create `Flags\ Logs\ Data\ Scripts\` under the log folder.
2. Write **`data-payload.json`** — the one document everything after this
   reads: share path and accounts, image, project/deployment/requester,
   the installer folder/file pairs, the tags, the placement facts.
3. **Encrypt the two share passwords** with AES, key derived from the
   machine's BIOS UUID. The payload is useless copied off-box.
4. Generate a runner, execute it via a one-shot task as local admin: map
   the share read-only, copy `04-stage-payloads`, `05-build-master`,
   `06-validate-build` locally, unmap, launch staging.
5. Write the flag, exit 1003. Reboot 2. cloudbase-init's job is done.

`04-stage-payloads` copies every installer to local disk (installers never
run across SMB — immune to network blips and file locks mid-install) and
registers the **`Build-Master` startup task**. From here on, every boot
runs `05-build-master.ps1` until the build is complete.

What the requester actually sees is a short form. Stripped of the
site-specific enum values, the inputs are:

```yaml
inputs:
  location:        # site code -> hostname prefix
  classification:  # security zone -> hostname prefix, OU
  environment:     # prod / pre-prod / test -> hostname prefix, tags
  application:     # application code -> hostname prefix, folder
  image:           # Windows2025 (the template is image-versioned)
  flavor:          # Small / Medium / Large -> vCPU + RAM
  count:           # number of identical machines
  bootDiskSizeGB:  # C: (extended in-guest by 01-config-disks)
  primaryNetwork:  # required
  network2..4:     # optional; each becomes a static NIC
  additionalDisks: # [{number, name, letter, sizeGB}] -> D:, L:, ...
  tags:            # free-form key/value -> written to disk, shown in the report
```

Every one of those either shapes the hostname, lands in `guestinfo`, or
is written to disk for the build engine to read. Nothing is entered twice.

## Why this matters outside the lab

For an organisation, this pipeline turns a Windows server from something a
person builds into something the platform *delivers*: a request in a
catalog, a domain-joined and agent-loaded server out, with the security
team's controls (naming, join, hardening, monitoring agents) applied every
time because they're in the pipeline, not in a checklist. The separation of
concerns is what makes it maintainable — the platform holds the
credentials, the guest does the work, and a change to the software stack
is a script update on a share rather than a template re-release.

## Rules learned

- Split by **who holds the credential**: platform queries AD/vCenter,
  guest never does. `guestinfo` is the one-way bridge.
- **Disable vCenter customization** when cloudbase-init owns the guest.
  One owner.
- **Pull the engine** from a share; embed only what must run before the
  network exists.
- Flag files + transcripts + exit 1003 = idempotent, reboot-safe
  first-boot scripts.
- Anything after the domain join runs in a **scheduled task under an
  explicit identity** — for policy, for the execution ceiling, and for the
  startup trigger.
- Never reuse hostname gaps.

*Part 2: [the state machine that survives four reboots](/posts/windows-2025-aria-part-2/).*

---
*Lab write-up of a production pattern; customer specifics removed. Opinions
my own.*
