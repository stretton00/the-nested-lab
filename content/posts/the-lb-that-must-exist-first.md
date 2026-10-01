---
title: "The load balancer that must exist before the namespace"
date: 2026-09-16T08:10:00+01:00
lastmod: 2026-10-01
draft: false
tags: [vcf, nsx, vpc, supervisor, ncp, troubleshooting]
products: ["NSX", "vSphere and vSAN"]
series: ["The VPC Pod Papers"]
seriesPart: 3
tldr:
  - "In our self-service NSX VPC, the LoadBalancer services sat at `<pending>` for an hour, explained only by a 'Generic error'."
  - "NCP looks for the VPC's load balancer once, when the namespace is created, and never again, however long you wait."
  - "Create the VPC, the VPCAttachment and the LoadBalancer before the namespace, or the only tenant fix is recreating the namespace."
tested: "VCF 9.1"
cover:
  image: "/images/post2-hero-ordering.svg"
  alt: "The ordering rule: VPC, VPCAttachment, LoadBalancer, then the namespace - swap steps 3 and 4 and VIPs pend forever"
  hidden: false
summary: "VIPs pending forever, a retryable error that never stops retrying, and an ordering rule the docs don't tell you: in a self-service NSX VPC, the LBService must exist before the namespace that will use it."
---

Everything was green. The VPC: realized. The namespace: ready. The VMs:
powered on, endpoints populated, ports listening. And the LoadBalancer
services sat at `<pending>` — for an hour.

This is the story of the least helpful error message in my recent memory,
what it actually means, and the one-line ordering rule that would have saved
an afternoon. If you're doing self-service NSX VPCs on VCF 9 with the
vSphere Supervisor, you will hit this. Bookmark accordingly.

## The setup

Tenant-created VPC (via the VCF Automation CCI API), a supervisor namespace
pinned to it, and a couple of `VirtualMachineService` objects of type
`LoadBalancer` to publish SSH and HTTPS for the workloads inside. Standard
stuff — the exact pattern that works out of the box in the org's default VPC.

The k8s side looked perfect:

```
$ kubectl get endpoints -n pod-a
NAME           ENDPOINTS                        AGE
esx01-access   172.30.0.40:443,172.30.0.40:22   6m36s
esx02-access   172.30.0.41:443,172.30.0.41:22   6m35s
```

Endpoints resolved. VIPs: nothing. The only clue, a recurring event:

```
Warning  FailedRealizeNSXResource  service/esx01-access
Generic error occurred during realizing network for Service
```

"Generic error." Wonderful.

## Digging: what NCP actually wants

The supervisor's network container plugin (NCP) logs told the real story:

```
nsx_ujo.ncp.nsx.policy.lb_layer4_service Lb Service not Found for Namespace pod-a
NCP00270 Failed to process virtual ip for service ...: Lbs pod-a is not found
Encountered retryable error ... : Lbs pod-a is not found
```

NCP wants an NSX **LBService** in the namespace's VPC. In the org's
*default* VPC, one exists — the platform created it when the VPC was born.
In my self-service VPC? Nobody had created one. Fair enough — that's
actually documented behaviour once you know where to look: a fresh VPC needs
a `LoadBalancer` object (and before that, a `VPCAttachment` to a
connectivity profile with the service gateway enabled, or the LB creation
itself fails with a much better error message).

So I created the attachment, then the LBService. NSX: `Realized=True`.
Problem solved?

```
Warning  FailedRealizeNSXResource  service/esx01-access
Generic error occurred during realizing network for Service
```

No.

## The actual bug-shaped behaviour: a snapshot, not a lookup

Here's the part that costs you the afternoon. That "retryable error" retries
the *lookup in NCP's cache* — not the discovery. **NCP snapshots the VPC's
LB inventory when the namespace is created.** An LBService that appears
afterwards is never discovered, no matter how long you wait:

- Recreating the k8s services: no effect.
- Tagging the LBService with the `nsx-op/*` ownership tags the working ones
  carry: no effect — the cache doesn't re-read NSX.
- Restarting NCP would force a full resync — but supervisor system pods are
  protected; even `Administrator@vsphere.local` gets a Forbidden.
- Mutating the namespace to nudge a re-sync: also blocked, by the
  supervisor's namespace validation webhook.

As a tenant, there is exactly one fix: **delete and recreate the namespace**,
now that its VPC has an LB. Fifteen minutes of rebuild for want of one
ordering rule.

And the control experiment proves the rule: a namespace created *after* its
VPC already had an LBService got its VIPs assigned without any drama —

```
esx01-access   VIP=192.168.144.34   22 OPEN · 443 OPEN
esx02-access   VIP=192.168.144.35   22 OPEN · 443 OPEN
```

And once the ordering is right, this is what "working" looks like — the
pod's state a couple of minutes after a correctly-ordered deployment:

![Live replay: catalog-deployed pod with both VMs powered on and VIPs assigned](/images/c2-catalog-pod.gif)

![VCFA deployment topology: namespace, subnets, hosts, two VIPs](/images/ui/u4-deployment-topology.jpg)
*What the requester sees once the order is right.*

## The ordering rule

For every self-service VPC that will publish LoadBalancer services, create —
in this order, *before* the namespace:

```
1. VPC                                   (vpc.nsx.vmware.com/v1alpha1)
2. VPCAttachment                         (connectivity profile w/ service gateway
                                          — LB creation errors without it)
3. LoadBalancer   {regionName, vpcName}  (the step everyone misses)
4. ...and only THEN the Supervisor Namespace
```

Encode it in whatever provisions your VPCs — a script, a pipeline, an
operator. It's four API calls and it turns a silent, undiagnosable
`<pending>` into a platform that just works.

## Why this matters outside the lab

Nobody buys a platform for its ordering rules — but this is exactly the kind
of edge that decides whether self-service provisioning feels reliable or
flaky to the people using it. In a customer deployment the answer isn't a
blog post; it's that the provisioning automation already does the four
steps in the right order, every time, so a tenant never sees a VIP stuck at
`<pending>`. Knowing where the sharp edges are — because you've been cut by
them in a lab — is most of what an experienced delivery partner is for.

## Rules learned

- In a self-service NSX VPC, **the LBService must predate the namespace**.
  NCP discovers LBs at namespace-add and never again.
- `FailedRealizeNSXResource: Generic error` on a Service = go read the NCP
  logs; the real message (`Lbs <ns> is not found`, NCP00270) is there.
- `VPCAttachment` (service gateway) is the prerequisite for the LB itself —
  that one at least fails loudly.
- Retro-tagging NSX objects to look "owned" doesn't help a cache that never
  re-reads. Recreating the namespace is the only tenant-level fix.
- While you're at it: new namespaces also reject VM creation until image
  `status.disks` syncs (~1–3 minutes after content library attach). Build
  the wait into your automation and both sharp edges disappear.

## Broadcom documentation

- [Deploying Supervisor with VCF Networking with VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsphere-supervisor-installation-and-configuration/supervisor-networking-with-virtual-private-clouds.html): what NCP creates for a namespace given no VPC: a VPC with its load balancer and SNAT IP.
- [Create vSphere Namespaces on VPCs without SNAT and Load Balancer](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsphere-supervisor-installation-and-configuration/configuring-and-managing-vsphere-namespaces/managing-vsphere-namespaces-on-a-supervisor-with-nsx-vpc/create-and-configure-a-vsphere-namespace-on-a-supervisor-with-vpc/create-namespaces-with-vpc-nosnat-nolb.html): without the VPC's load balancer, LoadBalancer services and VirtualMachineServices cannot be deployed.
- [Add a VPC Connectivity Profile](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-vpc-connectivity-profile.html): the transit gateway, the service gateway and default outbound NAT.
- [Create and Configure a vSphere Namespace on a Supervisor with NSX VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsphere-supervisor-installation-and-configuration/configuring-and-managing-vsphere-namespaces/managing-vsphere-namespaces-on-a-supervisor-with-nsx-vpc/create-and-configure-a-vsphere-namespace-on-a-supervisor-with-vpc.html): placing a new namespace in an existing VPC.
- [Create a Virtual Private Cloud in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/adding-and-managing-virtual-private-clouds/add-a-vpc.html): a tenant VPC, its connectivity profile and its load balancing setting.
- [Sample Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html): a VPC, its VPCAttachment and a namespace that depends on them, as blueprint resources.

*Previously in this series: [nested ESXi inside an NSX VPC](/posts/nested-esxi-nsx-vpc/).
Next: three datacenters, one IP plan — identical isolated pods.*

---
*Lab environment; opinions my own. Output captured live, trimmed for length,
never edited for outcome.*
