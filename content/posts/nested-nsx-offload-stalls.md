---
title: "Ping works, TCP dies: two vmxnet3 offloads under a nested NSX pod"
date: 2026-12-16
draft: false
tags: [vcf, nsx, nested-esxi, vmxnet3, geneve, troubleshooting, homelab]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/post25-hero-offloads.svg"
  alt: "A nested ESXi host sends Geneve TSO super-frames the outer layer drops, and receives LRO-merged frames its driver rejects; the fix is encapOffload=0 rxInnerOffload=0 disableLRO=1"
  hidden: false
summary: "Tunnels up, BFD green, big don't-fragment pings fine - and bulk TCP across the overlay died per connection. Two offload faults between nested ESXi and the layer below, one in each direction, and the counter pair that found the second one in minutes."
---

Every tunnel was up. BFD was green, 1572-byte don't-fragment pings crossed the
overlay without complaint, the edges were healthy and the alarm list was
nearly empty. Meanwhile a download from the shared binaries server inside the
pod crawled at 2-15 MB/s, SFTP sessions reset halfway, a nested vCenter's
disk import took 64 minutes, and nested vSAN logged "Setting pulse failed".

This is how that looked from a test client on the morning I started
measuring properly: six paced connections to the same server, then one
stream that reconnects whenever it stalls:

```text
== baseline 10:10:46
conn 1: flowed 4.3 s then stalled after 42 MB
conn 2: dead from the start after 0 MB
conn 3: dead from the start after 0 MB
conn 4: dead from the start after 0 MB
conn 5: dead from the start after 0 MB
conn 6: dead from the start after 0 MB
1 stream(s), 64 s: 8.2 MB/s total; per stream MB: [522]; reconnects: [12]
```

It hit flows, not hosts. A retry often landed on a working path, so for days
it read as "the lab is a bit slow" rather than as an outage.

## The setup

The pod is a VCF 9.1 instance whose six ESXi hosts are themselves VMs on an
outer vSphere cluster. The pod runs NSX with VPCs, so traffic between its
workloads is Geneve-encapsulated by the nested hosts and then carried by the
outer layer: each nested host's vmxnet3 vNIC, a plain vSphere distributed
switch with MAC learning on the trunk port group, and Broadcom `bnxtnet` 10G
NICs. VCF 9.1 runs the nested NSX uplinks in Enhanced Datapath mode, so they
use the `nvmxnet3_ens` driver.

Two layers of virtual networking, each offering the other help with big
packets. That turned out to be the whole story, twice.

## Fault 1: the send side

`nvmxnet3_ens` has an `encapOffload` parameter that defaults to Auto: it takes
whatever the vmxnet3 device's backend recommends. The outer hosts recommended
Geneve offload, so every nested host activated `GENEVE_OFFLOAD` and
`TSO256k` on its uplinks. From then on a nested host handed each TCP burst to
its vNIC as one Geneve-encapsulated super-frame, 64 KB and more, and trusted
the layer below to cut it into MTU-sized frames.

Packet captures on both ends settled it. With `pktcap-uw` on the uplinks of
the server's host and the client's host, and a small parser to strip the
Geneve header, the server's data frames left at up to 9 KB and over 64 KB.
Only frames of 1,600 bytes or less arrived. The SYN-ACK always made it; the
data behind it did not. Small packets are never offloaded, which is why
pings, BFD and handshakes looked perfect.

Setting `encapOffload=0` and rebooting the host took the same copy between
the same two hosts from 2-15 MB/s to 235-273 MB/s. The reboot is not
optional: a runtime `Net.UseHwTSO=0` plus an uplink reset, tried first, did
nothing, because the Enhanced Datapath keeps its offload capabilities until
the driver reloads at boot.

I rolled the option to all six hosts and ran the full test set again:

```text
== outside, en02 active 14:22:30
conn 1: flowed 6.2 s then stalled after 61 MB
conn 2: dead from the start after 0 MB
conn 3: dead from the start after 0 MB
conn 4: dead from the start after 0 MB
conn 5: no stall in 25 s after 16 MB
conn 6: no stall in 25 s after 11 MB
4 stream(s), 23 s: 7.4 MB/s total; per stream MB: [170, 1, 0, 0]; reconnects: [4, 4, 4, 4]
```

Two of the six connections kept moving, at well under 1 MB/s. The other four
still died, and four parallel streams managed 7.4 MB/s between them.

## Fault 2: the receive side

The second fault only showed up once I stopped timing transfers and started
counting drops at both ends of the hop. The nested driver keeps per-queue
counters under `vsish`, and the outer distributed switch keeps per-port
counters for each vNIC. For one test, on the receiving nested host and on its
port on the outer switch:

```text
=== esx03 RX deltas
  vmnic0 Rx Errors                                 +267
  vmnic0 [rq0] pkts rx err                         +267
esx03 nic1  ... in 292408 pk 125.5 MB drop 1 | out 408391 pk 462.5 MB drop 267
```

267 packets dropped on the way out of the outer switch, 267 receive errors in
the nested driver. The next run was 590 and 590, the one after 430 and 430.
The counters matched one for one every time, which put the loss exactly on
the vNIC boundary.

The cause is LRO. The outer hosts merge consecutive TCP segments heading into
a VM (`Net.Vmxnet3HwLRO=1`, `Net.Vmxnet3SwLRO=1`) and skip that only for
promiscuous ports (`Net.VmxnetPromDisableLro=1`). The pod's trunk port group
uses MAC learning, not promiscuous mode, so its nested hosts get merged
frames. For plain TCP, such as vSAN or vMotion, the nested driver takes a
merged frame without complaint. A merged *Geneve* frame completes with an
error instead. The first one or two packets of a burst arrive before merging
starts; the rest is lost as one. A dead connection's first 16-17 data packets
left the server's host and two arrived, TCP backed off, and the flow looked
stalled.

The tests that pinned it down, each six downloads with both counters read
before and after:

| Test on the receiving host | Nested rx errors | Outer port drops | Downloads |
| --- | --- | --- | --- |
| Default (LRO on), 1,572-byte Geneve frames | 557-1,266 | same count | 3-5 of 6 dead |
| `rxInnerOffload=0` alone | 557 | 559 | 5 of 6 dead |
| Receive ring 512 / 2,048 / 4,096 | 430 / 267 / 590 | same count | stalled |
| Server MTU 1400 (1,472-byte frames) | 0 | 0 | clean |
| UDP, 1,572-byte frames in bursts of 16 | 0 | 0 | 4,800 datagrams |
| `disableLRO=1` | 0 | 0 | clean |

The UDP row is the tell. Same frame size, same burst pattern, zero errors,
because LRO only merges TCP. Whether the outer NIC or the outer kernel does
the merging, I never determined; the fix does not depend on it.

## The fix

Three options on both vmxnet3 drivers of every nested host that carries NSX
overlay traffic, then a reboot:

```bash
esxcli system module parameters set -m nvmxnet3_ens -p "encapOffload=0 rxInnerOffload=0 disableLRO=1"
esxcli system module parameters set -m nvmxnet3     -p "encapOffload=0 rxInnerOffload=0 disableLRO=1"
```

`encapOffload=0` keeps segmentation in the nested host; `disableLRO=1` stops
the outer layer handing it merged frames. `rxInnerOffload=0` was part of the
tested set, although on its own it changed nothing. `parameters set`
replaces the module's whole option string, so always send all three.

For hosts already in a vSAN cluster I went one at a time: set the options,
maintenance mode with "Ensure accessibility", save the config with
`auto-backup.sh`, then `reboot -f`. A graceful reboot of a nested host can
hang in the vSAN shutdown handler; in maintenance mode the forced reboot was
safe and the host was back in about two minutes. After boot, check that
`vsish -e get /net/pNics/vmnic0/properties` no longer lists
`GENEVE_OFFLOAD` as an activated hardware capability, and that
`pkts rx err` stays flat under load.

The same tests after all six hosts had the options:

```text
=== paced: 6 connections at 10 MB/s (19:43:49)
conn 1: no stall in 25 s after 249 MB
conn 2: no stall in 25 s after 250 MB
...
conn 6: no stall in 25 s after 250 MB
=== unpaced: 4 parallel streams for 20 s
4 stream(s), 20 s: 178.8 MB/s total; per stream MB: [842, 835, 1074, 828]; reconnects: [0, 0, 0, 0]
=== upload 400 MB through the edge to the binaries server
uploaded 400 MB in 7.1 s = 56.0 MB/s; writes that took >2 s: none
TOTAL (delta) rx 16382394, rx err 0, OOB 2565, LRO pkts 0
```

Zero receive errors in 16.4 million packets. The 2,565 left over are
receive-ring overruns on the host running the busy edge, the ordinary "host
briefly too busy" kind that TCP absorbs. The next full nested lab build
(hosts, vSAN, vCenter, VCF Operations) passed end to end in 3 hours 51
minutes.

There are outer-layer alternatives: turning LRO off on the outer hosts,
disabling Geneve offload in the outer NIC driver, or a promiscuous trunk.
Each would cover every pod at once, and each changes shared hosts, so the
per-host fix stays the recommendation until one of them is tested. The lab
build automation now sets the options on every new nested host, and reboots
it, before vSAN or vCenter exist.

## Why this matters outside the lab

Nested VCF pods are where teams rehearse upgrades, reproduce customer
problems and train people. When the overlay underneath quietly eats bulk TCP,
everything above it looks unreliable: vSAN heartbeats, appliance deploys,
backups, file copies. People then chase the wrong layer for days, because
every health check they know how to run is green.

The same class of fault appears wherever encapsulated traffic crosses a
virtual NIC that two layers of software both want to optimise: nested NSX,
overlays over overlays, tunnel endpoints inside VMs. The method carries over
too. Throughput tells you something is wrong; counters at both ends of each
hop tell you where.

## Rules learned

- Green tunnels, BFD and large don't-fragment pings prove nothing about bulk
  TCP. Offloads only touch large TCP.
- In a nested NSX pod, set `encapOffload=0 rxInnerOffload=0 disableLRO=1` on
  both vmxnet3 drivers of every nested host, then reboot. The drivers read the
  options only at load.
- `esxcli system module parameters set` replaces the whole option string.
  Send all three every time.
- Count, don't time. The nested `pkts rx err` (vsish, per receive queue)
  against the outer port's drops found the second fault in minutes. Refresh
  the port state before reading the outer counters, or you get cached zeros.
- A UDP burst at the same frame size is the cheapest discriminator: no errors
  with UDP means a TCP-only feature such as LRO or TSO, not the MTU or the
  fabric.
- Promiscuous mode or MAC learning on the outer trunk changes offload
  behaviour: the outer host disables LRO only for promiscuous ports.
- Read "Rx Missed" separately. Ring overruns are a different, milder problem,
  and they were not this one.

## Broadcom documentation

- [Configuring advanced driver module parameters in ESX/ESXi](https://knowledge.broadcom.com/external/article/310348/configuring-advanced-driver-module-param.html): new module options replace all existing ones, and take effect at boot.
- [What is Large Receive Offload](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/vsphere/9-1/vsphere-networking/managing-network-resources/large-receive-offload.html): LRO, on by default in the VMkernel and in VMXNET3 adapters.
- [Manage Hardware LRO for All VMXNET3 Adapters on an ESX Host](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/vsphere/9-1/vsphere-networking/managing-network-resources/large-receive-offload/enable-hardware-lro-for-all-vmxnet2-and-vmxnet3-adapters-on-a-host.html): the `Net.Vmxnet3HwLRO` setting.
- [Manage TSO on an ESX Host](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/vsphere/9-1/vsphere-networking/managing-network-resources/enabling-tso/enable-tso-on-an-esxi-host.html): `Net.UseHwTSO`, and reloading the NIC driver after a change.
- [Enhanced Data Path](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/host-switches/enhanced-datapath.html): EDP, enabled automatically in new VCF 9 workload domains.
- [What is MAC Learning Policy](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/vsphere/9-0/vsphere-networking/networking-policies/mac-learning-policy.html): MAC learning on distributed port groups, for nested hypervisors.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
