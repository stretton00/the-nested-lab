---
title: "Six phases, one catalog: what a student and a trainer get"
date: 2026-11-18
draft: false
tags: [vcf, vcf-automation, self-service, nested-esxi, training-labs, homelab]
products: ["VCF Automation"]
series: ["Nested Labs as Code"]
seriesPart: 4
cover:
  image: "/images/post37-hero-six-phases.svg"
  alt: "Six catalog items as six restore points, from a jump host with blank hosts to a lab with vCenter, VCF Operations and Active Directory sign-in; students request Phases 1 and 2, trainers build any phase for any student"
  hidden: false
summary: "A student signs in, sees two catalog items, makes two decisions on a form and gets a complete nested lab: an RDP address, a README with the lab's facts and, from Phase 3, a start page that follows the build. A trainer uses the same catalog to build or rebuild any student's lab and pre-builds the long phases. The six phases as restore points, what each takes on f06, and how everyone can tell when a lab is ready."
---

`student01` is an Organization User in VCF Automation and a member of one
project. Signed in through the API, this is everything the catalog offered,
followed by the student's first request:

```text
session: user=student01 org=dev-01 roles=['Organization User']
projects: 403 {"message":"forbidden","statusCode":403,...}
catalog items: 200 ['lab-phase-1-dc-build', 'lab-phase-2-blank-hosts']
deployments visible: 200 []
request as student01: 200 inputs={} [{"deploymentId": "94a21cdf-c750-492e-ba5e-e067c3241954", "deploymentName": "student01-rehearsal"}]
```

Two items, no projects to browse, nothing deployed yet. The request carried
no inputs at all, because every field has a default. Ten minutes later the
Supervisor held the whole lab, in the student's own VPC:

```text
namespace ns-student01-vbrsg
dc01-student01    best-effort-small    PoweredOn
esx01-student01   nested-esx-large     PoweredOn
esx02-student01   nested-esx-large     PoweredOn
esx03-student01   nested-esx-large     PoweredOn
esx04-student01   nested-esx-large     PoweredOn
jump-student01    best-effort-medium   PoweredOn
...
jump-access   LoadBalancer   10.96.3.121   192.168.144.10   3389/TCP   9m9s

lab-students supervisor namespace ns-student01-vbrsg vpc vpc-student01 class nested-pod
```

This post is about that experience for the two kinds of people who use the
catalog: the student who works in a lab, and the trainer who looks after a
class of them.

## Six restore points

The catalog offers the lab at six points of the class. Each phase has
everything the one before it has, plus the next piece, so a phase is also a
restore point: a student whose lab breaks in the vCenter exercise gets a
Phase 4 lab and carries on. The design is in
[the first post of this series](/posts/nested-labs-as-code/); this is the
menu, with the build times on f06, a platform nested two levels deep:

| Phase | Catalog item | What it adds | Ready in |
|---|---|---|---|
| 1 | `lab-phase-1-dc-build` | the jump host; `dc01` as plain Windows Server 2025 for the class to promote; four blank hosts with the ESXi installer attached | about 5 min |
| 2 | `lab-phase-2-blank-hosts` | `dc01` as the domain controller of `acme.lab`, with DNS and NTP; the jump host in the domain | about 15 min |
| 3 | `lab-phase-3-esxi-hosts` | four installed ESXi hosts, 172.30.0.40 to .43 | about 20 min |
| 4 | `lab-phase-4-vcenter` | the lab vCenter at .50, with vSAN ESA, a distributed switch and the binaries datastore | about 1 h 50 min |
| 5 | `lab-phase-5-ops` | VCF Operations at .51, with the lab vCenter added | about 3 h 15 min |
| 6 | `lab-phase-6-ad-integration` | the lab domain as the identity source of vCenter and VCF Operations | about 3 h 30 min |

Phases 5 and 6 are timed with VCF Operations at Small; at Extra small they
take four hours or more. In every phase the two Windows VMs start as linked
clones of the image cache, one of the two ideas from Tom Fojta that
[the first post](/posts/nested-labs-as-code/) credits.

## The student: two decisions and a desktop

Phases 1 and 2 are the students' own. Their
[request form](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/learn-more-about-custom-forms-in-vcfa-for-all-apps.html)
has two tabs. `Your lab` opens with a short text of rules, then the two
decisions a student makes: the size of the nested hosts and the jump host's
password. `Trainer options` holds the fields that a student's request
ignores. Our form tool printed each phase's layout before storing it:

```text
lab-phase-1-dc-build (lab-students): catalog item 1a783a02-4f35-3d70-8ba3-f2d55bff7c26, blueprint 0ecb54ff-73bd-4e23-aec1-15b776be943f, custom forms now: none
  tab Your lab:        hostSize, jumpPassword
  tab Trainer options: labName, release, jumpSize, capacityDiskGi, bootDiskGi
...
lab-phase-6-ad-integration (default-project): catalog item 784f409d-440e-3399-9234-6682629509a9, blueprint 1e25a988-3a55-4365-a0ed-f8bb3260e7fc, custom forms now: none
  tab Lab:             labName, hostSize, vcsaSize, opsSize, esxPassword, vcsaPassword, opsPassword, jumpPassword
  tab Trainer options: release, jumpSize, capacityDiskGi
```

The rules text uses the portal's own words for what people trip over: the lab
goes into the student's own network, `vpc-<user name>`; one lab at a time,
deleted before the next and followed by a five-minute wait once it has left
Instances; blank hosts are installed from their web console; and the RDP
address is in the lab's User Events, as the CREATE event's `rdp` output.

![The Phase 1 request form signed in as student01: on the Your lab tab, the deployment name, the rules text, the nested host size and the jump host password](/images/ui/phase1-form-your-lab.png)

Over RDP, the jump host's desktop is the lab's documentation, generated with
the lab so that it cannot drift from it. `LAB-README.txt` has the lab's
hosts, networks and names, and current labs put the passwords chosen on the
form at the top. A Phase 1 lab's README, read off its desktop:

```text
Training lab student02
Nested ESXi hosts (VLAN 1610, gateway 172.30.0.33):
172.30.0.40  esx01  esx01.acme.lab
172.30.0.41  esx02  esx02.acme.lab
172.30.0.42  esx03  esx03.acme.lab
172.30.0.43  esx04  esx04.acme.lab
Networks in this lab: management VLAN 1610 172.30.0.32/27, vMotion VLAN 1611 172.30.0.64/27, vSAN VLAN 1612 172.30.0.96/27
dc01 (172.30.0.34) is a plain Windows Server 2025 - building the lab's domain controller is part of the class:
promote it to acme.lab (NetBIOS ACME) with DNS, then join this jump host to the domain.
...
Hosts arrive blank: install ESXi from the CD-ROM and set the root password
yourself, then give each host its address above in the DCUI.
...
You are on the jump host; it is the only machine reachable from outside the lab.
```

The install happens in each host's console: in the portal, Instances, the
lab, Topology, select a host, then Actions >
[Connect to Web console](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/creating-policies-for-all-apps-orgs/vcfa-all-apps-day-2-policies/vcfa-all-apps-day-2-actions.html).
That is one reason students request their own Phase 1 and 2 labs: the
deployment is theirs, and so is its console.

![student01's Phase 1 lab under Instances: on the Topology tab, esx01 is selected and its Actions menu is open on Connect to Web console](/images/ui/phase1-topology-web-console.png)

Phase 2 builds the domain for them. On a Phase 2 lab that `student01`
requested at 18:38, the jump host's join log ended like this, with the values
for the class manual copied from `dc01`:

```text
18:52:29  member of acme.lab (secure channel OK)
18:52:30  ACME\Domain Users -> Remote Desktop Users
18:52:30  AD-DETAILS.txt copied from dc01
18:52:36  === phase 2 complete ===
AD-DETAILS present:
Active Directory for this lab
=============================
Domain (DNS):        acme.lab
Domain (NetBIOS):    ACME
Domain controller:   dc01.acme.lab  (172.30.0.34)  - also DNS and NTP for the lab
LDAP:                ldap://dc01.acme.lab:389     (LDAPS 636 needs a certificate - use LDAP in class)
```

From Phase 3 the build script also keeps `START-HERE.html` on the desktop:
each build step with the time it finished, buttons for the lab vCenter, VCF
Operations and the hosts' Host Clients, and a sign-in table with the lab's
own passwords. While a step is still building, the page refreshes itself
every two minutes.

![START-HERE.html on a finished Phase 6 lab: all four build steps done, the buttons for the lab vCenter and VCF Operations, and the Sign in table with its passwords blurred](/images/ui/phase6-start-here.png)

## The trainer: the same catalog, any lab

Trainers use the same items. On Phases 1 and 2, the shared ones, a trainer
picks the lab on the Trainer options tab, and the blueprint decides on the
server: if the requester is on the `trainers` list in the site's
[property group](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html),
`nestedLabSite`, the lab goes into the chosen student's VPC; anyone
else's goes into their own. Adding a trainer changes the property group, not
the catalog. On f06, `student06` played the trainer and built `student04`'s
lab:

```text
request as student06: 200 inputs={'labName': 'student04'} [{"deploymentId": "1a54e483-9de6-4d44-b3eb-acc8fc151d97", "deploymentName": "student04-p1t"}]
16:10:50 namespace ns-student04-7lgnz
16:13:01 deployment done, all VMs powered on
```

Phases 3 to 6 live in the trainers' project, with the Lab field on their
first tab, so a trainer can build any phase for any student. The long phases
are where that pays: trainers pre-build a Phase 6 for each student before the
class, and students request Phases 1 and 2 themselves when the exercises call
for them. A pre-built lab belongs to the trainer who requested it: the student
works in it over RDP as usual and asks the trainer for a host console.
Trainers sign in as organization administrators, so Instances shows them
every lab, while a student sees only their own.

## Ready means more than powered on

A deployment shows Create Successful as soon as its VMs are on, within
minutes. From Phase 2 the lab keeps building itself after that, for as long
as the phase needs, so readiness has two layers, and our tools read both.

`phase_watch.py` follows a deployment and stops when every VM is on. The end
of one, for a Phase 6 lab requested at 12:53:

```text
12:54:52 deployment CREATE_INPROGRESS pending=snVsan
12:54:53 VMs: dc01-student02=<none> esx01-student02=<none> esx02-student02=<none> esx03-student02=<none> esx04-student02=<none> jump-student02=<none>
...
12:55:24 deployment CREATE_INPROGRESS pending=none
12:55:26 VMs: dc01-student02=PoweredOn esx01-student02=PoweredOff esx02-student02=PoweredOn esx03-student02=PoweredOff esx04-student02=PoweredOn jump-student02=PoweredOn
12:55:56 deployment CREATE_SUCCESSFUL pending=none
12:55:58 VMs: dc01-student02=PoweredOn esx01-student02=PoweredOn esx02-student02=PoweredOn esx03-student02=PoweredOn esx04-student02=PoweredOn jump-student02=PoweredOn
12:55:59 fullest vSAN disk 58%, 3730 GiB used
12:55:59 deployment done, all VMs powered on
```

The rest is written by the lab itself. Each stage leaves a marker when it
finishes: `domain-joined` in the lab's folder, then `HOSTS-READY.txt`,
`VCENTER-READY.txt`, `VCENTER-AD-READY.txt` and `OPS-READY.txt` on the
desktop. A stage that stops leaves a `-FAILED.txt` that says what happened
and how to run it again. `START-HERE.html` turns the markers into the
student's progress list, and for the people running the class `lab_status.py`
reads them from every lab at once, through guest operations, and counts the
ones each phase needs:

| Phase | A finished lab has written |
|---|---|
| 1 | nothing: the class builds the domain |
| 2 | domain-joined |
| 3 | domain-joined, HOSTS-READY |
| 4 | domain-joined, VCENTER-READY |
| 5 | domain-joined, VCENTER-READY, OPS-READY |
| 6 | domain-joined, VCENTER-READY, VCENTER-AD-READY, OPS-READY |

Two Phase 6 builds for `student03`'s lab from the trainers' project, one 21
minutes in and one finished, as `lab_status.py` showed them:

```text
Labs: 1   fullest vSAN disk: 57.5% (esx02)   memory: 197 GiB free, largest host 43 GiB
lab                    owner        project       phase             age          RDP              progress
student03-p6-206       <api service account> default-proje 6 AD integration  21 min       192.168.144.12   building: next VCENTER-READY (1/4)
                        domain-joined Tue 18:00
...
Labs: 1   fullest vSAN disk: 57.7% (esx02)   memory: 134 GiB free, largest host 27 GiB
lab                    owner        project       phase             age          RDP              progress
student03-p6-208       <api service account> default-proje 6 AD integration  3 h 39 min   192.168.144.12   ready (4/4)
                        VCENTER-READY Wed 02:15
                        VCENTER-AD-READY Wed 02:15
                        OPS-READY Wed 03:50
                        domain-joined Wed 00:30
```

The header answers the question to ask before requesting another lab: the
fullest vSAN disk and the free memory decide whether it fits.

## Rebuild instead of repair

There is no reset button, because the design does not need one: a phase is
the restore point. A student who wants a clean start deletes their lab in
Instances and requests again, and a trainer does the same for any lab. One
rule comes with the shared address plan: one lab per VPC at a time. Every lab
in a student's VPC uses the same subnets, and NSX releases a deleted lab's
subnets a few minutes after VCF Automation reports it gone, which is why the
form asks for five minutes' wait. Our delete tool waits for NSX itself:

```text
04:44:38 deployment=DELETE_INPROGRESS namespaces=1 volumes=12
04:45:00 deployment=DELETE_INPROGRESS namespaces=1 volumes=5
04:45:21 deployment=DELETE_INPROGRESS namespaces=1 volumes=0
04:46:03 deployment=DELETE_INPROGRESS namespaces=0 volumes=0
04:47:07 deployment=gone namespaces=0 volumes=0
clean - vpc-student03 has no subnets left, a new lab can use it
```

Delete, wait for `clean`, request: a rebuild is a routine, not a repair.
[The network post](/posts/lab-network-no-router/) has why every lab's
addresses are the same.

## Why this matters outside the lab

Self-service works when the person requesting only has their own decisions to
make. A student gets a complete lab from two choices, finds its documentation
where they land, and can see for themselves when it is ready. A trainer uses
the same catalog to prepare, rebuild or rescue any lab, with no separate
toolchain. Restore points replace snapshots and reset scripts with something
simpler: ask for the environment as it should be at that step.

The same shape fits any catalog of environments that people learn or test in:
onboarding, customer demos, proofs of concept, support reproductions. Offer
the milestones, keep the form to the requester's decisions, write the facts
onto the environment itself, and make "ready" visible.

## Rules learned

- Offer an environment at its milestones, each a superset of the one before,
  so every request is also a restore point.
- Keep the requester's form to the decisions they make; the rest goes on a
  second tab or into defaults in a property group.
- Generate the documentation with the lab: a README and a start page that
  carry the lab's own addresses and passwords.
- Tell "deployed" from "ready": have each stage write a marker, and count the
  markers per phase.
- Let one catalog item serve students and trainers, and decide on the server
  where a lab lands.
- Rebuild rather than repair: delete, wait until the VPC is clean, request
  again.

## Broadcom documentation

- [Request an Item from the Catalog in VCF Automation for All Apps](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/consumer-interfaces-in-vcf/getting-started-with-the-vcf-automation-catalog/request-a-catalog-item-in-vcf-automation-for-all-apps.html):
  a request, from the catalog to the Instances page.
- [Managing Deployed Instances in VCF Automation for All Apps](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/consumer-interfaces-in-vcf/getting-started-with-the-vcf-automation-catalog/request-a-catalog-item-in-vcf-automation-for-all-apps/managing-instances.html):
  the Instances page, where every lab appears.
- [Day 2 Actions on Catalog-Provisioned Resources Provided with VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/creating-policies-for-all-apps-orgs/vcfa-all-apps-day-2-policies/vcfa-all-apps-day-2-actions.html):
  Delete, Web Console and the other actions.
- [Creating Custom Forms for Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/learn-more-about-custom-forms-in-vcfa-for-all-apps.html):
  the form designer; each blueprint version pairs with its own form.
- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html):
  input and constant property groups.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
