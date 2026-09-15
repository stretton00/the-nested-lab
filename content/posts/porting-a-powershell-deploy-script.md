---
title: "Porting a PowerShell deploy script to a catalog item: the mapping table is the post"
date: 2027-03-16
draft: false
tags: [vcf-automation, vm-apps, vro, powershell, powercli, ovftool, nested-esxi, refactoring]
series: ["The Lab Factory"]
cover:
  image: "/images/post22-hero-porting.svg"
  alt: "Left: an interactive script's menu prompts. Right: where each one went — inputs, actions, template expressions, subscriptions."
  hidden: false
summary: "esxihostdeploy.ps1 was 400 lines of ovftool and PowerCLI behind a menu. It became a cloud template, two vRO actions and two subscriptions — and the interesting part is deciding where each behaviour belongs. The full mapping, four non-obvious decisions, and the 'yes' that isn't 'true'."
---

Every lab has one: the script that builds the nested hosts. Ours was
`esxihostdeploy.ps1` — ovftool plus PowerCLI, an interactive menu for
environment, ESX version, role, size, host count, then a loop of
`ovftool --prop:guestinfo.*`, `Set-VM`, `New-NetworkAdapter`, `Set-HardDisk`.
It worked for years. It also prompted for credentials, lived on one
machine, and knew nothing about the bringup that came after.

Porting it to a VCF Automation catalog item (VM Apps — a cloud template
plus vRO) is not a rewrite. It's a **sorting exercise**: every behaviour in
the script has a natural home in the declarative model, and the skill is
finding it. Here's the whole table, then the four rows that took thought.

## The mapping

| Script behaviour | Where it lives now |
|---|---|
| Environment menu (f01–f10) | `environment` input (enum) |
| Version menu → OVA path on a share | `esxVersion` input → **image mapping** → content library item |
| Role menu (management / workload / both) | `role` input; "both" = two requests |
| Size menu / auto-detect from an existing host | `size` input (auto-detect dropped — see below) |
| vCenter + ESXi credential prompts | vCenter creds gone (cloud account); `esxiRootPassword` an encrypted input |
| Next-free `esxNN` index scan (gap-filling) | vRO **action** `getNextEsxHostIndexes`, bound to the request form |
| VLAN / IP / gateway arithmetic | **template expressions** (same formulas) |
| `ovftool --prop:guestinfo.*` | `ovfProperties` on `Cloud.vSphere.Machine` |
| Folder lookup / `New-Folder` | **allocation-phase subscription** creates the folder if missing |
| `Set-VM` cpu / mem | `cpuCount` / `totalMemoryMB` in the template |
| 2× `New-NetworkAdapter` (Vmxnet3) | `networks` array, `deviceIndex` 0/1/2 |
| 3× `Set-HardDisk` grow | **post-provision subscription** |
| `NestedHVEnabled = $true` | post-provision subscription |
| "Power on after?" prompt | `powerOn` input, honoured post-provision |
| Summary table printed at the end | the deployment view in the UI |

Five homes, in decreasing order of preference: **input**, **template
expression**, **platform abstraction** (image mapping, network profile,
cloud account), **form action** (read-only lookup at request time),
**subscription** (imperative work at a lifecycle stage). Push each
behaviour as far up that list as it will go.

## The four decisions that weren't obvious

### 1. Drop auto-detect; the platform already remembers

The script inspected an existing host to infer size. That was a workaround
for having no record. The catalog *is* the record — deployment history
shows what size every existing host was requested at — so the input
simply asks. Fewer moving parts, and the requester sees the choice.

### 2. The index scan is a form action, not a workflow step

"Next free `esx07`" has to be known *at request time* so the requester
sees the names they'll get. That's a **vRO action bound to the custom
form** (`getNextEsxHostIndexes(environment, role, count)` → array of
strings), not a step inside provisioning. Forms can call actions; use it
for anything that's a lookup.

### 3. Rename and folder go in *Compute Allocation*, hardware goes in *Post Provision*

Two blocking subscriptions, filtered by a custom property on the template:

| | Subscription 1 | Subscription 2 |
|---|---|---|
| Topic | Compute allocation | Compute post provision |
| Runnable | "Set VM Name & Folder" | "Finalize Hardware" |
| Does | sets `resourceNames`, creates folder | grows 3 disks, `NestedHVEnabled`, power on |
| Timeout | 10 min | 30 min |

The rename *must* be at allocation — it's the only stage where a workflow
output named `resourceNames` is applied to the machine. Disk growth and
nested-HV need a VM that exists, so they wait for post-provision. Both
are blocking: the deployment doesn't proceed until they return.

### 4. `nestedEsx: 'yes'` — not `true`

The subscription condition is
`event.data.customProperties.nestedEsx == "yes"`. Why not `"true"`?
Because boolean-looking strings can arrive in the event payload as typed
booleans, and `true == "true"` is false in the condition evaluator *and*
in the vRO code. It fails silently — the subscription just never fires.
`yes` can't be coerced. Small thing; two hours.

## What stayed exactly the same

The formulas. `10.(20+X).<sub>.0/24`, VLAN `2X0n`, gateway `.254` — they
were string concatenation in PowerShell and they're template expressions
now, character for character. The `guestinfo.*` property names — identical,
because the OVA didn't change. Porting a script well means most of it
survives; only the *plumbing* moves.

## The bits that still bite

- **Network profile without IP ranges.** Addressing is injected via
  `guestinfo`, not the platform's IPAM. Tag the trunk portgroup, add no
  ranges, or IPAM and guestinfo will disagree.
- **Two template revisions in the repo.** v1 is what the guide documents;
  v2 grew later. Both kept deliberately, both labelled. Check which one
  the org has *imported* before editing either.
- **Content-source lag.** A new or changed vRO action needs ~15–20 minutes
  of data collection before the form sees it. Publish, wait, then test.
- **Small disks and OSDATA.** Nested hosts with 64 GB disks ship
  ESX-OSDATA at essentially the whole disk. Templates now provision 128 GB;
  a relocate-scratch script mitigates existing hosts.

![The Nested ESX request form: environment, version, role, size, count — and Host Indexes already computed by the form action](/images/ui/f6-f00-nested-esx-form.jpg)
*Every menu prompt from the script is now a field; `Host Indexes` is the form action's answer to "next free esxNN".*

## Rules learned

- Porting is **sorting**: input → expression → platform abstraction →
  form action → subscription. Push each behaviour as far up as it goes.
- Lookups the requester needs to *see* are **form actions**.
- Rename at **allocation** (`resourceNames` output); hardware at
  **post-provision**. Both blocking.
- Filter subscriptions on a custom property, and make its value a word
  that can't be coerced to a boolean.
- Drop workarounds for missing state; the catalog is the state.
- Keep the formulas. Move the plumbing.

*Part of [The Lab Factory](/series/the-lab-factory/). Next: [driving the
VCF Installer API from vRO](/series/the-lab-factory/).*

---
*Lab environment; opinions my own.*
