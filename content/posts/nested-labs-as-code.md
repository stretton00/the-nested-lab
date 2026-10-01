---
title: "Nested labs in VCF Automation 9.1, built from code instead of captured"
date: 2026-10-28
draft: false
tags: [vcf, vcf-automation, nested-esxi, nsx, vpc, blueprints, training-labs, homelab]
products: ["VCF Automation", "NSX"]
series: ["Nested Labs as Code"]
seriesPart: 1
tldr:
  - "A VCF Automation catalog builds a complete nested lab per request, from jump host to VCF Operations, in its own VPC."
  - "Blueprints are generated from one site file, and the VPC gateway does the routing, with no router VM to patch."
  - "Capture a lab you need once, and generate a lab you need again."
tested: "VCF 9.1"
cover:
  image: "/images/post34-hero-labs-as-code.svg"
  alt: "site-f06.yaml feeds gen_lab_blueprint.py, which writes eight blueprints and two property groups; each request builds a lab in its own VPC with a jump host, dc01, four nested hosts, vCenter, VCF Operations and AD, routed by the VPC gateway with no router VM"
  hidden: false
summary: "A VCF Automation 9.1 catalog that builds a complete nested VCF lab per request, each in its own VPC. How it differs from capturing a hand-built lab, and what building from code buys you."
---

On a Sunday morning, our lab catalog took one request, made as the student
account `student03`. After that, nobody touched the lab. In the afternoon, our
instructor tool showed this:

```text
lab                    owner        project       phase             age          RDP              progress
student03-phase6       student03    lab-students  6 AD integration  7 h 48 min   192.168.144.10   ready (4/4)
```

`ready (4/4)` means all four markers the lab writes as it builds itself are
in. The jump host joined the lab domain at 08:53. The lab vCenter was ready
at 10:32, and its Active Directory integration at 10:33. VCF Operations came
last, at 11:56, 3 h 18 min after the request.

Behind that RDP address sit a Windows jump host, a domain controller `dc01`
for the lab domain `acme.lab`, and four nested ESXi 9.1 hosts. Inside those
run the vCenter, on vSAN ESA (Express Storage Architecture) with a
distributed switch, and VCF Operations. A complete VCF lab, then, from one
request and no further help. Easily the most productive Sunday I've spent
doing nothing.

This series is about the catalog behind that line. It's one lab in six
phases, generated from one site file, and requested by students and trainers
in a VCF Automation 9.1 All Apps organization. If you've ever built the same
lab by hand twice, read on. First, though, the other way to do it.

## Two routes to a nested lab

Tom Fojta's post
[Building Nested Labs in VCF Automation 9.1](https://fojta.wordpress.com/2026/05/12/building-nested-labs-in-vcf-automation-9-1/)
takes the other route, and it's well worth reading. He builds a "vPod" by
hand in one Supervisor namespace. Then he captures it as a blueprint with VCF
Automation 9.1's
[namespace capture](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/working-with-stateful-blueprints-in-vcf-automation.html),
and deploys copies from it.

Each vPod has a VyOS router. Its uplink sits on a private VPC subnet, and its
downlink on a trunk subnet that carries a VLAN subinterface per lab network.
He binds the VLAN subnets to the trunk with SubnetConnectionBindingMaps, but
keeps them off the VPC gateway. So the router routes between them, and
masquerades their traffic on the way out. A DNAT rule on the VPC gateway
reaches the router, which forwards what the lab needs, such as RDP to a jump
host.

The ESXi hosts install from the ISO on a VM class with nested
virtualisation, and VM Groups set the start-up order. He's open about the
rough edges of 9.1.0: capture leaves out the binding maps, VyOS has no VMware
Tools, and guest customisation needs a workaround.

Two of his ideas are now in our catalog, with thanks to Tom. The first is
`promoteDisksMode: Disabled`. It keeps our Windows VMs as linked clones of the
image cache, instead of copying about 25 GiB each after power-on. On our
domain controller test item, the time from request to domain-joined fell from
17.6 to 15.1 minutes, and guest operations answered 9 minutes sooner. The
second is `vmkernel9Guest` on our blank hosts: their image's own guest type,
at hardware version 22.

| | Capture a hand-built vPod | Generate from a site file |
|---|---|---|
| A lab is defined by | The lab itself, built by hand and captured | A site file and a generator; the blueprints are their output |
| Network and routing | A router VM per lab routes the VLAN subnets, NATs outbound and forwards what comes in | VLAN subnets on a trunk, routed by the VPC gateway; NAT and RDP on the VPC |
| Versions and sizes | As captured; another version is another vPod | Picked on the request form |
| Another platform | Carry the images across, or build and capture again | A new site file and a property-group sync |
| Updating | Change the vPod by hand, capture again | Change a script or the generator, release a version |
| Time to deploy | Copies of a finished lab: nothing left to build | Minutes for blank hosts; 3 h 15 min to 3 h 30 min when the lab builds its own vCenter and VCF Operations |
| What a lab carries | Whatever was done by hand, including state no script knows | Exactly what the scripts do, logged step by step |

Capture wins for a one-off. Build the lab once, the way you like it, and
every copy starts from those disks, including the things nobody wrote down.
Generating pays off when labs repeat: a copy for every student, a new ESXi
build, a move to another platform, many people requesting without help. We
had all four, which rather settled it.

## What building from code gives us

### Versions and sizes at request time

In our catalog, versions and sizes are form fields. From the Phase 6
blueprint, trimmed:

```yaml
  hostSize:
    type: string
    title: Nested host size
    ...
    default: medium
    oneOf:
      - title: Medium - 16 vCPU / 64 GiB per host
        const: medium
      - title: Large - 32 vCPU / 128 GiB per host
        const: large
...
  release:
    type: string
    title: Software release
    ...
    oneOf:
      - title: "VCF 9.1.0 - ESXi 9.1.0.0200, vCenter 9.1.0.0200, VCF Operations 9.1.0.0400"
        const: vcf-9.1.0
```

The blueprint then looks up every image and folder as
`propgroup.nestedLabMedia.releases[input.release].<key>`, and works out the
namespace quota from the sizes asked for. The lab above was requested with
VCF Operations at Small, on a host of its own. It was finished 3 h 18 min
after the request, against about four hours at Extra small.

### No router VM

Our lab networks are ordinary private VPC subnets. Three binding maps put
management, vMotion and vSAN onto the hosts' trunk subnet as VLANs 1610, 1611
and 1612, following
[the trunk design from the Pod Papers](/posts/nested-esxi-nsx-vpc/). The VPC
gateway routes them like any other subnet. Here's a student's Phase 1 lab on
f06, read from the Supervisor a minute after it came up:

```text
namespace ns-student03-pj5nt
dc01-student03    PoweredOn
esx01-student03   PoweredOn
esx02-student03   PoweredOn
esx03-student03   PoweredOn
esx04-student03   PoweredOn
jump-student03    PoweredOn
jump-access   LoadBalancer   10.96.1.153   192.168.144.10   3389/TCP   76s
```

Six VMs, and not one of them routes. The VPC's own SNAT takes traffic out.
RDP to the jump host comes in through the VPC's load balancer
(`jump-access`). The shared binaries server lives in another VPC,
[across the transit gateway](/posts/shared-services-for-isolated-tenants/).
A trace from a jump host to it passes the VPC gateway, 172.30.0.33, then the
transit gateway. So there's no router to patch, no VM without VMware Tools,
and nothing extra to capture.

### One site file per platform

Everything that differs between platforms sits in one YAML file: region, zone
and classes, image IDs, the binaries server and the lab's address plan. From
`site-f06.yaml`:

```yaml
  network:
    mask: 255.255.255.224
    mgmt:    {cidr: 172.30.0.32/27, gateway: 172.30.0.33, vlan: 1610}
    vmotion: {cidr: 172.30.0.64/27, gateway: 172.30.0.65, vlan: 1611}
    vsan:    {cidr: 172.30.0.96/27, gateway: 172.30.0.97, vlan: 1612}
```

A generator writes eight blueprints and two
[property groups](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html)
from it. The blueprints carry references instead of site values, and VCF
Automation resolves them when a lab is requested. The binding maps take their
VLANs from the group, and `dc01` takes its image, guest type, VM class,
storage and disk mode:

```yaml
        metadata:
          name: ${'dc01-' + input.labName}
          labels: {app: dc01, role: dc}
        spec:
          imageName: ${propgroup.nestedLabSite.windowsImage}
          guestID: ${propgroup.nestedLabSite.windowsGuestId}
          className: ${propgroup.nestedLabSite.dc.vmClass}
          storageClass: ${propgroup.nestedLabSite.storageClass}
          powerState: PoweredOn
          promoteDisksMode: ${propgroup.nestedLabSite.vmService.windowsPromoteDisksMode}
```

So a changed site value is a sync, not a new blueprint version. When our
binaries server moved to a versioned folder tree, the whole catalog change was
six values in two property groups. All eight blueprints regenerated identical,
byte for byte. Few things are as quietly satisfying as an empty diff.

A second, made-up site file, with its own region, address plan and VLANs,
generates the same eight. They differ from f06's only in the lab list, the
form's starting values and the sample accounts.

### Phases are restore points

The catalog offers one lab at six points in a class. Phase 1 is the jump
host, `dc01` as a plain Windows server, and four blank hosts with the ESXi
installer attached. Phase 2 adds the domain, Phase 3 installed hosts, Phase 4
the lab vCenter and Phase 5 VCF Operations. Phase 6 adds the lab domain as a
sign-in source for both.

Each phase holds everything before it, so each one is a restore point. Say a
student's hosts break in the vCenter chapter. The lab is deleted and Phase 4
requested again, and about 1 h 50 min later the student carries on with a
working vCenter. On f06, every phase has been requested from scratch, which
is all a restore is.

![Six phase cards, each holding everything before it: DC build about 5 min, domain about 15 min, ESXi hosts about 20 min, vCenter about 1 h 50 min, VCF Operations about 3 h 15 min, AD sign-in about 3 h 30 min](/images/diagrams/six-phases-restore-points.svg)
*Each phase is the one before it plus one layer, so any phase is a restore point. Times are request to ready on f06.*

### Every student gets the same lab

Each lab has a VPC of its own, with
[the same addresses inside it](/posts/three-datacenters-one-ip-plan/). `dc01`
is at 172.30.0.34, the jump host at .35, the hosts at .40 to .43, the vCenter
at .50 and VCF Operations at .51, all in `acme.lab`. So the class manual needs
no table per seat.

The labs are also kept apart. On f06, two students each requested Phase 1.
Each saw only their own deployment, and each got a 404 when opening the
other's by its ID.

### Blueprints tested and released like software

The blueprints are build output, and they're treated that way. The generator
refuses to write one that contains a site value, and it can't be talked
round. VCF Automation validates each one. A draft request then deploys an
unreleased blueprint as a real lab, before anyone else sees it. Finally, one
tool releases all eight as one version and withdraws the previous one. Here
are the Phase 6 item's lines from the 30 September release:

```text
== lab-phase-6-ad-integration (default-project, labname) -> blueprint-nested-esxi-lab-full.yaml 2.1.10, 92527 bytes
   version 2.1.10 request form: custom (dc947b26-b884-4c33-8c41-71a865db34af)
   un-release 2.1.9: 200
   release 2.1.10: 200
   versions now: [('2.1.10', True), ('2.1.9', False), ('2.1.8', False), ('2.1.7', False), ...
```

That was its 21st version. Every earlier one stays in VCF Automation, so
rolling back means releasing an older one. And a running lab keeps the
version it was built from.

## What the series covers next

The next five posts take the catalog apart:

- what a catalog like this is for: a class, a demo, a new release side by
  side, an offline rehearsal and testing tools;
- the network inside a lab VPC, and how the VPC gateway compares with
  provider VLANs and a router VM;
- the six phases, what a student and a trainer each get, and how anyone can
  tell a lab is ready;
- inside the blueprint: what a phase is made of, how the lab builds itself,
  and the pipeline that releases it;
- making it yours: a new site, a new release, a new size or address plan, and
  a new lab.

## Why this matters outside the lab

A lab defined as code is a product, not a pet. Nobody mourns it when it's
deleted. Anyone allowed can request it, it comes out the same every time, and
it moves to another platform or release without anyone repeating clicks.

A training team gets one set of instructions for every seat, and a reset
button for every student. A platform team gets its changes as reviewed files
and released versions. The same pattern fits anything people need many
identical copies of: demo kits, proof-of-concept sandboxes, rehearsal copies
of a production design.

## Rules learned

- Capture a lab you need once; generate a lab you need again.
- Keep every site value in one file, and let the blueprints read it when a
  lab is requested.
- Let the VPC route. Binding maps carry the VLANs, and the VPC gateway, its
  NAT and its load balancer do the rest.
- Put releases and sizes on the request form, not in a captured image.
- Make every phase a restore point: a broken lab is simply deleted and
  requested again.
- Release blueprints like software: generate, lint, deploy a draft, then
  release one version of everything.

## Broadcom documentation

- [Capturing Namespaces as Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/working-with-stateful-blueprints-in-vcf-automation.html): the capture route, and what it takes from a namespace.
- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): property groups, shared across an organization or a project.
- [Versioning Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html): versions, releasing one to the catalog, restoring an older one.
- [Add a Subnet to a VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-subnet-for-the-vpc.html): the Private and Private Transit Gateway subnets the labs and the binaries server use.
- [Transit Gateways](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/transit-gateways.html): how VPCs reach each other and the outside.
- [Working with VM Classes in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/working-with-vm-classes-in-vsphere-with-tanzu.html): custom VM classes, like the ones that size the nested hosts.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
