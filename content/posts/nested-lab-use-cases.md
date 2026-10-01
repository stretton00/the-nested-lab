---
title: "What a nested lab catalog is for"
date: 2026-11-04
draft: false
tags: [vcf, vcf-automation, nested-esxi, training-labs, self-service, homelab]
products: ["VCF Automation"]
series: ["Nested Labs as Code"]
seriesPart: 2
tldr:
  - "One catalog of nested VCF labs serves a class, a demo, a release trial, an offline rehearsal and tool testing."
  - "Instead of five precious hand-built environments, the team keeps one design and everyone gets a lab they are allowed to break."
  - "Build ahead what takes hours, request live what takes minutes, and rehearse each use before it counts."
tested: "VCF 9.1"
cover:
  image: "/images/post35-hero-use-cases.svg"
  alt: "One lab catalog, four of its uses: a class with the same lab for every student, a demo on a Phase 6 built ahead, a new release side by side, and an offline rehearsal of an install; each lab is requested, built, used, deleted and requested again"
  hidden: false
summary: "A catalog that builds a complete nested VCF lab per request is more than a classroom tool. Five uses, each with who gains and the catalog feature that makes it work: a class, a demo, a new release side by side, an offline install rehearsal, and testing tools against a real vCenter and VCF Operations. What we ran on f06, and what the design supports that we have not run yet."
---

On a Sunday morning, two hours after it was requested and with nobody laying
a finger on it, a lab's jump host showed this:

```text
AD-DETAILS.txt 08:53:01
LAB-README.txt 08:44:12
VCENTER-AD-READY.txt 10:33:27
VCENTER-READY.txt 10:32:37
10:33:12  permission: ACME\gg_vsphere_administrators -> Admin at the vCenter root, propagating
10:33:20  permission: ACME\gg_vsphere_operators -> Lab Operators at the vCenter root, propagating
10:33:27  permission: ACME\gg_vsphere_readonly -> ReadOnly at the vCenter root, propagating
10:33:27  === done: log in to https://vcsa.acme.lab/ui as alice@acme.lab (administrator), carol (operator) or bob (read-only) ===
```

It was a Phase 6 lab, built for a demo the next day. Its vCenter was up, with
the lab domain as its identity source and three users on three levels of
rights. [The first post in this series](/posts/nested-labs-as-code/) opened on
the same lab, and showed how the catalog builds labs from code instead of
capturing them.

This one is about what that's good for: five uses, who gains from each, and
the catalog feature that makes each one work. We've run most of them on f06.
Where the design supports something we haven't run yet, I say so, rather than
hoping nobody asks.

![One catalog, five uses: a class, a demo, a new release side by side, an offline rehearsal and testing tools, each with who gains and the feature that makes it work](/images/diagrams/lab-use-cases.svg)
*One catalog, five jobs. The sections below take them one at a time.*

## A class

**Who gains:** students and trainers.

A class needs the same lab at every seat, labs that can't see each other, and
a way back for a student who falls behind. The catalog gives each student a
lab in a VPC of their own, with the same addresses and the same `acme.lab`
domain inside. So the manual reads the same everywhere. On f06, `student03`
requested Phase 1, and then `student01` went looking for that lab by its
deployment ID:

```text
deployments visible: 200 [('student03-rehearsal', 'student03', 'CREATE_SUCCESSFUL')]
...
student01 GET /deployment/api/deployments/<id> -> 404
student01 GET /deployment/api/deployments/<id>/actions -> 404
student01 GET /deployment/api/deployments/<id>/resources -> 404
deployments visible: 200 []
```

The first line is `student03`'s own view. The rest is `student01`: no way into
the other lab, and no deployments of their own. Three blank stares in a row.
Not the warmest of welcomes, but exactly the one we wanted.

The class leans on three more features:

- **Phases are restore points.** A student who breaks a lab, or falls behind,
  gets a fresh one at the phase the class has reached.
- **One item serves both audiences.** A student's request always lands in
  their own VPC. A trainer on a trainers list, which the blueprint checks on
  the server, can pick any student's lab from the same item. On f06, a test
  trainer built `student04`'s Phase 1 into `vpc-student04`. Meanwhile, a
  student who put `student04` on the form still got their own lab.
- **Long phases are built ahead.** Phases 5 and 6 take over three hours, so
  trainers request them before the class, a few at a time. One status tool
  lists every lab with its markers.

What f06 hasn't had is a class of students. We ran the rehearsals and the
acceptance tests a class needs, but not a class week.

## A demo

**Who gains:** whoever gives it, and an audience that sees a finished VCF lab
and a live request.

A demo works backwards from build times the catalog already publishes: each
item's description ends with how long it takes. The lab above was requested
at 08:38 the day before the demo. VCF Operations, its last step, was ready at
11:56. That gives a demo its two halves.

The first half is the finished lab. It has a vCenter where `alice`, `carol`
and `bob` sign in with three different rights. On the jump host's desktop,
`START-HERE.html` lists the build steps with their times, the links, and who
signs in where.

The live half is a short phase, requested in front of the audience. We
rehearsed it that afternoon, beside the finished lab. A student requested
Phase 2 at 13:10, and at 13:25 its jump host had joined the lab domain. The
finished lab was checked again the next morning: all green, the only colour
anyone wants to see on the morning of a demo.

One thing that first demo lab still needed by hand was the VCF Operations
first-login wizard and the start of its collection. Builds since do both, as
the rehearsal below shows. Getting there
took two days, not helped by a message reading "no any VCF license", which sent
me hunting for a licence problem that wasn't there. The cure was to start
collection the way the UI's own Save button does.

## A new release, side by side

**Who gains:** the platform team, and trainers moving a course to a newer
build.

A release in this catalog is a named set of ESXi, vCenter and VCF Operations
builds that belong together. The request form offers releases, rather than
three version pickers that may not fit each other. Each release is an entry in
the site file, synced into the
[property group](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html)
`nestedLabMedia`:

```yaml
defaultRelease: vcf-9.1.0
releases:
  vcf-9.1.0:
    title: VCF 9.1.0 - ESXi 9.1.0.0200, vCenter 9.1.0.0200, VCF Operations 9.1.0.0400
    esxAppliance: vmi-06c9d169cecd2eb9d      # Nested_ESXi9.1.0.0_Appliance_Template_v1.0 (hardware version 20)
    ...
    esxIso: vmi-e400a813bbd5d52a5            # ESXi 9.1.0.0200 installer
    ...
    vcsaFolder: vcenter/9.1.0.0200-25573614/ovf/      # the VCSA OVF on the binaries server (v2 tree since 26 Sep; v1 was vcsa/)
    ...
    opsFolder: ops/9.1.0.0400-25541561/ovf/          # the VCF Operations 9.1.0.0400 OVF + disks (v1 was ops/)
```

The same blueprint serves every release. The binaries server keeps each build
in a folder of its own, and a running lab keeps the release it was built with.
So a lab on the next release can run beside today's for as long as the trial
takes. Students follow `defaultRelease`, so moving the class over afterwards is
one property-group sync. It's the lab-sized version of
[rehearsing on a fresh instance of the right version](/posts/one-catalog-item-one-vcf-instance/).

To be straight about it: f06 has one release so far, which makes for a fairly
short side-by-side. A second release is data, plus one new option in the
form's Release list. The data is its images in the content library, its files
on the binaries server, and an entry beside `vcf-9.1.0`. The new option is the
only part that needs a new blueprint version, because an input's list of
choices can't come from a property group.

## Rehearsing an install offline

**Who gains:** the platform team preparing an install at a site without
internet access, and whoever runs it there.

Nothing inside a lab needs the internet. The build scripts, the vCenter and
VCF Operations files and, for a template without it, PowerCLI all come from
the shared binaries server. So a rehearsal is simply a lab with its internet
taken away.

We rehearsed both halves on f06. For the lab half, we built a Phase 6 lab with
its Windows machines cut off from the internet by their own firewall. Those
are the machines that run every build step. For the server half, a throwaway
binaries server with no internet installed its web and NFS packages from a
folder of offline packages. The lab finished 3 h 31 min after the request.
These are among the last lines of the follower watching it:

```text
14:36:33  60.2 min markers: OPS-READY.txt,VCENTER-AD-READY.txt,VCENTER-READY.txt | last ops-build.log=14:36:14 === VCF Operations ready: https://172.30.0.51/ui (ops.acme.lab) admin ===
...
14:36:51  60.5 min ops: 14:32:22 ready: first-login wizard finished (EULA accepted, management packs configured)
...
14:36:51  60.5 min ops: 14:33:35 collection started (account saved and started as the UI does)
...
14:36:51  60.5 min ops: 14:36:14 AD sign-in: checked - alice@acme.lab signs in (gg_vcf_ops_administrators)
```

The minutes count from a restart of the follower, not from the request. Every
marker is there, VCF Operations is collecting from the lab vCenter, and the
lab's Active Directory (AD) users sign in to it.

The rehearsal also earned its keep. It found one step for the install guide
to change: the offline packages must be installed from `/tmp`, because apt
can't read them in the `ubuntu` user's home folder.

## Testing tools against a real vCenter and VCF Operations

**Who gains:** the platform team, and anyone who writes automation for vCenter
or VCF Operations.

Phases 4 to 6 give a real vCenter on request, and Phases 5 and 6 add VCF
Operations. Active Directory is there from Phase 2. It's all at the same
addresses every time, so a test script needs no settings per lab. A lab broken
by a bad test is simply deleted and requested again.

Our own build scripts are the first tools we test this way, and the ones that
need it most. When the Phase 6 AD step stopped at creating a vCenter role, we
ran a short script on a lab's jump host. It tried four ways to read a role's
privileges from that lab's vCenter:

```text
PowerCLI Core 13.3.0.24145081
A  Get-VIPrivilege -Server -Role : Parameter set cannot be resolved using the specified named parameters.
B  Get-VIPrivilege -Role         : OK, 512 privileges
C  Get-VIPrivilege -Server -Id   : OK, 512 privileges
...
Get-VIPrivilege parameter sets: Server(Name,Id,Server) Role(Name,Role,Id) Group(Name,Id)
```

In PowerCLI 13.3, `-Role` and `-Server` belong to different parameter sets.
The fix went into the build script, and the same lab ran the step again. This
time it created the role and three group permissions, and `alice`, `carol` and
`bob` signed in with administrator, operator and read-only rights.

VCF Operations got the same treatment. Lab instances are where we worked out
how the build
[imports the lab domain's groups](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/-configuring-administration-settings/managing-user-access-control/authentication-sources-overview/authentication-sources-add-authentication-source-for-user-and-group-import.html)
so that they keep their members. Every Phase 6 build now checks each group
with a real sign-in: that's the last line of the rehearsal output above.

## Why this matters outside the lab

Most teams that run VCF need the same few environments again and again. They
need somewhere to train people, something to show, a place to try the next
release, a rehearsal before a change, and a target for their own automation.
Usually each one is built by hand, drifts, and ends up too precious to break,
like the good china.

One catalog that builds complete, identical and disposable labs covers all
five, and turns each from a small project into a request. The platform team
keeps one design instead of five pets, and everyone else gets a lab they're
allowed to break.

## Rules learned

- One catalog, many audiences: build the lab once as code, and let each use
  pick a phase, a release and a size.
- Rehearse each use on the catalog before it counts: the demo's live request,
  the students' own path, the offline install.
- Build ahead what takes hours; request live what takes minutes.
- A release is data: a named set of builds in a property group, not a new lab
  design.
- Keep everything a lab fetches inside the platform. An offline rehearsal is
  then just a firewall rule.
- Test automation against a disposable copy that has the same addresses every
  time.

## Broadcom documentation

- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): property groups, where the releases and the trainers list live.
- [Versioning Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html): the new version that a new Release option needs.
- [Creating Custom Forms for Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/learn-more-about-custom-forms-in-vcfa-for-all-apps.html): request forms, one per blueprint version.
- [Bill of Materials 9.1.0](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/release-notes/vmware-cloud-foundation-9-1-0-0-release-notes/vmware-cloud-foundation-bill-of-materials.html): the component builds that make up a VCF release.
- [Authentication Sources: Add Authentication Source for User and Group Import](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/-configuring-administration-settings/managing-user-access-control/authentication-sources-overview/authentication-sources-add-authentication-source-for-user-and-group-import.html): AD sign-in to VCF Operations, as Phase 6 sets it up.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
