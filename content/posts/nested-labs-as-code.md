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
summary: "A catalog in VCF Automation 9.1 that builds a complete nested VCF lab per request, from a jump host to VCF Operations, each in its own VPC. How it differs from capturing a hand-built vPod, the two ideas we borrowed from that route, and six things building from code gives us, each shown on f06."
---

On a Sunday morning our lab catalog took one request, made as the student
account `student03`. Nobody touched the lab after that. In the afternoon our
instructor tool showed this:

```text
lab                    owner        project       phase             age          RDP              progress
student03-phase6       student03    lab-students  6 AD integration  7 h 48 min   192.168.144.10   ready (4/4)
```

`ready (4/4)` means all four markers the lab writes as it builds itself are
in: the jump host joined the lab domain at 08:53, the lab vCenter was ready at
10:32, its AD integration at 10:33 and VCF Operations at 11:56, 3 h 18 min
after the request. Behind that RDP address sit a Windows jump host, a domain
controller `dc01` for the lab domain `acme.lab` and four nested ESXi 9.1
hosts. Inside those run the vCenter, on vSAN ESA with a distributed switch,
and VCF Operations.

This series is about the catalog behind that line: one lab in six phases,
generated from one site file and requested by students and trainers in a VCF
Automation 9.1 All Apps organization. First, the other way to do it.

## Two routes to a nested lab

Tom Fojta's post
[Building Nested Labs in VCF Automation 9.1](https://fojta.wordpress.com/2026/05/12/building-nested-labs-in-vcf-automation-9-1/)
takes the other route, and it is well worth reading. He builds a "vPod" by hand
in one Supervisor namespace, captures it as a blueprint with VCF Automation
9.1's
[namespace capture](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/working-with-stateful-blueprints-in-vcf-automation.html),
and deploys copies from it. Each vPod has a VyOS router, with its uplink on a
private VPC subnet and its downlink on a trunk subnet carrying a VLAN
subinterface per lab network. The VLAN subnets are bound to the trunk with
SubnetConnectionBindingMaps but kept off the VPC gateway, so the router routes
between them and masquerades outbound. A DNAT rule on the VPC gateway reaches
the router, which forwards what the lab needs, such as RDP to a jump host. The
ESXi hosts install from the ISO on a VM class with nested virtualization, and
VM Groups set the start-up order. He is open about the rough edges of 9.1.0:
capture leaves out the binding maps, VyOS has no VMware Tools, and guest
customisation needs a workaround.

Two of his ideas are now in our catalog, with thanks to Tom. The first,
`promoteDisksMode: Disabled`, keeps our Windows VMs as linked clones of the
image cache instead of copying about 25 GiB each after power-on. On our domain
controller test item, request to domain-joined fell from 17.6 to 15.1 minutes,
and guest operations answered 9 minutes sooner. The second is `vmkernel9Guest`
on our blank hosts, their image's own guest type at hardware version 22.

| | Capture a hand-built vPod | Generate from a site file |
|---|---|---|
| A lab is defined by | The lab itself, built by hand and captured | A site file and a generator; the blueprints are their output |
| Network and routing | A router VM per lab routes the VLAN subnets, NATs outbound and forwards what comes in | VLAN subnets on a trunk, routed by the VPC gateway; NAT and RDP on the VPC |
| Versions and sizes | As captured; another version is another vPod | Picked on the request form |
| Another platform | Carry the images across, or build and capture again | A new site file and a property-group sync |
| Updating | Change the vPod by hand, capture again | Change a script or the generator, release a version |
| Time to deploy | Copies of a finished lab: nothing left to build | Minutes for blank hosts; 3 h 15 min to 3 h 30 min when the lab builds its own vCenter and VCF Operations |
| What a lab carries | Whatever was done by hand, including state no script knows | Exactly what the scripts do, logged step by step |

Capture wins for a one-off: build the lab once, the way you like it, and every
copy starts from those disks, including the things nobody wrote down.
Generating pays off when labs repeat: a copy for every student, a new ESXi
build, a move to another platform, many people requesting without help. We had
all four.

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

Every image and folder is then looked up as
`propgroup.nestedLabMedia.releases[input.release].<key>`, and the namespace
quota is computed from the sizes asked for. The lab above was requested with
VCF Operations at Small, on a host of its own: 3 h 18 min to a finished lab,
against about four hours at Extra small.

### No router VM

Our lab networks are ordinary private VPC subnets. Three binding maps put
management, vMotion and vSAN onto the hosts' trunk subnet as VLANs 1610, 1611
and 1612, in [the trunk design from the Pod Papers](/posts/nested-esxi-nsx-vpc/),
and the VPC gateway routes them like any other subnet. A student's Phase 1 lab
on f06, read from the Supervisor a minute after it came up:

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

Six VMs, and none of them routes. The VPC's own SNAT takes traffic out, RDP to
the jump host comes in through the VPC's load balancer (`jump-access`), and
the shared binaries server lives in another VPC,
[across the transit gateway](/posts/shared-services-for-isolated-tenants/): a
trace from a jump host to it passes the VPC gateway, 172.30.0.33, then the
transit gateway. There is no router to patch, no VM without VMware Tools, and
nothing extra to capture.

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
from it. The blueprints carry references instead of site values, which VCF
Automation resolves when a lab is requested. The binding maps take their VLANs
from the group, and `dc01` its image, guest type, VM class, storage and disk
mode:

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
six values in two property groups, and all eight blueprints regenerated
identical, byte for byte. A second, made-up site file, with its own region,
address plan and VLANs, generates the same eight: they differ from f06's only
in the lab list, the form's starting values and the sample accounts.

### Phases are restore points

The catalog offers one lab at six points of a class. Phase 1 is the jump host,
`dc01` as a plain Windows server and four blank hosts with the ESXi installer
attached. Phase 2 adds the domain, 3 installed hosts, 4 the lab vCenter, 5 VCF
Operations, and 6 the lab domain as a sign-in source for both. Each phase holds
everything before it, so each is a restore point. When a student's hosts break
in the vCenter chapter, the lab is deleted and Phase 4 requested again; about
1 h 50 min later the student carries on with a working vCenter. On f06 every
phase has been requested from scratch, which is all a restore is.

### Every student gets the same lab

Each lab has a VPC of its own and
[the same addresses inside it](/posts/three-datacenters-one-ip-plan/): `dc01`
at 172.30.0.34, the jump host at .35, the hosts at .40 to .43, the vCenter at
.50 and VCF Operations at .51, all in `acme.lab`. The class manual needs no
table per seat. The labs are also kept apart: on f06 two students each
requested Phase 1, each saw only their own deployment, and each got a 404
opening the other's by its ID.

### Blueprints tested and released like software

The blueprints are build output. The generator refuses to write one that
contains a site value, VCF Automation validates each, and a draft request
deploys an unreleased blueprint as a real lab before anyone else sees it. One
tool then releases all eight as one version and withdraws the last. The Phase 6
item's lines from the 30 September release:

```text
== lab-phase-6-ad-integration (default-project, labname) -> blueprint-nested-esxi-lab-full.yaml 2.1.10, 92527 bytes
   version 2.1.10 request form: custom (dc947b26-b884-4c33-8c41-71a865db34af)
   un-release 2.1.9: 200
   release 2.1.10: 200
   versions now: [('2.1.10', True), ('2.1.9', False), ('2.1.8', False), ('2.1.7', False), ...
```

That was its 21st version. Every earlier one stays in VCF Automation, so
rolling back is releasing an older one, and a running lab keeps the version it
was built from.

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

A lab defined as code is a product, not a pet. Anyone allowed can request it,
it comes out the same every time, and it moves to another platform or release
without anyone repeating clicks. A training team gets one set of instructions
for every seat and a reset button for every student; a platform team gets its
changes as reviewed files and released versions. The same pattern fits
anything people need many identical copies of: demo kits, proof-of-concept
sandboxes, rehearsal copies of a production design.

## Rules learned

- Capture a lab you need once; generate a lab you need again.
- Keep every site value in one file, and let the blueprints read it when a
  lab is requested.
- Let the VPC route. Binding maps carry the VLANs; the VPC gateway, its NAT
  and its load balancer do the rest.
- Put releases and sizes on the request form, not in a captured image.
- Make every phase a restore point: a broken lab is deleted and requested
  again.
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
