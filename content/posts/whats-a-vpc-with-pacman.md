---
title: "What's a VPC? Let Pac-Man explain"
date: 2026-09-16T08:30:00+01:00
lastmod: 2026-10-01
draft: false
tags: [vcf, nsx, vpc, vks, kubernetes, explainer]
products: ["NSX", "VKS"]
series: ["The VPC Pod Papers"]
seriesPart: 1
tldr:
  - "An NSX VPC is a tenant's own network, private by default, and two VPCs can even use identical CIDRs."
  - "Pac-Man shows it: make its service `ClusterIP` and the game vanishes from outside; make it `LoadBalancer` and the door reopens."
  - "But the game would not load: my own patch had replaced the ports array, and five green layers hid one wrong integer."
tested: "VCF 9.1"
cover:
  image: "/images/post0-hero-pacman.svg"
  alt: "Pac-Man inside a VPC boundary; a LoadBalancer VIP is the one door out"
  hidden: false
summary: "Part 0 of the Pod Papers: an NSX VPC explained with a running game. Private by default, one deliberate door out — and a self-inflicted outage that taught me five green layers can hide one wrong integer."
---

Before this series gets into trunk subnets and binding maps, it's worth ten
minutes on the thing everything else stands on: **what an NSX VPC actually
is**, seen from the tenant's chair. No slides, just a game of Pac-Man.
Strictly for educational purposes, you understand.

The lab has Pac-Man running twice on VCF 9.1. One copy runs on a VKS
(vSphere Kubernetes Service) cluster I built by hand with `kubectl`. The
other runs on a cluster deployed through VCF Automation's catalog. Both live
inside VPCs, and both were reachable when I started:

```
http://192.168.144.15/  ->  <title>Pacman in HTML 5 Canvas
http://192.168.144.23/  ->  <title>Pacman in HTML 5 Canvas
```

{{< video src="/images/pacman-vip-23.mp4" ratio="710 / 610" caption="Pac-Man, live at `192.168.144.23` — a VIP on the VPC load balancer. The only door in." >}}

## A VPC is a private universe with a door policy

Think of an NSX VPC as a tenant's own routed network space. It has its own
subnets, its own gateway and its own address plan. The tenant carves it out,
rather than filing a ticket with the network team. Three rules define it:

1. **Private by default.** A `Private` subnet is reachable only from inside
   the same VPC. Nobody outside can route to it: not other tenants, not
   other VPCs in the same org, not the corporate network.
2. **Your addresses are your business.** Private subnets aren't advertised
   anywhere, so two VPCs can use *identical* CIDRs. (This is the superpower
   the rest of the series is built on.)
3. **Every door out is deliberate.** Traffic leaves through the transit
   gateway (with source NAT), or arrives through a **LoadBalancer VIP** from
   an external block the provider allocated. Nothing is exposed by accident.

Pac-Man's pods sit on a private subnet. The only reason `192.168.144.23`
answers is a Kubernetes `Service` of type `LoadBalancer`, which NSX turns
into a VIP on the VPC's load balancer. So let's remove the door.

## Before: close the door

```
$ kubectl patch svc pacman -n pacman -p '{"spec":{"type":"ClusterIP"}}'
service/pacman patched
NAME     TYPE        CLUSTER-IP       EXTERNAL-IP   PORT(S)   AGE
pacman   ClusterIP   10.106.219.213   <none>        80/TCP    4d13h

$ curl -m 5 http://192.168.144.23/
curl: timed out / unreachable
```

The pods are running. The service exists. The game is fine, *for anything
inside the VPC*. From my desk, it has simply gone, ghosts and all.

That's the whole VPC model in one `curl`. The boundary isn't a firewall rule
somebody wrote; it's the absence of a route.

## After: open it again

```
$ kubectl patch svc pacman -n pacman -p '{"spec":{"type":"LoadBalancer"}}'
service/pacman patched
NAME     TYPE           CLUSTER-IP       EXTERNAL-IP      PORT(S)        AGE
pacman   LoadBalancer   10.106.219.213   192.168.144.23   80:31467/TCP   4d13h
```

Same VIP, handed straight back. NSX programmed a virtual server and pool on
the VPC's load balancer, and the supervisor stitched them to the cluster's
NodePort. Door open. Lesson over, or so I thought.

And then the game *didn't load*.

## The outage I gave myself (this is the useful bit)

Everything was green:

- `kubectl get svc`: LoadBalancer, VIP assigned
- `kubectl get endpoints`: pod IPs present
- NSX: virtual server up, pool members healthy
- `iptables` on the node: NodePort rules identical to a working
  neighbour service

Five layers, all green, and `curl` hung. The control experiment was the
Pac-Man at `.15` on the hand-built cluster: untouched throughout, and still
playing.

The culprit, it turns out, was me. My "harmless" `ClusterIP` patch earlier
had included a `ports` list. A merge patch with `kubectl patch` **replaces
arrays** rather than merging them, and my array said `targetPort: 80`.
Pac-Man listens on **8080**.

So every layer above was faithfully forwarding traffic to a port nothing was
listening on. And every layer reported success, because *its* job was done.

```
$ kubectl patch svc pacman -n pacman --type=json \
    -p '[{"op":"replace","path":"/spec/ports/0/targetPort","value":8080}]'
service/pacman patched
$ curl -s http://192.168.144.23/ | grep -o '<title>.*</title>'
<title>Pacman in HTML 5 Canvas</title>
```

Instant recovery. The diagnosis walked the whole paravirtual chain: the VIP,
the supervisor's `VirtualMachineService`, the NSX virtual server and pool,
the NodePort `iptables` rules, and finally the pod. It's exactly the walk
you'll need one day:

| Layer | Check | What "green" hides |
|---|---|---|
| VIP | `kubectl get svc` EXTERNAL-IP | nothing about the backend |
| NSX LB | virtual server + pool status | pool health is TCP to the *NodePort*, not the pod |
| Endpoints | `kubectl get endpoints` | it lists pod IP:**targetPort** — read the number |
| Node | `iptables -t nat -L KUBE-SERVICES` | rules can be perfect and point at the wrong port |
| Pod | `kubectl exec ... ss -ltn` | the only place the truth lives |

Bonus find on the way: kube-proxy *and* Antrea on that cluster had dropped
their API watches days earlier (`http2: client connection lost`). Neither
re-established its informers until it was restarted. It didn't cause this
outage, but it's the kind of thing you only find when you're forced to look.

## Why this matters outside the lab

If you run a platform for more than one team, this is the feature you've been
asking the network team for. A VPC gives each team, project or customer its
own private network space. They create it themselves, in minutes, and nothing
in it is reachable from outside until they publish it.

Security teams like it for the same reason developers do. Exposure is a
deliberate, auditable act, not a side effect of plugging something in.

What organisations do with it once they have it:

- **Per-team sandboxes** that can't see each other, provisioned without a
  ticket.
- **Partner or supplier environments**, isolated from the corporate estate
  but hosted on the same platform.
- **Multi-tenant hosting**, for service providers and internal IT alike,
  with isolation enforced by topology rather than a growing pile of firewall
  rules.

## Rules learned

- A VPC's boundary is **the absence of a route**, not a rule. `Private`
  subnets are unreachable from outside by construction, which is also why
  identical CIDRs across VPCs just work.
- A `LoadBalancer` service is the *deliberate* door: an NSX VIP from the
  external block, programmed per service. Flip the type and the door closes,
  with nothing else to clean up.
- `kubectl patch` (merge) **replaces `spec.ports`**; it doesn't merge it.
  Patch a single field with `--type=json`, or leave the array out.
- Five green layers can hide one wrong integer. Keep a *working control*
  (here, the untouched `.15` instance) and compare layer by layer.
- Read `kubectl get endpoints` as `IP:targetPort`. The port is the part
  people skim.

## Broadcom documentation

- [Virtual Private Clouds Overview](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview.html): the subnet access modes, and the NAT a private subnet needs to reach outside.
- [Create a VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/create-a-vpc.html): private CIDRs, local to each VPC and allowed to overlap between VPCs.
- [Transit Gateways](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/transit-gateways.html): how VPCs reach each other and the outside network.
- [Deploying Supervisor with VCF Networking with VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsphere-supervisor-installation-and-configuration/supervisor-networking-with-virtual-private-clouds.html): the VPC, load balancer and SNAT IP behind a namespace, and the LoadBalancer services NCP provides.
- [Create vSphere Namespaces on VPCs without SNAT and Load Balancer](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsphere-supervisor-installation-and-configuration/configuring-and-managing-vsphere-namespaces/managing-vsphere-namespaces-on-a-supervisor-with-nsx-vpc/create-and-configure-a-vsphere-namespace-on-a-supervisor-with-vpc/create-namespaces-with-vpc-nosnat-nolb.html): without the VPC load balancer, LoadBalancer services cannot be deployed at all.

*Next in the Pod Papers: [nested ESXi inside a VPC](/posts/nested-esxi-nsx-vpc/),
where "private by default" meets a host that fakes its own MAC address.*

---
*Lab environment; opinions my own. Output captured live, trimmed for length,
never edited for outcome — including the outage.*
