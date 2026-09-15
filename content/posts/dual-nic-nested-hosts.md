---
title: "Dual-NIC nested hosts: what redundancy means when the fabric is virtual"
date: 2026-11-24
draft: false
tags: [vcf, nested-esxi, nsx, vpc, networking, vsphere]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/product-03-failover.jpg"
  alt: "Fail a NIC. Nothing blinks."
  hidden: false
summary: "VCF wants two pNICs per host. In a nested lab the second vNIC adds no physical redundancy — so why add it? Because bringup validation and uplink teaming expect it, and because the failover test tells you something real about the trunk. vmnic0 down, 0% loss, and the SSH session watching it never dropped."
---

"Naturally, a VCF host has at least two NICs. Are we testing that, or have
you virtualised it away?"

Fair question, and the honest answer has two halves. In a nested lab the
*physical* redundancy is provided by the outer host — its vDS, its NSX
uplinks — and a second vNIC on the nested VM adds precisely none. But VCF
doesn't know it's nested. Bringup's host validation and the vDS uplink
teaming it configures **expect two vmnics**, and a host with one gets
flagged. So the nested hosts get two vNICs, both on the trunk subnet, and
the question becomes: does failover between them actually work inside a
VPC?

## The setup

Both vNICs attach to the same `sn-trunk` subnet — [the trunk from part
1](/posts/nested-esxi-nsx-vpc/) — and ESXi sees them as two 10G vmnics:

![Host Client: vmnic0 and vmnic1, both 10 Gbit/s on vSwitch0](/images/ui/u13-hostclient-dual-nics.jpg)

vSwitch0 teams them active/active with the default originating-port-ID
policy; every portgroup (Management 1610, vMotion 1611, vSAN 1612) inherits
it. Nothing you wouldn't do on metal.

## The test: pull a NIC while watching from inside

The interesting bit isn't whether pings continue — it's *which* session
I'm watching from. I'm SSH'd to `esx01` **through its public VIP**, which
means my session traverses the NSX LB → the VPC → the trunk port → whichever
vmnic happens to carry vmk0. If failover breaks anything, it breaks the
terminal I'm typing in.

```
[root@esx01-a:~] esxcli network nic list
Name    ...  Admin Status  Link Status  Speed  MAC Address
vmnic0  ...  Up            Up           10000  04:50:56:00:5c:03
vmnic1  ...  Up            Up           10000  04:50:56:00:68:00

[root@esx01-a:~] esxcli network nic down -n vmnic0    # FAIL THE FIRST NIC
vmnic0  ...  Down          Down             0  04:50:56:00:5c:03
vmnic1  ...  Up            Up           10000  04:50:56:00:68:00

[root@esx01-a:~] vmkping -I vmk1 172.30.0.71          # vMotion VLAN, now over vmnic1
3 packets transmitted, 3 packets received, 0% packet loss

[root@esx01-a:~] vmkping -I vmk2 172.30.0.101         # vSAN VLAN, now over vmnic1
3 packets transmitted, 3 packets received, 0% packet loss

[root@esx01-a:~] esxcli network nic up -n vmnic0      # restore
# session never dropped.
```

![Before / after: vmnic0 down, every VLAN still passing](/images/c6-nic-failover-beforeafter.gif)

![Full failover transcript](/images/demo-c6-nic-failover.jpg)

Every VLAN moved to vmnic1. Zero loss on vMotion and vSAN. And the
management session — the one *most* likely to notice — never blinked.


## Why this is a real result, not a party trick

Think about what just happened at the NSX layer. vmk0's MAC — a MAC ESXi
synthesised, not the vNIC's — was being learned on trunk port A. When
vmnic0 went down, the same MAC appeared on trunk port B mid-flow, with an
established TCP session riding on it.

On a **standard** VPC subnet port that is exactly the scenario SpoofGuard
exists to stop: the port's address bindings pin one MAC, and a frame from a
different MAC — or the *same* MAC arriving on a different port — is dropped.
Part 1 showed that killing the host on a standard subnet before it ever
spoke. This test shows the trunk subnet tolerating the live migration of a
foreign MAC between two of its ports, which is the property nested vSphere
(and anything else with a vSwitch inside a VM) fundamentally needs.

So the second vNIC buys three things, none of them physical redundancy:

1. **Bringup and vLCM stop complaining** about a single-uplink host.
2. **The teaming policy you'll configure in production gets exercised** —
   uplink failover, active/standby for vSAN, whatever you're rehearsing.
3. **A live proof that the trunk carries MAC mobility**, which is the
   real assurance that the design isn't relying on a quiet network.

## What it does *not* buy, and how to say so

If someone asks "is this host redundant?", the answer is "the nested host
believes it is; actual redundancy lives one layer down." In a training pod
that's the correct and useful answer — students configure and test failover
exactly as they would on metal, and the outer platform does the real work.
In a reproduction lab for a customer NIC-teaming issue, it's usually enough
too: most teaming bugs are in ESXi's policy handling, not in the copper.

Where it's genuinely insufficient: anything about physical link behaviour —
LACP negotiation, LLDP, flapping, MTU mismatch on one uplink. The virtual
fabric never fails asymmetrically, so it can't reproduce those.

## Rules learned

- Give nested VCF hosts **two vNICs on the same trunk subnet**. Bringup,
  vLCM and vDS teaming expect ≥ 2 vmnics; humouring them costs nothing.
- Test failover **from a session that depends on it** (SSH via the VIP).
  Pings passing while your terminal dies is not success.
- The trunk subnet tolerates a **vmk MAC moving between ports mid-flow**
  — that's the property standard subnets lack and nested vSphere needs.
- Be precise in the write-up: nested dual-NIC gives *policy* realism, not
  *physical* redundancy. Physical link faults can't be reproduced here.
- Rebuilds re-run the vmk config: the appliance creates vmk0 only;
  vmk1/vmk2, their VLANs and override gateways are applied post-boot.

*Companion to [nested ESXi inside an NSX VPC](/posts/nested-esxi-nsx-vpc/).*

---
*Lab environment; opinions my own. Output captured live, trimmed for length,
never edited for outcome.*
