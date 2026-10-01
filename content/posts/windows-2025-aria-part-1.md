---
title: "Windows Server 2025 via Aria Automation, part 1: the pipeline"
date: 2026-09-17T06:10:00+01:00
lastmod: 2026-10-01
draft: false
tags: [aria-automation, vcf-automation, vm-apps, windows, cloudbase-init, vro, powershell]
products: ["VCF Automation"]
series: ["The Windows Build Pipeline"]
seriesPart: 1
tldr:
  - "One catalog request delivers a domain-joined Windows Server 2025 with its agents, a build report and no automation tooling left behind."
  - "Three layers share the work: Aria and vRO hold the credentials, cloudbase-init handles first boot, a file-share build engine does the rest."
  - "The domain join changes the rules mid-build, so everything after it runs as a scheduled task under an explicit identity."
cover:
  image: "/images/post15-hero-winpipe.svg"
  alt: "Three layers: Aria control plane, cloudbase-init first boot, file-share build engine"
  hidden: false
summary: "One catalog request, one fully-built domain-joined Windows Server 2025 with a standard agent stack, a validation report, and no trace of the tooling that built it. The three-layer design — Aria/vRO control plane, cloudbase-init first boot, a pulled build engine — and the reasoning behind each seam."
---

A user fills in a form: environment, size, disks, networks, tags. Some time
later there's a Windows Server 2025 VM with:

- a sequential hostname, allocated from Active Directory (AD);
- static IPs on up to four NICs;
- its data disks laid out and lettered;
- domain membership;
- the standard agent stack, installed and healthy;
- a pixel-perfect HTML build report on a file share.

And there's **none of the automation tooling left on the box**. The build
behaves like the ideal house guest: it makes itself useful, tidies up and
leaves.

This three-part series is how that works. It's a VM Apps build: a classic
Aria Automation cloud template plus vRO (Aria Automation Orchestrator). It's
also a good example of the pattern. The platform does the allocation and
the metadata; the guest does the guest.

Part 1 is the architecture. [Part 2](/posts/windows-2025-aria-part-2/) is the
state machine that survives four reboots. [Part 3](/posts/windows-2025-aria-part-3/)
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

- **Aria/vRO owns what needs platform credentials:** querying AD for the
  next hostname, and reading vCenter for where the VM landed. The guest
  never holds a vCenter or AD-admin credential.
- **cloudbase-init owns what must happen before anything else.** The
  network has to work before the share can be reached. The disk layout has
  to exist before installers land on it. And the domain join changes the
  security context that everything after it runs in. That last one is the
  whole reason the next layer exists (more on that below).
- **The engine is pulled, not embedded.** Installers change and agents get
  new versions, and re-releasing a cloud template for every payload update
  is how automation dies. Update a script on the share, and every build
  after that gets it.

vCenter guest customization is **disabled** ([`customizeGuestOs: false`](https://techdocs.broadcom.com/us/en/vmware-cis/aria/aria-automation/8-18/assembler-on-prem-using-and-managing-master-map-8-18/maphead-designing-your-deployments/initialize-general/initialize-vsphere-static-ips.html)).
One code path owns hostname, networking, disks and join. Two would fight.

## The control plane: two vRO hooks that matter

**Compute Allocation: a sequential hostname.** The template builds a prefix
from the location, classification, environment and application inputs. A
vRO workflow queries AD computer objects with that prefix and allocates
*highest existing suffix + 1*.

Gaps are never reused. With `-001`, `-002`, `-003` and `-005` present, the
next is `-006`. A gap usually means a deleted machine, and deleted machines
can be less gone than we'd like. The old name may still live in DNS, a backup
catalogue or the configuration management database (CMDB). Reusing it is
how you restore the wrong server.

**Compute Post Provision: placement metadata into the guest.** A second
workflow asks vCenter where the VM actually landed: vCenter, datacenter,
cluster, host, folder, datastores, and which portgroup each NIC is on. It
writes all that as JSON into the VM's `extraConfig`, as
`guestinfo.vra.infrastructure`.

Later, inside the guest,
`vmtoolsd.exe --cmd "info-get guestinfo.vra.infrastructure"` reads it back.
That's the bridge that lets the build report say "this VM is on host X,
datastore Y" with **zero vCenter credentials in the guest**.

Three more Post Provision workflows email the backup team, the security
operations centre (SOC) and the requester. (A note for part 3: the
requester's "your deployment has completed" email fires here, before the
in-guest build has even started.)

## First boot: cloudbase-init, four scripts, two reboots

The template's `cloudConfig` is a MIME multipart. It holds one
`cloud-config` part (set the hostname, write the tags to disk) and four
`#ps1_sysnative` scripts, run in order. Three conventions make them safe to
re-run (idempotent):

- **Flag files** under `Flags\`. A script exits straight away if its flag
  exists, so re-runs after a reboot do nothing.
- **Transcripts** under `Logs\`, one per script.
- **Exit 1003** means "reboot me and run this part again on next boot" (the
  flag then short-circuits it). Exit 0 means done. Exit 1 means failure.

| Script | Does | Exit |
|---|---|---|
| `00-config-network` | pairs adapters (by ifIndex) with `to_json(self.networks)` (by deviceIndex); static IP/gateway/DNS per NIC | **1003** — reboot 1 |
| `01-config-disks` | extends C:, onlines/initialises/partitions/formats each extra disk from the request array | 0 |
| `02-join-domain` | runs the join script via a one-shot scheduled task as local admin; verifies `CsDomain ≠ WORKGROUP` | 0 |
| `03-init-puller` | writes `data-payload.json`, encrypts the share secrets, pulls 04/05/06 from the share, launches staging | **1003** — reboot 2 |

That's two reboots before a single agent has been installed. By Windows
standards, it's barely clearing its throat.

The network script carries an assumption worth writing on the wall. It
pairs OS adapters with the request's NICs **by position**. That holds for
freshly cloned VMs where the NICs were added in PCI order. If anyone ever
changes the NIC order after cloning, revisit it.

## Why not just cloudbase-init (or guest customization) all the way down?

The obvious design is the one we started with: let the platform do the
guest. vCenter guest customization sets the hostname and IP and joins the
domain. Then one cloudbase-init userdata installs the agents and patches,
and reports back. No scheduled tasks, no pulled engine, no state machine.

It works on a workgroup machine. It stops working the moment the machine
joins a real domain, and it stops in a way that is easy to misread.

**The domain join changes the rules mid-build.** Everything up to the join
runs as a fresh, local, unmanaged Windows install. That means the local
Administrator, the default execution policy, and no central policy.

At the join, the machine lands in its target organisational unit (OU). On
the next policy refresh, which the reboot guarantees, **Group Policy
applies**. In this environment, the policy for member servers includes the
usual security baseline:

- controls on script execution;
- limits on what may run, from where, and under which accounts;
- hardening of the local administrator context.

None of that is negotiable, and none of it should be. It's the same policy
every production server gets.

**What that does to a first-boot pipeline.** cloudbase-init runs its
plugins as a service, as LocalSystem, running scripts from its own
directory. Before the join, that context can do anything. After the join,
it's exactly the kind of context the baseline is designed to restrict.

So everything that comes *after* the join is in trouble: the installer
pulls, the agent installs, the reboots, the validation. They either fail
outright or, worse, quietly do nothing. cloudbase-init logs the plugin as
executed, the script never ran anything, and the build "completes" with an
unpatched server carrying no agents.

The first few builds looked exactly like that. The log was technically
correct, which is the least useful kind of correct.

**Two ways out, one of them wrong.** You can relax policy for the build: a
staging OU with a weaker baseline, a Group Policy Object (GPO) exemption
for the cloudbase-init path, or a delayed join. But then the server is
built under one set of rules and delivered under another. And the join
becomes a late step that nothing after it exercises.

Or you can accept the policy as the environment it is, and run the
post-join work in a context the policy *permits*.

**The permitted context is a scheduled task under an explicit identity.**
Each task runs as a named account: a domain-joined local admin for the pull
and the join check, and SYSTEM for the build master. It runs at the highest
run level, with `-ExecutionPolicy Bypass` on each call, from a staging path
the policy allows. That's an ordinary, auditable pattern, and the baseline
was written to allow for it.

So cloudbase-init doesn't run the OS commands itself; it hands them to
tasks. Its job shrinks to "get the network up, lay out disks, join, hand
off". The design also picks up three things it now depends on:

- a **per-task execution ceiling** (1 h for the pull, 2 h for the build)
  that contains a hung installer instead of leaving a half-built VM;
- an **at-startup trigger**, which is what makes a multi-reboot state
  machine possible after cloudbase-init has been uninstalled;
- a clean **security story**: the identities that do the work are the
  ones the domain already governs, and they stop existing on the box when
  the build is done.

**Why not Aria's own in-guest mechanisms?** Guest customization only
covers hostname, IP and join. Letting it *and* cloudbase-init own the same
settings means two code paths fighting (hence `customizeGuestOs: false`).

Driving the guest from outside means vRO calling into the VM for two hours.
That needs guest credentials held centrally, and it keeps a management path
open for the whole build. ABX (Aria's action-based extensibility) can't
reach inside the guest at all.

The platform's job is what needs platform credentials: the hostname from
AD and the placement facts from vCenter. The guest does the guest, under
the domain's rules, from the first reboot after the join.

Even if the GPO were relaxed tomorrow, don't simplify the wrappers away.
The ceiling and the startup trigger are worth having on their own.

## The hand-off: `03-init-puller`

This is where the code baked into the template stops, and the centrally
managed engine starts:

1. Create `Flags\ Logs\ Data\ Scripts\` under the log folder.
2. Write **`data-payload.json`**, the one document everything after this
   reads. It holds the share path and accounts, the image, the project,
   deployment and requester, the installer folder and file pairs, the tags
   and the placement facts.
3. **Encrypt the two share passwords** with AES, using a key derived from
   the machine's BIOS UUID. Copied off the box, the payload is useless.
4. Generate a runner, and run it through a one-shot task as local admin.
   It maps the share read-only, copies `04-stage-payloads`,
   `05-build-master` and `06-validate-build` locally, unmaps, and launches
   staging.
5. Write the flag and exit 1003. Reboot 2. cloudbase-init's job is done,
   though nobody has mentioned the uninstall to it yet.

`04-stage-payloads` copies every installer to local disk. Installers never
run across SMB, so they're immune to network blips and file locks
mid-install. It also registers the **`Build-Master` startup task**. From
here on, every boot runs `05-build-master.ps1` until the build is complete.

What the requester actually sees is a short form. Leaving out the
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

Each of those shapes the hostname, lands in `guestinfo`, or is written to
disk for the build engine to read. Nothing is entered twice.

## Why this matters outside the lab

For an organisation, this pipeline turns a Windows server from something a
person builds into something the platform *delivers*. A request goes into a
catalog, and a domain-joined server with its agents comes out. The security
team's controls (naming, join, hardening, monitoring agents) apply every
time, because they're in the pipeline, not in a checklist.

The separation of concerns is what keeps it maintainable. The platform
holds the credentials and the guest does the work. A change to the
software stack is a script update on a share, not a template re-release.

## Rules learned

- Split by **who holds the credential**. The platform queries AD and
  vCenter; the guest never does. `guestinfo` is the one-way bridge.
- **Disable vCenter customization** when cloudbase-init owns the guest.
  One owner.
- **Pull the engine** from a share. Embed only what must run before the
  network exists.
- Flag files, transcripts and exit 1003 make first-boot scripts idempotent
  and reboot-safe.
- Anything after the domain join runs in a **scheduled task under an
  explicit identity**: for policy, for the execution ceiling, and for the
  startup trigger.
- Never reuse hostname gaps.

## Broadcom documentation

- [Cloudbase-Init commands for Windows in Automation Assembler](https://techdocs.broadcom.com/us/en/vmware-cis/aria/aria-automation/8-18/assembler-on-prem-using-and-managing-master-map-8-18/maphead-designing-your-deployments/initialize-general/initialize-windows-general/initialize-cloudbase-init.html): a `cloudConfig` section of Cloudbase-Init commands in the cloud template
- [Windows Automation Assembler image for vSphere](https://techdocs.broadcom.com/us/en/vmware-cis/aria/aria-automation/8-18/assembler-on-prem-using-and-managing-master-map-8-18/maphead-designing-your-deployments/initialize-general/initialize-windows-general/initialize-windows-image-vsphere.html): the Windows template with Cloudbase-Init installed to run as LocalSystem
- [vSphere static IP addresses in Automation Assembler](https://techdocs.broadcom.com/us/en/vmware-cis/aria/aria-automation/8-18/assembler-on-prem-using-and-managing-master-map-8-18/maphead-designing-your-deployments/initialize-general/initialize-vsphere-static-ips.html): why `customizeGuestOs` must be `false` when the `cloudConfig` sets the network
- [Event topics provided with Automation Assembler](https://techdocs.broadcom.com/us/en/vmware-cis/aria/aria-automation/8-18/assembler-on-prem-using-and-managing-master-map-8-18/maphead-designing-your-deployments/maphead-extensibility-in-cloud-assembly/learn-more-about-extensibilty-subscriptions/event-topics-provided-with-cloud-assembly.html): Compute allocation, where resource names can still change, and Compute post provision
- [How do I modify virtual machine properties using a Automation Orchestrator Client workflow subscription](https://techdocs.broadcom.com/us/en/vmware-cis/aria/aria-automation/8-18/assembler-on-prem-using-and-managing-master-map-8-18/maphead-designing-your-deployments/maphead-extensibility-in-cloud-assembly/extensibility-workflow-subscriptions/how-do-i-modify-virtual-machine-properties-using-a-vro-workflow-subscription.html): an Orchestrator workflow subscribed to Compute allocation to set the VM name
- [Query Information using GuestInfo Variable](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/tools/12-5-0/vmware-tools-administration-12-5-0/configuring-vmware-tools-components/using-vmware-tools-configuration-utility/view-virtual-machine-status-information/query-information-using-guestinfo-variable.html): reading `guestinfo` variables from inside the guest with VMware Tools

*Part 2: [the state machine that survives four reboots](/posts/windows-2025-aria-part-2/).*

---
*Lab write-up of a production pattern; customer specifics removed. Opinions
my own.*
