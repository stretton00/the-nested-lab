---
title: "Inside the blueprint: generated from one file, built by the lab itself"
date: 2026-11-25
draft: false
tags: [vcf, vcf-automation, blueprints, cci, nested-esxi, automation, homelab]
products: ["VCF Automation"]
series: ["Nested Labs as Code"]
seriesPart: 5
tldr:
  - "Our Phase 5 blueprint is 1,232 lines of YAML with 25 resources and 11 form fields, and nobody typed any of it."
  - "From Phase 3, the lab keeps building after VCF Automation reports success, in stages that leave marker files and can run again."
  - "Code pays off when labs repeat, change version or move: every change is a reviewable diff, validated before release."
tested: "VCF 9.1"
cover:
  image: "/images/post38-hero-blueprint.svg"
  alt: "The generator turns the site file into eight blueprints; one phase is 25 resources (a namespace, four subnets, three binding maps, six VMs, eight disks and a load balancer); the jump host then builds the rest from scripts on the binaries server, and every release goes through validate, version and release"
  hidden: false
summary: "Our Phase 5 blueprint is 1,232 lines of YAML that nobody typed. What a phase is made of, what the requester decides, how the lab builds itself, and the pipeline that releases it like code."
---

The Phase 5 blueprint in our lab catalog is 1,232 lines of YAML. It creates 25
objects, asks 11 questions and makes 246 references to two property groups.
And nobody typed any of it: `gen_lab_blueprint.py ops` writes it from a site
file.

Two hours after the last release, I regenerated all eight catalog items from
the same file. Each came out identical to the copy VCF Automation was serving,
which is more than I can say for anything I've ever typed twice.

[Post 1](/posts/nested-labs-as-code/) set out why we build labs from code
instead of capturing a hand-built one. This is the view from inside.

## One site file, eight blueprints

The generator has a mode per catalog item. `builddc`, `build`, `ready`,
`vcenter`, `ops` and `full` are Phases 1 to 6. `jump` and `dc` are two dev
items without nested hosts.

A ninth mode, `propgroups`, writes the two
[property groups](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html)
the blueprints read. `nestedLabSite` holds the platform, the sizes and the lab
network plan. `nestedLabMedia` holds the software releases.

Each phase has everything the one before it has. So the modes share one
skeleton, and differ in a few switches:

- blank or pre-built hosts;
- a plain or promoted `dc01`;
- what the jump host builds next;
- which fields the form shows.

[Post 4](/posts/six-phases-one-catalog/) covers what each phase gives a student
and a trainer.

## Twenty-five resources

Every phase blueprint has the same inventory of
[Supervisor resources](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html):

| Resource | Kind | Count | Sized by |
|---|---|---|---|
| `namespace` | CCI.Supervisor.Namespace | 1 | limits computed from the request |
| `sn-trunk`, `sn-mgmt`, `sn-vmotion`, `sn-vsan` | Subnet, Private | 4 | 32 addresses each |
| `bm-mgmt`, `bm-vmotion`, `bm-vsan` | SubnetConnectionBindingMap | 3 | VLAN 1610, 1611, 1612 |
| `esx01` to `esx04`, `dc01`, `jump` | VirtualMachine | 6 | host size Small, Medium or Large; jump host Medium or Large |
| `esx01-cap0` to `esx04-cap1` | PersistentVolumeClaim | 8 | 50 GiB each by default, 16 to 400 |
| `dc-bootstrap`, `jump-bootstrap` | Secret | 2 | the Windows VMs' cloud-config |
| `jump-access` | VirtualMachineService, LoadBalancer | 1 | RDP on 3389 |

The dev items are the same skeleton without the hosts: 11 resources for
`jump`, 13 for `dc`. The namespace's limits follow the request. Here are
Phase 5's:

```yaml
  namespace:
    type: CCI.Supervisor.Namespace
    properties:
      generateName: ${'ns-' + input.labName + '-'}
      className: ${propgroup.nestedLabSite.namespaceClass}
      regionName: ${propgroup.nestedLabSite.region}
      vpcName: ${'vpc-' + input.labName}
      storageClasses:
        - name: ${propgroup.nestedLabSite.storagePolicy}
          limit: "${4 * (propgroup.nestedLabMedia.releases[input.release].esxApplianceBaseGi + 2 * input.capacityDiskGi) + 550 + 'Gi'}"
      zones:
        - name: ${propgroup.nestedLabSite.vsphereZone}
          cpuLimit: "${(4 * propgroup.nestedLabSite.hostSizes[input.hostSize].cpu + propgroup.nestedLabSite.jumpSizes.large.cpu + propgroup.nestedLabSite.dc.cpu) * 2000 + 'M'}"
          cpuReservation: 0M
          memoryLimit: "${4 * propgroup.nestedLabSite.hostSizes[input.hostSize].memMi + propgroup.nestedLabSite.jumpSizes[input.jumpSize].memMi + propgroup.nestedLabSite.dc.memMi + 'Mi'}"
          memoryReservation: 0Mi
```

At the defaults, that's 1126 GiB of storage. In Phases 1 and 2 it's 1206 GiB,
because a blank host counts a 64 GiB boot disk instead of the appliance's 44.
These are caps, not use, which is just as well: a finished Phase 6 lab took
about 160 to 180 GiB of vSAN on our platform.

The binding maps put the three lab networks on the trunk as VLANs.
[Post 3](/posts/lab-network-no-router/) shows them, and explains why that
replaces a router. Tom Fojta found that VCF Automation 9.1.0's namespace
capture leaves binding maps out, so a captured blueprint gets them added by
hand. Here they're generated with everything else, each VLAN read from the
property group, so they can't be forgotten.

## What the requester decides

The form asks only what differs between labs: the lab, the host size, the
vCenter and VCF Operations appliance sizes, four passwords, the release, the
jump host size and the vSAN disk size. Phase 5 has 11 fields; Phase 1 has
seven.

Each password field carries a `pattern` with the product's own rule, and VCF
Automation checks it on encrypted inputs too. So a password vCenter would
refuse an hour into the build is refused at submit instead. That's a far
better moment to find out.

A release is a named set, such as `vcf-9.1.0`. Every image and binaries
folder is looked up as `propgroup.nestedLabMedia.releases[input.release].<key>`.
A custom form puts the rarely changed settings on a second tab.

Everything else is read at request time: region, zone, namespace class,
storage, VM classes, the Windows image, every lab address, the DNS forwarders
and the binaries server. The generator refuses to write any of those into a
blueprint. That's why the same eight blueprints work on another platform.

Phases 1 and 2 are shared by students and trainers, and the server decides
whose lab it is. The rule is written once, in the generator:

```python
WHO = "replace(to_lower(split(env.requestedBy, '@')[0]), '.', '-')"      # the requesting user, as a DNS label
...
TRAINER = "contains(%s, %s)" % (S("trainers"), WHO)
LAB_ID = {"requester": WHO,
          "shared": "((%s && input.labName != 'mine') ? input.labName :%s)" % (TRAINER, WHO)}.get(VPC_BINDING, "input.labName")
```

A student's lab always lands in their own VPC. A user on the `trainers` list
in `nestedLabSite` may pick any student's. The Phase 1 blueprint uses that
expression 13 times, from the namespace and the VPC to every VM name and both
config files. Adding a trainer is a property-group change, not a new version.

## The lab builds itself

VCF Automation reports success once the six VMs are powered on. From Phase 3
on, the lab keeps building, for hours in Phases 4 to 6. Nobody signs in to
start anything, which is exactly the amount of effort I like to put in.

![Five stages from request to ready lab, each ending in a marker file, with the binaries server supplying scripts and appliance files](/images/inside-the-lab-blueprint-diagram.svg)

The Windows VMs boot with cloudbase-init, which reads the same cloud-config as
cloud-init on Linux. The blueprint writes a `lab-config.json` onto each one,
with the lab's resolved values and the request's passwords. It adds the few
scripts needed before anything can be downloaded. These are the jump host's
last commands in Phases 4 to 6:

```yaml
              - powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\lab\Install-PowerCLI.ps1
              - powershell -NoProfile -ExecutionPolicy Bypass -Command "& C:\ProgramData\lab\Get-LabFile.ps1 -Url '${propgroup.nestedLabSite.scriptsUrl}Build-Lab-vCenter.ps1' -OutFile 'C:\ProgramData\lab\Build-Lab-vCenter.ps1' -TimeoutSec 120"
              - powershell ... $p = New-ScheduledTaskPrincipal -UserId SYSTEM -RunLevel Highest; $s = New-ScheduledTaskSettingsSet -ExecutionTimeLimit (New-TimeSpan -Hours 12) -StartWhenAvailable; Register-ScheduledTask -TaskName LabVCenterBuild ...
              - powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\lab\Join-LabDomain.ps1 -Phase 1
```

The last one joins the domain. Once `dc01` answers for the vCenter's name,
the jump host starts `LabVCenterBuild`. The later scripts come from the
binaries server as the lab reaches them, so a fix there reaches the next lab
without a new blueprint version.

Three habits keep it reliable:

- Every download gets five attempts, with 60 seconds for the response
  headers, and every attempt is logged.
- Every connection to a nested host gets six tries, 20 seconds apart.
- Every step checks for its own result first, so starting the task again
  carries on where it stopped.

A fourth habit arrived on 1 October. A lab sat perfectly still for 70
minutes, partway through importing its vCenter's disks. DRS had live-migrated
two of its nested hosts mid-import, and the SSH session watching the import
never noticed that its connection had died. It just kept waiting. The build's
two-hour watchdog couldn't step in either, because it runs in the same loop
and was waiting too.

The fix was two SSH options for keep-alives, so a dead session now ends within
a minute and the next check opens a fresh one. It went onto the binaries
server that evening, so the next lab picks it up without a new blueprint
version.

Each stage ends in a marker file, or in a `-FAILED.txt` on the desktop with
the reason and the command to run it again. Here's the end of the vCenter
stage in a Phase 6 rehearsal lab, and the jump host's desktop at that moment:

```text
13:04:32    NFS datastore binaries mounted on esx03.acme.lab
13:04:33    NFS datastore binaries mounted on esx04.acme.lab
13:04:33  === lab vCenter build complete: https://172.30.0.50/ui (administrator@vsphere.local) ===
13:04:34  running Checkpoint-vCenter-AD.ps1 - progress in checkpoint-vcenter-ad.log
13:05:23  AD integration finished (VCENTER-AD-READY.txt written)
13:05:23  handing over to Build-Lab-Ops.ps1 - progress in ops-build.log

Name                 LastWriteTime
----                 -------------
AD-DETAILS.txt       30/09/2026 11:21:13
LAB-README.txt       30/09/2026 11:11:51
VCENTER-AD-READY.txt 30/09/2026 13:05:23
VCENTER-READY.txt    30/09/2026 13:04:33
```

`OPS-READY.txt` followed an hour and a half later.
[Post 4](/posts/six-phases-one-catalog/) shows how trainers read these markers
from every lab at once.

## Linked clones and the right guest type

Two settings came from Tom Fojta's post
[Building Nested Labs in VCF Automation 9.1](https://fojta.wordpress.com/2026/05/12/building-nested-labs-in-vcf-automation-9-1/),
and both paid off at once.

The first is `promoteDisksMode: Disabled` on the Windows VMs. VM Service
creates a VM as a linked clone of its image cache. By default, it then
promotes the disks to full ones after power-on. For our ~25 GiB Windows
image, that's more than 10 minutes per VM, with guest operations refused in
the meantime.

With promotion off, the trial lab went from request to joined domain in 15.1
minutes instead of 17.6. Guest operations were available about 9 minutes
sooner, and there was no ~25 GiB copy per VM:

```text
jump-student01 Hard disk 1 90 GiB | parent: 410d3f0d1754eaaf4.vmdk
...
dc01-student01 Hard disk 1 90 GiB | parent: 410d3f0d1754eaaf4.vmdk
...
promoteDisks tasks for student01 in the last 20 min: 0
```

The price is a dependency on the image cache, which is easy to accept for a
lab. The nested hosts keep the default, because a blank host grows its boot
disk.

The second is the guest type. The blank-host image is hardware version 22 and
declares `vmkernel9Guest`, ESXi 9's own type. The appliance is hardware
version 20, which stops at `vmkernel8Guest`. Here are the field and both
images, as the Supervisor sees them:

```text
FIELD: promoteDisksMode <string>
ENUM:
    Online
    Offline
    Disabled
...
    - Disabled -- Do not promote disks.
...
    Defaults to Online.
...
Nested_ESXi9.1.0.0_Appliance_Template_v1.0 osType=vmkernel8Guest hw=20 fw=efi
blank_vm_esx_attached osType=vmkernel9Guest hw=22 fw=efi
```

Neither needed a new capture. The promote mode is a value in `nestedLabSite`,
and each guest type is a key of its release in `nestedLabMedia`.

## Validate, version, release

A change reaches the catalog through `release_v2.py <version>`. It regenerates
each blueprint, keeps a copy, and hands each one to `release_bp.py` for its
project. That script updates the content, waits for VCF Automation's
`ContentValid` verdict, and stops if the verdict is false.

With `VALIDATE_ONLY=1` it stops there anyway. That's how we checked a
blueprint in the students' project without touching its catalog:

```text
PUT blueprint: 200 OK
ContentValid: True
VALIDATE_ONLY: content is valid in lab-students - no version created, nothing released
```

Otherwise it creates the
[version](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html)
and withdraws the published one, because VCF Automation publishes one version
per item. Then it releases the new one.

A content update clears the blueprint's link to its custom form, and each
version takes its own copy of the form. So the script restores the link
first, and reports which form the version got. Here's version 2.1.10, on
30 September:

```text
...
== lab-phase-2-blank-hosts (lab-students, shared) -> blueprint-nested-esxi-lab-build.yaml 2.1.10, 94348 bytes
   version 2.1.10 request form: custom (bfec6644-126b-4f89-bf95-40f7e159ce87)
   un-release 2.1.9: 200
   release 2.1.10: 200
   versions now: [('2.1.10', True), ('2.1.9', False), ('2.1.8', False), ...]
...
== lab-phase-4-vcenter (default-project, labname) -> blueprint-nested-esxi-lab-vcenter.yaml 2.1.10, 88414 bytes
   version 2.1.10 request form: custom (e5f56632-8413-410a-879b-621e13e1f006)
   un-release 2.1.9: 200
   release 2.1.10: 200
...
== nested-esxi-lab-jump (default-project, labname) -> blueprint-nested-esxi-lab-jump.yaml 2.1.10, 49780 bytes
   version 2.1.10 request form: VCF Automation's generated form
   un-release 2.1.9: 200
   release 2.1.10: 200
...
exit 0
```

The one-version rule is one of
[seven CCI blueprint gotchas](/posts/cci-blueprint-gotchas/), and
[validateOnly everywhere](/posts/validateonly-everywhere/) argues for a dry run
in front of every change.

## Why code

Capturing a hand-built lab needs no generator, and it keeps any state built
by hand. For a one-off, that's hard to beat. Code pays off when labs repeat,
change version or move.

Every change is a reviewable diff. The code is testable, too. The generator
refuses a site value in a blueprint. It also refuses a Phase 6 site file
without the accounts the Active Directory steps use by name. It caught exactly
that in an earlier version of our own example file, which I mention purely in
the interest of honesty. And a draft request proves a change before release.

It's reproducible, as the regeneration after 2.1.10 showed. And a new
release, size or trainer is an input or a property-group value, not a new
capture.

## Why this matters outside the lab

Every VCF Automation catalog grows the same way. The first blueprint works,
then a second environment, release or team arrives. Generate the blueprints
from one description of the platform. Read its values at request time.
Release through a pipeline that validates and reports. Together, those turn
that growth into routine changes, with a trail anyone can follow.

## Rules learned

- Generate what repeats. Four subnets, three binding maps and 13 uses of one
  naming rule belong in one definition.
- Keep site values out of the blueprint, and make the generator refuse them.
- Decide whose lab it is on the server, from `env.requestedBy`.
- Let the lab build itself, in stages that leave markers and can run again.
- Release through a pipeline that validates first, keeps the form, and
  withdraws the old version on purpose.
- Borrow across approaches. Two settings from a capture-based design became
  one value each here.

## Broadcom documentation

- [Managing Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation.html): blueprints in VCF Automation 9.1, with versions, property groups and forms
- [Sample Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html): `CCI.Supervisor.Namespace` and `CCI.Supervisor.Resource` with VirtualMachine manifests
- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): input and constant property groups
- [Versioning Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html): versions and releasing one to the catalog
- [Creating Custom Forms for Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/learn-more-about-custom-forms-in-vcfa-for-all-apps.html): request forms, each coupled to a blueprint version
- [Deploying and Managing Virtual Machines in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane.html): the VM Service, VM classes, images and content libraries

---
*Lab environment; opinions my own. Everything above was captured from a live VCF 9.1 environment - output trimmed for length, never edited for outcome.*
