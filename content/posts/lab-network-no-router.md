---
title: "No VLANs to request, no router to run: the network inside a lab VPC"
date: 2026-11-11
draft: false
tags: [vcf, nsx, vpc, nested-esxi, vcf-automation, training-labs]
products: ["NSX", "VCF Automation"]
series: ["Nested Labs as Code"]
seriesPart: 3
cover:
  image: "/images/post36-hero-no-router.svg"
  alt: "A lab VPC whose gateway routes the management, vMotion and vSAN subnets that binding maps carry to the nested hosts' trunk, with the load balancer in front of the jump host and the transit gateway to the shared binaries server"
  hidden: false
summary: "Every lab in our catalog gets management, vMotion and vSAN networks, a way in, a way out and a route to a shared server, and nobody requests a VLAN or runs a router. The VPC gateway routes the lab's VLAN subnets, and NSX does the NAT, the load balancing and the addressing. How it is built, the receipts from f06, and a fair comparison with VLANs and with a router VM."
---

A student's jump host traced its route to the class's binaries server, which
lives in another VPC:

```text
Tracing route to 172.31.0.34 over a maximum of 8 hops
  1     1 ms    <1 ms    <1 ms  172.30.0.33
  2    <1 ms     1 ms     1 ms  100.64.0.16
  3    <1 ms    <1 ms    <1 ms  100.64.0.9
  4     2 ms     1 ms    <1 ms  172.31.0.34
Trace complete.
```

Three NSX hops and the server: the gateway of the lab's management subnet,
the transit gateway and the gateway of the shared-services VPC. The lab has
no router VM, and no physical switch carries a VLAN for it. Its management,
vMotion and vSAN networks are ordinary subnets of the lab's own VPC, and the
VPC routes them.

This is the network half of [the design](/posts/nested-labs-as-code/), and
how it compares with the other two ways to network a nested lab.

## One VPC per lab, one plan in every VPC

Every student has a VPC of their own, `vpc-student01` and so on, created once
with a load balancer and the same private range, `172.30.0.0/16`. A lab
request creates a Supervisor namespace pinned to that VPC and four subnets in
a fixed order, and a fresh VPC hands out /27 blocks in creation order, so
every lab gets the same plan
([three datacenters, one IP plan](/posts/three-datacenters-one-ip-plan/) has
the mechanism):

| Subnet | Block | Gateway | VLAN on the trunk | What uses it |
|---|---|---|---|---|
| sn-trunk | 172.30.0.0/27 | .1 | - | the nested hosts' vNICs, four per host |
| sn-mgmt | 172.30.0.32/27 | .33 | 1610 | dc01 .34, jump host .35, vmk0 .40-.43, vCenter .50, VCF Operations .51 |
| sn-vmotion | 172.30.0.64/27 | .65 | 1611 | vmk1 .70-.73 |
| sn-vsan | 172.30.0.96/27 | .97 | 1612 | vmk2 .100-.103 |

Class notes that say esx01 is 172.30.0.40 are right for every student; the
RDP address is the only one a student sees change from lab to lab.

## Three ordinary subnets on one trunk

A nested host's vNICs attach only to `sn-trunk`. The three networks a vSphere
host needs are ordinary `Private` VPC subnets, and a
[`SubnetConnectionBindingMap`](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kuberenetes-service-clusters-and-workloads/managing-networking-for-tkg-service-clusters/enable-antrea-egress-separate-subnet-on-a-tkg-cluster-with-nsx-vpc/create-a-subnetconnectionbindingmap-cr-on-the-supervisor.html)
binds each of them to the trunk with a VLAN tag. The nested hosts tag their
vmkernel traffic 1610, 1611 or 1612, as they would on a physical trunk, and
each binding map delivers its tag into its subnet.
[Nested ESXi inside an NSX VPC](/posts/nested-esxi-nsx-vpc/) explains why the
hosts need a trunk subnet rather than a plain one, and
[dual-NIC nested hosts](/posts/dual-nic-nested-hosts/) fails a vNIC over on it.

The generated blueprint creates all of this as plain Supervisor resources.
The management subnet, its binding map and the jump host's interface:

```yaml
  snMgmt:
    type: CCI.Supervisor.Resource
    dependsOn: [snTrunk]
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: crd.nsx.vmware.com/v1alpha1
        kind: Subnet
        metadata: {name: sn-mgmt}
        spec: {accessMode: Private, ipv4SubnetSize: 32}
...
  bmMgmt:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: crd.nsx.vmware.com/v1alpha1
        kind: SubnetConnectionBindingMap
        metadata: {name: bm-mgmt}
        spec: {subnetName: sn-mgmt, targetSubnetName: sn-trunk, vlanTrafficTag: '${propgroup.nestedLabSite.network.mgmt.vlan}'}
...
            interfaces:
              - name: eth0
                network: {apiVersion: crd.nsx.vmware.com/v1alpha1, kind: Subnet, name: sn-mgmt}
                addresses: ["${propgroup.nestedLabSite.network.jumpIp}/${propgroup.nestedLabSite.network.prefix}"]
                gateway4: ${propgroup.nestedLabSite.network.mgmt.gateway}
```

`dependsOn` fixes the creation order, and with it every address. The VLAN
tags and the addresses come from the site's property group, so the blueprint
carries no address or VLAN of its own. The jump host and `dc01` are ordinary
VMs on `sn-mgmt`: VM Operator asks NSX for their fixed addresses, .35 and
.34, and hands them the gateway, because
[our VPC subnets have no DHCP](/posts/vpc-subnets-have-no-dhcp/).

## The gateway is the VPC's own router

Nothing in the blueprint creates a router. Each subnet's gateway is an
interface of the VPC gateway, which NSX runs as a distributed router in every
host's kernel plus a service router on an edge node for the NAT and the load
balancer (`DR-vpc-student02` and `SR-vpc-student02` on the edge). The service
router's interfaces hold the lab's four gateway addresses beside its uplink
to the transit gateway:

```text
...
  aa154637-32e3-47ff-a1ba-e6682d700e8d default--f06-vpc-student02-t1_lrp uplink 100.64.0.19/31;fc3c:246e:19e5:8c00::2/64(NA);fe80::50:56ff:fe56:4455/64(NA) mtu=1500
  ca116caf-e033-4e2f-92cf-7e37017924c7 sn-mgmt_98j70 downlink 172.30.0.33/27 mtu=1500
...
  d6ce23e4-8331-4444-9658-4e1b542e724d sn-trunk_98j70 downlink 172.30.0.1/27 mtu=1500
  1f849cd3-74e5-4065-ad2d-db7dd50f5f85 sn-vmotion_98j70 downlink 172.30.0.65/27 mtu=1500
  56129ec5-510c-40cf-869c-2ca57476e676 sn-vsan_98j70 downlink 172.30.0.97/27 mtu=1500
```

Traffic inside one network stays at layer 2 on its subnet. Traffic between
the lab's networks is routed by the distributed router on the host where it
starts, and traffic in and out passes the service router. No VM sits in the
path, and there is nothing in the lab to size, patch or recover from a
console.

## What NSX does for the lab

What NSX does for each lab, with nothing to configure per request:

**The way out.** Each student VPC is attached to the
[connectivity profile](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-vpc-connectivity-profile.html)
`default--f06`, which turns default SNAT on: every lab VPC gets an outbound
NAT rule that nobody wrote. NSX's view of a lab VPC and the shared-services
VPC:

```text
== shared-svc  private_ips=['172.30.0.0/16']  ...
   subnet sn-binaries_h989i  Private_TGW  ['172.31.0.32/27']
   NAT DEFAULT  SNAT   src=172.30.0.0/16      dst=None               -> 192.168.144.36 default-shared-svc-172_30_0_0_
== vpc-student02  private_ips=['172.30.0.0/16']  ...
   subnet sn-mgmt_p56fn      Private      ['172.30.0.32/27']
   subnet sn-trunk_p56fn     Private      ['172.30.0.0/27']
   subnet sn-vmotion_p56fn   Private      ['172.30.0.64/27']
   subnet sn-vsan_p56fn      Private      ['172.30.0.96/27']
   NAT DEFAULT  SNAT   src=172.30.0.0/16      dst=None               -> 192.168.144.8 default-vpc-student02-172_30_0
```

**The shared binaries server.** The build scripts, PowerCLI and the vCenter
and VCF Operations files sit on one server in `shared-svc`, on a `PrivateTGW`
subnet (`Private_TGW` above) that the transit gateway advertises to every lab
VPC: the route in the opening trace.
[Shared services for isolated tenants](/posts/shared-services-for-isolated-tenants/)
shows why the server cannot reach back into a lab.

**The way in.** The jump host is the lab's only door, published by the VPC's
load balancer through a `VirtualMachineService` of type `LoadBalancer`; a
deployment output gives the student the address as
`RDP to <address> as student`:

```yaml
        kind: VirtualMachineService
        metadata: {name: jump-access}
        spec:
          type: LoadBalancer
          selector: {app: jump}
          ports:
            - {name: rdp, port: 3389, targetPort: 3389, protocol: TCP}
```

What the Supervisor made of it in one lab:

```text
NAME                  TYPE           CLUSTER-IP    EXTERNAL-IP      PORT(S)    AGE   SELECTOR
service/jump-access   LoadBalancer   10.96.0.204   192.168.144.10   3389/TCP   40m   <none>

NAME                                                      TYPE           AGE
virtualmachineservice.vmoperator.vmware.com/jump-access   LoadBalancer   40m
```

The VPC's load balancer must predate the lab's namespace, which is why every
student VPC is created with one
([the load balancer that must exist first](/posts/the-lb-that-must-exist-first/)).

**Addresses.** NSX's IPAM hands out and records every VM port's address: the
fixed ones `dc01` and the jump host ask for, and one on `sn-trunk` for each of
the sixteen host vNICs. The fixed two, as the Supervisor lists their ports:

```text
NAME                          VIFID                                  IPADDRESS        MACADDRESS
dc01-student01-sn-mgmt-eth0   66313239-3765-4232-ad37-6134652d3433   172.30.0.34/27   04:50:56:00:30:00
jump-student01-sn-mgmt-eth0   34303932-3833-4561-ad31-6239332d3431   172.30.0.35/27   04:50:56:00:3c:00
```

**MAC learning.** A nested host sends from MAC addresses that are not its
vNIC's: its vmkernel ports and, later, the VMs it runs. The lab VPCs' own
[service profile](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-vpc-service-profile.html),
`lab-nested`, turns MAC learning on, so NSX learns those addresses behind each
trunk port instead of flooding their frames.

## Three ways to give nested hosts their VLANs

The two other ways each buy something real.

**VLANs from the provider.** The classic answer: VLANs for each lab, trunked
to the hosts as VLAN-backed port groups or connected into the VPC by the
provider. The lab gets real layer-2 networks that reach physical equipment.
Each new lab costs provider-side objects and switch changes, and identical
addresses need a routing domain per lab.

**A router VM in the lab.** Tom Fojta's
[Building Nested Labs in VCF Automation 9.1](https://fojta.wordpress.com/2026/05/12/building-nested-labs-in-vcf-automation-9-1/)
uses the same trunk subnet and binding maps and makes the other choice about
the gateway. His trunk and VLAN subnets are disconnected from it, and a VyOS
router in the lab, uplink on a private VPC subnet and downlink on the trunk,
routes between the VLANs and masquerades traffic out; a DNAT rule on the VPC
gateway reaches the router, which forwards SSH and RDP inward. The router is
the lab's to shape: custom routes, a simulated WAN link, a firewall between
the lab's networks. And because he captures the whole namespace as a
blueprint, everything set up by hand, router included, comes along. The
price is a router image to build (VyOS lacks VMware Tools, so his post
compiles an ISO with open-vm-tools), its configuration, a DNAT rule and a port
forward for each service, binding maps that the 9.1.0 capture leaves out and
that go back in by hand, and a VM in the path of every packet that leaves a
network.

Our subnets stay on the gateway. In the Subnet object that is one field,
`advancedConfig.connectivityState`, which his post sets to `Disconnected`.
Ours are left at the default:

```text
sn-mgmt spec: {"accessMode": "Private", "advancedConfig": {"connectivityState": "Connected", "staticIPAllocation": {"enabled": true}}, "ipv4SubnetSize": 32, ... status: {... "gatewayAddresses": ["172.30.0.33/27"], "networkAddresses": ["172.30.0.32/27"], ...}
```

![Left, a lab VPC whose gateway routes the three VLAN subnets bound to the hosts' trunk; right, VLAN subnets off the gateway behind a router VM](/images/lab-network-no-router-diagram.svg)

| | VLANs from the provider | A router VM in the lab | The VPC gateway (ours) |
|---|---|---|---|
| A new lab needs | VLANs, port groups, switch changes | a router VM and its configuration | a catalog request |
| Same addresses in every lab | with a routing domain per lab | yes | yes |
| Routing between the lab's networks | the physical network | the router VM | NSX, on every host |
| To build and keep | provider-side objects | a router image, DNAT per service | nothing per lab |
| Its strength | real layer 2, physical gear | any routing the lab wants | no VM in any path, labs from code |

What ours gives up is the other side of that row. The VPC routes every
network in the lab, vMotion and vSAN included, where a physical design might
keep those two unrouted. A lab has no routing of its own, no WAN link to
simulate and no firewall appliance between its networks, and nothing set up
by hand survives a rebuild, which is a new request. For a class that installs
ESXi, vCenter and VCF Operations, none of that is the lesson; for a class
about routing, the router VM is the better tool.

## Why this matters outside the lab

Self-service scales when the network comes with the platform. Every lab gets
routing, NAT, a published door, addresses and a path to shared services from
NSX, the same way every time, with nothing for a network team to change per
request and no appliance to patch, size or rescue. That fits any repeatable environment: training labs, team sandboxes,
upgrade rehearsals, proofs of concept.

Support stays simple too: one lab's network is checked with the platform's
own tools, not by reading one router's configuration among dozens. When an
environment exists to exercise routing, a router VM earns its place; when it
does not, the platform's routing takes a moving part out of every copy.

## Rules learned

- Let the VPC gateway route the lab's networks; put a VM in the path only
  when routing is the lesson.
- Attach nested hosts to a trunk subnet only, and give each vSphere network an
  ordinary `Private` subnet bound to the trunk by its VLAN tag.
- Create the subnets in a fixed order in a fresh VPC, and every lab gets the
  same plan.
- Give infrastructure VMs fixed addresses through VM Operator (`addresses`,
  `gateway4`), so NSX's IPAM, the README and the class notes agree.
- Put shared servers in their own VPC once, on a `PrivateTGW` subnet.
- Turn MAC learning on for VPCs that carry nested hosts.

## Broadcom documentation

- [Virtual Private Clouds Overview](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview.html):
  the subnet access modes, Private, Private - Transit Gateway and Public.
- [Create a SubnetConnectionBindingMap CR on the Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kuberenetes-service-clusters-and-workloads/managing-networking-for-tkg-service-clusters/enable-antrea-egress-separate-subnet-on-a-tkg-cluster-with-nsx-vpc/create-a-subnetconnectionbindingmap-cr-on-the-supervisor.html):
  the binding map and its VLAN tag, shown for VKS egress subnets.
- [Add a VPC Connectivity Profile](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-vpc-connectivity-profile.html):
  the transit gateway, the service gateway and default outbound NAT.
- [Transit Gateways](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/transit-gateways.html):
  traffic between a tenant's VPCs, and out of the tenant.
- [Create a Virtual Private Cloud in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/adding-and-managing-virtual-private-clouds/add-a-vpc.html):
  a VPC in an organization, its private CIDRs and its load balancing toggle.
- [Extending VPC Subnet to VLAN and Onboarding DVPG VMs to VPC Subnets](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/extending-vpc-subnet-to-vlan-and-onboarding-dvpg-vms-to-vpc-subnets.html):
  the provider-side way to VLANs from the comparison above.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
