---
title: "Nested ESXi inside an NSX VPC: the trunk-subnet design"
date: 2026-09-16T08:20:00+01:00
draft: false
tags: [vcf, nsx, vpc, nested-esxi, homelab, vsphere-supervisor]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/post1-hero-trunk.svg"
  alt: "The trunk-subnet design: one trunk vNIC, binding maps demux VLANs 1610/1611/1612 into VPC subnets"
  hidden: false
summary: "Plain VPC subnets silently blackhole a nested ESXi host. Here's why — and the trunk subnet + binding map design that makes nested labs work as an ordinary NSX VPC tenant, verified end to end."
---

The host booted clean. Management IP configured, services up, DCUI happy.
And every single packet it sent — ARP included — died silently.

That's how my first attempt at running nested ESXi inside an NSX VPC ended,
and the failure mode is nasty precisely because nothing *looks* wrong. If
you're trying to build nested vSphere labs on VCF 9 with VPC networking,
this post is the map of the minefield — and the design that gets you across
it, verified live.

## The setup

VCF 9.1, vSphere Supervisor with NSX VPC networking. The goal: deploy nested
ESXi hosts as ordinary VM Service VMs inside a tenant's VPC — no physical
fabric changes, no provider tickets, no special treatment. The kind of thing
you want for training pods, cert-study labs, or reproducing customer issues.

Nested ESXi needs what physical ESXi needs: a management network, vMotion,
vSAN — traditionally VLANs trunked to every host. But a VPC is an overlay
world. There are no VLANs to trunk. So what happens if you just attach the
nested host's vNIC to a normal VPC subnet?

## Failure #1: the silent blackhole

Here's the trap. A standard VPC subnet port gets **address bindings**: NSX
pins the exact IP + MAC it allocated to that vNIC, and SpoofGuard drops
everything else.

ESXi's vmk0 doesn't use the vNIC's MAC. It synthesises its own:

```
vmk0
   MAC Address: 00:50:ac:1e:00:8c     <- NOT the vNIC MAC (04:50:56:...)
```

So every frame the management interface sends carries a MAC the port doesn't
own. NSX drops it all — ARP, ping, everything — while the host itself boots
green and reports healthy. There is no error anywhere. You just can't reach
it, ever.

![Standard VPC subnet port: SpoofGuard pins one IP+MAC; vmk0's synthesised MAC loses, silently](/images/post1-blackhole.svg)

(There's a second trap stacked on top: VPC subnets run with DHCP deactivated,
so the appliance also sits at "waiting for DHCP" unless you inject static
addressing via OVF `guestinfo.*` properties. More on that below.)

## The design that works: a trunk subnet + binding maps

The fix isn't a hack — it's a first-class NSX VPC construct that's barely
documented in the wild: **`SubnetConnectionBindingMap`**.

The idea:

1. Create one ordinary VPC subnet to act as a **trunk** (`sn-trunk`). The
   nested host's vNICs attach *only* here.
2. Create a normal VPC subnet per traditional network — `sn-mgmt`,
   `sn-vmotion`, `sn-vsan`.
3. Bind each of those to the trunk with a **binding map carrying a VLAN tag**.
   The nested host's vSwitch tags frames exactly as it would on metal; the
   binding map strips the tag and delivers the frame into the right subnet.

Pure L2 demultiplexing. One vNIC carries N VLANs, the VPC never routes on a
tag, and the physical fabric never sees any of it (the 802.1Q header rides
inside the Geneve overlay).

All of it is tenant-creatable through the supervisor as Kubernetes objects:

```yaml
# sn-trunk and sn-mgmt are ordinary Private Subnets; the interesting object:
apiVersion: crd.nsx.vmware.com/v1alpha1
kind: SubnetConnectionBindingMap
metadata: {name: bm-mgmt}
spec:
  subnetName: sn-mgmt          # the map is a child of the VLAN subnet...
  targetSubnetName: sn-trunk   # ...and points AT the trunk
  vlanTrafficTag: 1610
```

That direction is easy to invert, so it's worth saying twice: **the binding
map belongs to the VLAN subnet and points at the trunk**, not the other way
round.

![NSX: sn-trunk realized once per VPC, binding maps hanging off the VLAN subnets](/images/ui/u11b-nsx-sntrunk-per-vpc.jpg)

On the nested host, nothing exotic — plain VST, like physical:

```
Name                Virtual Switch  Active Clients  VLAN ID
------------------  --------------  --------------  -------
Management Network  vSwitch0                     1     1610
vMotion             vSwitch0                     1     1611
vSAN                vSwitch0                     1     1612
```

![Host Client: port groups on VLANs 1610 / 1611 / 1612](/images/ui/u12a-hostclient-portgroups-vlans.jpg)
*The same three VLANs as the nested host sees them.*

And because there's no DHCP in a VPC subnet, the nested-ESXi appliance gets
its identity through OVF properties in the VM Service spec:

```yaml
bootstrap:
  vAppConfig:
    properties:
      - {key: guestinfo.ipaddress, value: {value: "172.30.0.40"}}
      - {key: guestinfo.netmask,   value: {value: "255.255.255.224"}}
      - {key: guestinfo.gateway,   value: {value: "172.30.0.33"}}
      - {key: guestinfo.vlan,     value: {value: "1610"}}
```

## Does it actually work? The receipts

Two nested hosts, vNICs on `sn-trunk`, three VLANs. From host one:

```
[root@esx01:~] vmkping -c2 172.30.0.41            # mgmt, VLAN 1610
3 packets transmitted, 3 packets received, 0% packet loss
[root@esx01:~] vmkping -I vmk1 -c3 172.30.0.71    # vMotion, VLAN 1611
3 packets transmitted, 3 packets received, 0% packet loss
[root@esx01:~] vmkping -I vmk2 -c3 172.30.0.101   # vSAN, VLAN 1612
3 packets transmitted, 3 packets received, 0% packet loss
```

![Live capture: vmnic0 down, vMotion and vSAN VLANs still passing at 0% loss](/images/demo-c6-nic-failover.jpg)
*The transcript that matters: fail the first NIC, and every VLAN keeps flowing on the second — captured live.*

Two more results worth knowing before you design around this:

**Untagged frames are dropped.** I put a probe vmk on the untagged
portgroup using the address NSX itself had allocated to the trunk port:
100% loss, empty ARP table, while tagged traffic flowed happily beside it.
Every network your nested host uses needs a VLAN and a binding map — there
is no untagged fallback.

**Failover behaves like real hardware.** With two vNICs on the trunk teamed
active/active, `esxcli network nic down -n vmnic0` moved every VLAN onto
vmnic1 with zero loss — and the SSH session I was watching from never
dropped. The vmk MAC migrating between trunk ports mid-flow is exactly the
scenario that MAC-pinned standard ports would blackhole; the trunk carries
it fine.

## Why this matters outside the lab

Running whole vSphere environments *inside* a VPC turns the platform into
something most customers never had: a way to stand up complete, isolated
copies of infrastructure on demand, without a physical fabric change and
without waiting for anyone. That's what makes it commercially interesting:

- **Training and certification labs** where every learner gets a real
  vSphere environment, not a shared one.
- **Reproducing a customer problem** on a like-for-like copy instead of on
  the customer's estate.
- **Rehearsing upgrades and migrations** end to end before the change
  window, then throwing the copy away.
- **Vendor and feature evaluations** with real behaviour, at zero risk to
  production.

This is the design Comms-care uses to give every consultant a dedicated
environment, and the same pattern scales to a classroom or a proof-of-concept
factory.

## Rules learned

- A nested ESXi vNIC on a **standard** VPC subnet is dead on arrival:
  vmk0's synthesised MAC loses to SpoofGuard, silently.
- Attach nested-host vNICs **only to a trunk subnet**; one binding map per
  VLAN; the map lives under the VLAN subnet and points at the trunk.
- **No DHCP in VPC subnets** — bootstrap addressing via `guestinfo.*`
  (appliances) or cloud-init (Linux). Static IP plans are a feature in a
  lab anyway.
- ESXi's default TCP/IP stack has **one** gateway — set per-vmk override
  gateways (`esxcli ... ipv4 set -g`) so vMotion/vSAN carry their own
  subnet's gateway.
- Recreating a VM **reallocates** its NSX addresses. Pin what you depend on.
- MTU: everything here ran at 1500. Raise the trunk and the nested vDS
  before you do vSAN at any real scale.

Next in this series: what happens when you want *ten* of these labs — with
byte-identical IP plans, firewalled from each other by construction. That's
where NSX VPCs go from "workaround" to genuinely better than physical.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment — output trimmed for length, never edited for outcome.*
