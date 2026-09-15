---
title: "Three datacenters, one IP plan: identical isolated pods with NSX VPCs"
date: 2026-10-13
draft: false
tags: [vcf, nsx, vpc, nested-esxi, multi-tenancy, training-labs]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/post4-hero-pods.svg"
  alt: "Three VPC pods with byte-identical addressing and no route between them"
  hidden: false
summary: "Three nested-ESXi pods, byte-identical addressing — same subnets, same VLANs, same host IPs, even the same MACs — with zero reachability between them. How overlapping VPC CIDRs and deterministic subnet realization turn cookie-cutter environments into a first-class feature."
---

Here are three hosts, all answering to `vmk0 = 172.30.0.40`:

```
ssh root@192.168.144.30  ->  [root@esx01-a:~]  vmk0  172.30.0.40
ssh root@192.168.144.32  ->  [root@esx01-b:~]  vmk0  172.30.0.40
ssh root@192.168.144.34  ->  [root@esx01-c:~]  vmk0  172.30.0.40
```

Same IP. Same VLAN. Same gateway. Same *MAC address*, as it turns out. And
none of them can reach any of the others. This is the post where NSX VPCs
stop being a workaround for nested labs and become genuinely better than
the physical alternative.

![Three pods, identical IP plans, no route between them](/images/product-01-hook.jpg)

## Why identical addressing matters

If you've ever built training pods, cert-study labs, or per-team
reproduction environments, you know the pain: every copy needs a unique
address plan, so every runbook, every screenshot, every "type this exact
command" has to be parameterised per pod. Students in seat 7 see different
numbers from the slides. Reproductions drift from the original.

The fix is obvious and normally impossible: **give every pod the same
addresses**. On a physical fabric that means VRFs, per-pod NAT, and a
network team that stops answering your emails. In an NSX VPC it's the
default behaviour.

## The mechanism: overlapping privateIPs

Each pod gets its own VPC, and every VPC declares the same private range:

```yaml
apiVersion: vpc.nsx.vmware.com/v1alpha1
kind: VPC
metadata: {name: nested-vpc-a}      # then -b, then -c
spec:
  privateIPs: ["172.30.0.0/16"]      # identical in all three
```

A `Private` subnet is never advertised beyond its VPC, so NSX has no
objection to three VPCs carving up the same /16. The pods aren't
"firewalled from each other" — there is simply no route between them.
Isolation by construction, not by policy.

![NSX: four VPCs, four sn-mgmt subnets, same CIDR](/images/ui/u11a-nsx-snmgmt-four-vpcs.jpg)
*NSX's subnet view filtered to `sn-mgmt`: four rows, four VPCs, one CIDR.*

## The trick: deterministic realization

Identical *ranges* aren't enough — I want identical *subnets*, so the
management gateway is `.33` and the hosts are `.40`/`.41` in every pod.
NSX allocates subnets from `privateIPs` in creation order, and a fresh VPC
allocates deterministically. So the topology is applied in a **fixed
order** — trunk, mgmt, vMotion, vSAN — and every pod realizes the same
map:

| Subnet | Realized | VLAN | Hosts |
|---|---|---|---|
| sn-trunk | 172.30.0.0/27 | — | (carries the tags) |
| sn-mgmt | 172.30.0.32/27 | 1610 | .40 / .41, gw .33 |
| sn-vmotion | 172.30.0.64/27 | 1611 | .70 / .71, gw .65 |
| sn-vsan | 172.30.0.96/27 | 1612 | .100 / .101, gw .97 |

In the catalog blueprint that order is enforced with `dependsOn` between
the subnet resources — the one place a declarative tool needs to be told
about sequence. Skip it and two pods can come out with mgmt and vMotion
swapped, which works perfectly and confuses everyone.

![NSX: nested-vpc-a expanded, the /16 private block](/images/ui/u11-nsx-vpc-a-cidr.jpg)

## The door: one VIP per host

Each pod is unreachable from outside by design, so each host gets a
`VirtualMachineService` of type `LoadBalancer` publishing SSH and HTTPS.
The VIPs come from the org's *external* block, and they're the only
addresses that differ between pods:

| Pod | VPC | esx01 VIP | esx02 VIP |
|---|---|---|---|
| a | nested-vpc-a | 192.168.144.30 | .31 |
| b | nested-vpc-b | 192.168.144.32 | .33 |
| c | nested-vpc-c | 192.168.144.34 | .35 |

Which is how the opening transcript works: three VIPs, three hosts, one
inside address.

## Proving the isolation

Claims are cheap. The test matrix, from a VM in a *fourth* VPC (the org
default):

```
ping 172.30.0.140 (own VPC)....... REACHABLE
ping 172.30.0.40  (pod space)..... unreachable
curl http://172.31.0.2/ (shared).. shared-svc repo01
```

![Isolation matrix: own-VPC reachable, pod space unreachable, shared service reachable](/images/demo-c7-isolation.jpg)

Its own VPC's `172.30.0.140`: reachable. `172.30.0.40` — an address that
exists in three other VPCs simultaneously: unreachable, because from here
there is no such route. (The third line is the shared-services VPC, which
is [the next post](/series/the-vpc-pod-papers/).)

Inside each pod, east-west is normal: `esx01 → esx02` vmkping passes on
all three VLANs, in all three pods. And the detail I didn't expect: the
nested-ESXi appliance derives vmk0's MAC deterministically from its
config, so **the three hosts share a MAC as well as an IP**. Harmless — each
VPC is its own L2 domain — but a nice demonstration of how complete the
separation is.

## What this replaces

| | Physical / VLAN-based pods | VPC pods |
|---|---|---|
| Identical addressing | VRF per pod + NAT, fabric change per pod | default behaviour |
| Adding a pod | switch config, IPAM, firewall rules | one API call for the VPC, one blueprint request |
| Isolation guarantee | policy (auditable, breakable) | topology (no route exists) |
| Tenant self-service | no | yes — the VPC is a tenant object |

## Rules learned

- Overlapping `privateIPs` across VPCs is **supported and intentional**.
  Identical pods are a feature, not a hack.
- Fresh VPCs realize subnets **deterministically in creation order** —
  fix the order (`dependsOn` in a blueprint) and every pod gets the same
  map.
- Pods are unreachable from outside by construction; publish exactly what
  you mean to via `LoadBalancer` VIPs from the external block.
- Prove isolation from a *different* VPC, with a positive control (own
  VPC reachable) beside the negative.
- Expect duplicate MACs across pods from appliance images. It's fine.

*Previously: [the LB that must exist first](/posts/the-lb-that-must-exist-first/).
Next: one WSUS for pods that can't see each other.*

---
*Lab environment; opinions my own. Output captured live, trimmed for length,
never edited for outcome.*
