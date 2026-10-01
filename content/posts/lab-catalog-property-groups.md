---
title: "A blueprint that carries no site: property groups for a lab catalog"
date: 2026-12-09
draft: false
tags: [vcf, vcf-automation, blueprints, property-groups, nested-esxi, homelab]
products: ["VCF Automation"]
series: ["The Lab Factory"]
seriesPart: 5
cover:
  image: "/images/post26-hero-catalog-v2.svg"
  alt: "One site file generates both the blueprints and two property groups; at deploy time the blueprints read every site value from the groups"
  hidden: false
summary: "Our nested-lab blueprints worked, and had one platform written all over them: 59 values from the region to every lab address. How they now read all of it from two VCF Automation property groups, what I proved before trusting it, and the lint that keeps literals out."
---

Our nested-lab catalog worked: six phase items and two dev items, each building
an isolated training lab with nested ESXi hosts, a domain controller, a jump
host and, in the later phases, a vCenter and VCF Operations. It also had one
platform written all over it. When I finally counted, 59 values in those
blueprints belonged to the pod they were generated for: the region and zone,
the namespace class, storage policies, VM class names, content-library image
IDs, every address in the lab network plan, the DNS forwarders and the binaries
server URL.

A generator and a per-site YAML file kept that manageable, but the blueprints
themselves were not portable. Moving to another pod meant regenerating and
re-releasing all eight, and nobody could change a value without a new blueprint
version. The goal for this round: blueprints that contain no site at all.

## Where each setting lives now

| Kind | Examples | Lives in |
| --- | --- | --- |
| Site values | region, zone, namespace class, storage, VM classes per size, Windows image, lab DNS domain, forwarders, the lab network plan, binaries URLs | property group `nestedLabSite` |
| Software releases | ESXi, VCSA and Ops images and binaries folders, per release | property group `nestedLabMedia` |
| Per-request choices | lab name, host / vCenter / Ops size, release, passwords | inputs |
| Derived values | esx01 Large for the vCenter; the namespace quota | expressions |
| The lab's shape | host count, names, VM layout, scripts | generator + site file |

The site file is still the one place an operator edits. The generator now
writes the two [property groups](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html) from it as well as the blueprints, and a small
sync tool pushes the groups to VCF Automation:

```text
nestedLabSite: missing - creating it with 67 values
  created nestedLabSite (id 424a2fc4-f0b9-4c9e-b344-684b72f95493)
nestedLabMedia: missing - creating it with 13 values
  created nestedLabMedia (id 5a6a095c-aabb-45b0-8f63-12491b9b308a)
nestedLabSite: up to date
nestedLabMedia: up to date
```

The second run is the important one: a round trip through the API that
changes nothing, so a later difference means someone edited a group in the
UI.

## What a reference looks like

Wherever a blueprint used to say `domain-c9` or `172.30.0.40`, it now says where
to find it. The namespace:

```yaml
className: ${propgroup.nestedLabSite.namespaceClass}
regionName: ${propgroup.nestedLabSite.region}
zones:
  - name: ${propgroup.nestedLabSite.vsphereZone}
    memoryLimit: "${propgroup.nestedLabSite.hostSizes.large.memMi + 2 * propgroup.nestedLabSite.hostSizes[input.hostSize].memMi + (input.opsSize == 'xsmall' ? propgroup.nestedLabSite.hostSizes[input.hostSize].memMi : propgroup.nestedLabSite.hostSizes.large.memMi) + propgroup.nestedLabSite.jumpSizes[input.jumpSize].memMi + propgroup.nestedLabSite.dc.memMi + 'Mi'}"
```

A nested host picks its image from the requested release and its class from
the requested size. esx04 grows when VCF Operations needs it:

```text
'imageName':propgroup.nestedLabMedia.releases[input.release].esxAppliance,'className':(input.opsSize == 'xsmall' ? propgroup.nestedLabSite.hostSizes[input.hostSize].vmClass : propgroup.nestedLabSite.hostSizes.large.vmClass)
```

And inside the jump host's cloud-config, the lab's DNS script and its config
file carry references too, resolved before the VM ever sees them.

## Prove the expression language first

Blueprint validation skips expressions entirely; it only checks literals. So
"valid" said nothing about whether any of this would resolve. Before touching
the generator, I deployed three throw-away blueprints into a free VPC. They
covered each construct the refactor needed: references in namespace fields
and in block scalars, a map indexed by an input, arithmetic on group values,
and an integer where Kubernetes insists on one.

The arithmetic test echoed its results into a ConfigMap:

```text
configmap: {"cpu":"9000","disk":"133","mem":"99328","vlan":"1610","vlanText":"VLAN 1610"}
```

All four match the hand-computed values, so numbers inside an object-typed
property stay numbers. The VLAN test went through a real NSX binding map,
whose schema rejects anything but an integer:

```text
binding map: {"subnetName":"sn-mgmt","targetSubnetName":"sn-trunk","vlanTrafficTag":1610}
```

Only then did the generator change.

## Releases and sizes

A release is a set that belongs together, for example ESXi 9.1.0.0200 with
vCenter 9.1.0.0200 and VCF Operations 9.1.0.0400. The request offers releases,
not three independent version pickers, and every image and folder is looked
up as `releases[input.release].<key>`. Adding a release is data: media on the
binaries server, images in the content library, an entry in the site file, a
sync. The one blueprint change is the Release dropdown itself, because input
lists cannot come from a property group.

The design got its first real test the same morning, when the binaries server
moved from a flat folder to a versioned tree (`vcenter/<build>/`,
`ops/<build>/`, `scripts/`, `tools/`). Hard links kept every old path working
for labs already running. For the catalog, the move was this:

```text
nestedLabSite: 2 change(s)
  scriptsUrl: 'http://172.31.0.34/binaries/' -> 'http://172.31.0.34/binaries/scripts/'
  toolsUrl: 'http://172.31.0.34/binaries/' -> 'http://172.31.0.34/binaries/tools/'
nestedLabMedia: 4 change(s)
  releases.vcf-9.1.0.opsFolder: 'ops/' -> 'ops/9.1.0.0400-25541561/ovf/'
  releases.vcf-9.1.0.opsSparseFolder: 'ops-sparse/' -> 'ops/9.1.0.0400-25541561/sparse/'
  releases.vcf-9.1.0.vcsaFolder: 'vcsa/' -> 'vcenter/9.1.0.0200-25573614/ovf/'
  releases.vcf-9.1.0.vcsaSparseFolder: 'vcsa-sparse/' -> 'vcenter/9.1.0.0200-25573614/sparse/'
```

Six values in two groups. All eight blueprints, regenerated afterwards, came
out byte-for-byte identical.

Host sizes became Small, Medium and Large. Each entry in the group carries the
VM class and the vCPU and memory the quota should count, so the namespace
limits follow the request. The default Phase 5 lab comes out at exactly the
figures the old literal expressions produced: 126976 Mi and 52000 M.

## A lint for literals

The failure mode of "portable" templates is quiet: someone adds a feature,
types an address or an image ID straight into it, and portability is gone
until the next site finds out. So the generator now refuses to write a
blueprint containing any value from either property group. The first run
caught something:

```text
ERROR: site values written into the blueprint (use S()/ST()/M()/MT() instead):
  line 129: vcf-9.1.0  <- default: vcf-9.1.0
  line 132: vcf-9.1.0  <- const: vcf-9.1.0
```

That was the Release dropdown listing the release names. Those are exempt by
design, and the exemption is written down in the lint rather than in
someone's head.

The real test of "no site inside" is a second site. I wrote an example site
file for a made-up platform, with a different region, network plan, VLANs,
image IDs, binaries server and AD domain, and generated the same eight
blueprints from it. The Phase 5 blueprint for that site differs from f06's in
25 lines. Every one is either a password default on the form or a sample
domain account, both lab content by choice. The comparison also caught one
real leak the lint had missed: the NetBIOS name written as text into the jump
host's README. It is a reference now, and the lint checks for that name as a
whole word.

## End to end

Validation cannot see expressions, so the proof had to be a deployment. Before
releasing anything, I requested two of the regenerated blueprints as drafts,
straight from the generator's output, in a VPC nobody was using.

Phase 1, the first lab in the series, was done 13 minutes after the request.
Everything I could check against a hand calculation matched. The namespace
took its class, region and VPC from `nestedLabSite`, and its limits came out
at 44000 MHz and 77824 MB. The hosts were Small, with the release's image and
ESXi ISO. The three binding maps carried 1610, 1611 and 1612 as integers.

Phase 4 adds a vCenter, built by a script on the jump host, and that script
takes the network plan and the release folders from the lab's config file. So
the file the jump host received is the real test. Trimmed, with the passwords
masked and the host list cut:

```text
"zone": "acme.lab",
"labId": "student02",
"netbios": "ACME",
"release": "vcf-9.1.0",
"dns": "172.30.0.34",
"gateway": "172.30.0.33",
"netmask": "255.255.255.224",
"binariesUrl": "http://172.31.0.34/binaries/",
"scriptsUrl": "http://172.31.0.34/binaries/scripts/",
"toolsUrl": "http://172.31.0.34/binaries/tools/",
"network": {"vcenterIp": "172.30.0.50", "opsIp": "172.30.0.51", "mgmtVlan": 1610, "vmotionVlan": 1611, "vsanVlan": 1612, "vmotionGateway": "172.30.0.65", "vsanGateway": "172.30.0.97", "hosts": [...]},
"vcsaPassword": "***",
"vcsaSize": "small",
"vcsaFolder": "vcenter/9.1.0.0200-25573614/ovf/",
"vcsaSparseFolder": "vcenter/9.1.0.0200-25573614/sparse/",
```

Every value in it came from one of the two groups or from the request. The
check script ends by searching the jump host's files for `${`, which would
mean a reference the platform never resolved:

```text
no unresolved references in the jump host files
```

The build log shows the script working from that plan:

```text
09:34:34  === lab vCenter build starting (zone acme.lab) ===
09:35:25  ready: esxi 172.30.0.40
...
09:37:48  configuring vmkernel ports on 172.30.0.40
09:37:50    VM Network port group tagged VLAN 1610
...
09:38:06  bootstrapping vSAN ESA on 172.30.0.40
09:38:18    created a new single-node vSAN ESA cluster
```

The vCenter build needed two fixes before it finished, both in the build
script rather than the catalog, and both worth a post of their own: a PowerCLI
connection that hangs, and hosts that joined vSAN on the wrong network. The
final run ended at 12:26 with the lab's vCenter, four hosts, a 399 GB vSAN ESA
datastore, the distributed switch and the binaries share mounted over NFS.
Twenty minutes later the whole set went out as version 2.0.0.

## Why this matters outside the lab

A catalog is a product. The first version usually hard-codes the platform it
was built on, and that is fine until a second platform, a second team or a
second release arrives. Separating "what the lab is" from "where it runs" and
"which software it runs" turns a copy-and-edit exercise into two data changes,
with an audit trail in one YAML file. The same pattern fits any estate that
runs one service design on several VCF instances: regions, dev and prod, or a
disconnected site.

## Rules learned

- Blueprint validation skips expressions. Prove each construct with a
  throw-away deployment before building on it.
- Property-group values keep their JSON types: numbers do arithmetic, and an
  integer lands as an integer.
- Index a map by an input for choices like releases:
  `propgroup.<group>.releases[input.release].<key>`.
- Input lists and descriptions cannot hold expressions. Keep their text
  generic, or regenerate when it changes.
- Make the groups organization-wide, so every project's copy of an item can
  read them.
- Put a lint in the generator. Portability that is not checked erodes.

## Broadcom documentation

- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): input and constant property groups, shared with the organization or kept to one project
- [Constant Property Groups in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups/constant-property-groups-in-vcf-automation-for-all-apps.html): constant values that blueprints read through the `propgroup` binding
- [Expression syntax in VCF Automation for VM Apps](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/vcfa-overview/working-with-the-vcf-automation-catalog/maphead-designing-your-deployments/expressions-general/expressions-syntax.html): arithmetic, the `[ ]` operator, conditionals and functions, documented in the VM Apps guide
- [Versioning Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html): blueprint versions and releasing one to the catalog
- [Sample Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html): `CCI.Supervisor.Namespace` with `className`, `regionName` and `vpcName`

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
