---
title: "VM Apps vs All Apps: a field comparison of VCF Automation's two provisioning models"
date: 2026-09-16T07:00:00+01:00
lastmod: 2026-10-01
draft: false
tags: [vcf, vcf-automation, all-apps, vm-apps, aria-automation, architecture]
products: ["VCF Automation"]
tldr:
  - "VCF Automation 9.1 has two models: VM Apps is classic Aria Automation, and All Apps looks like Kubernetes because it is."
  - "All Apps makes identical isolated environments and nested ESXi natural; VM Apps still wins on vRO, ABX and deep vCenter work."
  - "Default to All Apps for new build-outs, keep VM Apps alongside for existing content, and script the ordering rules once."
tested: "VCF 9.1"
cover:
  image: "/images/post9-hero-vmapps-allapps.svg"
  alt: "Two provisioning paths side by side: IaaS engine to vCenter, vs blueprint to supervisor reconciliation"
  hidden: false
summary: "VCF Automation 9.1 ships two provisioning architectures, as two types of org. I ran the same use cases through both — Linux and Windows VMs, ISO attach, multi-NIC, isolated pods, nested ESXi, shared services, a catalog item. The honest scorecard, and how each use case is actually achieved."
---

VCF Automation 9.1 has two ways to build things, side by side, as two types
of organisation. If you've come from Aria Automation, you'll recognise one
of them immediately. The other looks like Kubernetes because it *is*
Kubernetes.

Choosing between them isn't a matter of taste. They have genuinely
different shapes, and some use cases are natural in one and awkward in the
other.

I've now pushed the same list of requirements through both on a live VCF
9.1 lab. This is the comparison I wish I'd had at the start. Hindsight, as
usual, turned up late.

## The two shapes

![VM Apps: Org, Project, Cloud Zone, Cloud Account, profiles, Cloud Template, then the IaaS engine drives vCenter, imperatively, with state in the IaaS database. All Apps: Org, CCI Project, Region, VPC, Supervisor Namespace, blueprint, then Supervisor controllers reconcile, declaratively, with state in etcd](/images/diagrams/vm-apps-vs-all-apps.svg)
*The same request, brokered on the left and declared on the right. The text versions below carry the detail.*

**VM Apps**, the classic Aria Automation model:

```
Org ─ Project ─ Cloud Zone(s)
                   │
        Cloud Account (vCenter / NSX)
                   │
   flavor · image · network · storage profiles
                   │
   Cloud Template (formatVersion 1) ──▶ IaaS engine ──▶ vCenter API
        Cloud.vSphere.Machine, Cloud.NSX.Network, customization spec
```

Provisioning is *imperative through a broker*. The IaaS engine holds the
vCenter session. The tenant references abstractions (flavors, image
mappings) that resolve at request time. State lives in the IaaS database.

**All Apps**, supervisor-native, through the Cloud Consumption Interface:

```
Org ─ CCI Project ─ Region
          │
   VPC (tenant-created; overlapping privateIPs allowed)
          │   + VPCAttachment   + LoadBalancer (before the namespace!)
   Supervisor Namespace (spec.vpcName pins it)
          │
   Kubernetes objects reconciled by the Supervisor:
     VirtualMachine / VirtualMachineService / Subnet / BindingMap / VKS Cluster
          │
   Blueprint (formatVersion 2, CCI.Supervisor.*) → BlueprintVersion → Catalog
```

Provisioning is *declarative*. The blueprint states the desired objects,
and the supervisor's controllers make reality match them and keep it that
way. State lives in etcd. Networking is NSX VPC-native.

## Scorecard by use case

Every row below was actually built, not read about. It's a slow way to fill
in a table, but an honest one.

| Use case | VM Apps | All Apps |
|---|---|---|
| Linux VM + software | `Cloud.vSphere.Machine` + cloudConfig | VM Service VM + cloud-init (typed field) |
| Windows VM | customization spec + software components | `bootstrap.sysprep`; ISO attachable declaratively |
| ISO / CD-ROM attach | day-2 edit in vCenter | `hardware.cdrom` in the manifest |
| Multi-NIC | NICs across network profiles | multiple `interfaces` on VPC subnets; failover verified |
| Self-service catalog | template released to catalog | blueprint → version → publish (one live version) |
| Load-balanced access | NSX LB via network profile | `VirtualMachineService` → VPC LB VIP |
| Kubernetes clusters | separate TKG integration | native `Cluster` object in the namespace |
| **Identical isolated environments** | hard: on-demand NAT nets, unique addressing usually forced | **natural**: VPC per pod, overlapping CIDRs, zero route between |
| **Nested ESXi / VLAN networks** | trunk portgroups on the physical vDS — a fabric change | **trunk subnet + binding maps** — no fabric change |
| Shared infra (WSUS, repos) | shared segment routed everywhere | one `PrivateTGW` subnet, one-way reachability |
| Extensibility | vRO, ABX, event broker (rich) | controllers, GitOps, kubectl (thinner day-2 today) |
| Deep per-device vSphere tuning | anything vCenter can do | what the VM Service API models |

The two bold rows are the ones that decided it for me. Both are
[documented](/posts/three-datacenters-one-ip-plan/) [in this
series](/posts/nested-esxi-nsx-vpc/). Both are genuinely hard in VM Apps,
and simply the default in All Apps.

## Where VM Apps still wins

Be fair to the incumbent:

- **Years of content.** vRO workflows, ABX actions, template libraries and
  a mature day-2 action framework carry over unchanged. If you have an
  estate of them, that's real value you'd be throwing away.
- **Deep vSphere reach.** Anything vCenter can do to a VM (RDMs, per-device
  tuning, exotic customization), the IaaS engine can do, because it drives
  vCenter directly.
- **Familiar network model.** Segments, portgroups, on-demand routed/NAT
  networks from a network profile. No new mental model.
- **Multi-cloud lineage.** The same template idiom stretched to other
  endpoints.

The [Windows Server 2025 pipeline](/series/the-windows-build-pipeline/)
elsewhere on this blog is a VM Apps build, and it's a good one. It has Event
Broker hooks for hostname allocation and placement metadata, cloudbase-init
staging, and a reboot-safe state machine in the guest. Nothing about it
needs rewriting, which, for a pipeline, is high praise.

## Where All Apps wins, and why it's structural

- **Declarative and self-healing.** Desired state lives in etcd, and
  controllers reconcile to it. There's no second database to drift from
  vCenter.
- **Structural multi-tenancy.** A VPC per tenant is a hard NSX boundary,
  not an administrative one. Overlapping CIDRs are *allowed*, so
  cookie-cutter environments deploy side by side.
- **VMs and Kubernetes are one model.** The same blueprint composes a VKS
  cluster, VMs, secrets and networking. It's GitOps-able with ordinary
  tools.
- **VPC networking is first-class.** Trunk subnets, binding maps,
  `PrivateTGW`, a per-VPC gateway firewall: none of it has a VM Apps
  equivalent.
- **Modern bootstrap.** cloud-init and sysprep as typed API fields.

## Where All Apps hurts today (all observed live)

- **Ordering matters, and the errors are opaque.** [The LB must exist
  before the namespace](/posts/the-lb-that-must-exist-first/). New
  namespaces reject VMs until images sync. Blueprint validation has
  [seven sharp edges](/posts/cci-blueprint-gotchas/), and I found every
  one of them by walking into it.
- **The tenancy layer is only partly blueprintable.** VPC and VPCAttachment
  have blueprint types (`CCI.VPC`, `CCI.VPC.Configuration`). But there's no
  LoadBalancer kind, and a blueprint-made VPC comes up with load balancing
  off. So all three go through the VPC API: scripted, not catalogued.
- **Two endpoints.** The CCI proxy serves tenancy objects, and workload
  manifests go to the supervisor. You'll hold two kubeconfigs.
- **Day-2 is thinner.** There's no event broker. Extensibility means
  controllers and GitOps, which is fine if that's your team and a gap if it
  isn't.

## Recommendation

Default to **All Apps** for new build-outs. Every use case on the list is
natural in the VPC model, including the two that are genuinely hard in VM
Apps. And the whole estate is version-controlled YAML.

Keep **VM Apps** as the compatibility surface for existing vRA content, and
for the rare thing that needs direct vCenter device manipulation. They
coexist as organisations of different types on one platform. So migration
is incremental, and nobody has to rewrite a working pipeline on a deadline.

And whichever you pick, **codify the ordering rules** into the scripts
that provision tenancy. The sharp edges stay wrapped up in there, and the
people requesting catalog items never meet them.

## Why this matters outside the lab

Most customers arriving at VCF 9 have an estate of Aria Automation content,
and a question: rewrite, coexist, or migrate? The answer above is the one
we take into design workshops.

In practice it starts with an assessment:

- which existing templates and workflows still earn their keep;
- which use cases are genuinely better served by the VPC model;
- where the boundaries sit.

Then comes a coexistence plan that moves workloads across
opportunistically, not on a deadline. What makes that low-risk is the two
architectures sharing one platform, as organisations of different types.

## Rules learned

- Two shapes, not two skins: imperative-through-a-broker vs
  declarative-reconciled. Pick per use case, not once for the estate.
- All Apps is structurally better at **isolation with identical
  addressing** and **nested/VLAN networks without fabric changes**.
- VM Apps is still the home for **existing vRO/ABX content** and
  **deep vCenter device work**.
- All Apps' pain is *ordering*, in this order: VPC, attachment, LB,
  namespace, subnets, image sync, then workloads. Script it once.
- They coexist, so migrate opportunistically.

## Broadcom documentation

- [Organization Management](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management.html): the two organization types in VCF Automation 9.1, All Apps and VM Apps
- [Bimodal Consumption Design for VM Apps and All Apps Workloads](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/design/design-library/vcf-automation-deployment-models-9-x/multi-tenancy-design-patterns/shared-tenancy-design.html): VM Apps and All Apps organizations on shared infrastructure, and a phased move between them
- [Sample Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html): All Apps blueprints built from `CCI.Supervisor.Namespace` and `CCI.Supervisor.Resource`
- [Deploying and Managing Virtual Machines in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane.html): the VM Service, its declarative API, VM classes and images
- [Managing Networking in VCF Automation Organizations](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/adding-and-managing-virtual-private-clouds.html): VPCs in an organization, whose private CIDRs need not be unique
- [vSphere resource examples in VCF Automation for VM Apps](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/vcfa-overview/working-with-the-vcf-automation-catalog/maphead-designing-your-deployments/other-code-examples/vsphere-resource-examples.html): VM Apps cloud templates built on `Cloud.vSphere.Machine`

---
*Lab environment; opinions my own. Grounded in a VCF 9.1 / vSphere
Supervisor with NSX VPC networking build-out; every row was deployed.*
