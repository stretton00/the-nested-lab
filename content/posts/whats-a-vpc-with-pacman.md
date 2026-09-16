---
title: "What's a VPC? Let Pac-Man explain"
date: 2026-09-16T08:30:00+01:00
draft: false
tags: [vcf, nsx, vpc, vks, kubernetes, explainer]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/post0-hero-pacman.svg"
  alt: "Pac-Man inside a VPC boundary; a LoadBalancer VIP is the one door out"
  hidden: false
summary: "Part 0 of the Pod Papers: an NSX VPC explained with a running game. Private by default, one deliberate door out — and a self-inflicted outage that taught me five green layers can hide one wrong integer."
---

Before this series gets into trunk subnets and binding maps, it's worth
spending ten minutes on the thing everything else stands on: **what an NSX
VPC actually is** from the tenant's chair. No slides. A game of Pac-Man.

The lab has Pac-Man running twice on VCF 9.1 — once on a VKS cluster I
built by hand with `kubectl`, once on a cluster deployed through VCF
Automation's catalog. Both live inside VPCs. Both were reachable when I
started:

```
http://192.168.144.15/  ->  <title>Pacman in HTML 5 Canvas
http://192.168.144.23/  ->  <title>Pacman in HTML 5 Canvas
```

{{< video src="/images/pacman-vip-23.mp4" ratio="710 / 610" caption="Pac-Man, live at `192.168.144.23` — a VIP on the VPC load balancer. The only door in." >}}

## A VPC is a private universe with a door policy

Think of an NSX VPC as a tenant's own routed network space: its own
subnets, its own gateway, its own address plan — carved out by the tenant,
not filed as a ticket with the network team. Three rules define it:

1. **Private by default.** A `Private` subnet is reachable only from inside
   the same VPC. Nobody outside can route to it — not other tenants, not
   other VPCs in the same org, not the corporate network.
2. **Your addresses are your business.** Because private subnets aren't
   advertised anywhere, two VPCs can use *identical* CIDRs. (This is the
   superpower the rest of the series is built on.)
3. **Every door out is deliberate.** Traffic leaves via the transit
   gateway — SNAT'd — or arrives via a **LoadBalancer VIP** from an
   external block the provider allocated. Nothing is exposed by accident.

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

The pods are running. The service exists. The game is fine — *for anything
inside the VPC*. From my desk it's simply gone. That's the whole VPC model
in one `curl`: the boundary isn't a firewall rule somebody wrote, it's the
absence of a route.

## After: open it again

```
$ kubectl patch svc pacman -n pacman -p '{"spec":{"type":"LoadBalancer"}}'
service/pacman patched
NAME     TYPE           CLUSTER-IP       EXTERNAL-IP      PORT(S)        AGE
pacman   LoadBalancer   10.106.219.213   192.168.144.23   80:31467/TCP   4d13h
```

Same VIP handed straight back. NSX programmed a virtual server and pool on
the VPC LB; the supervisor stitched it to the cluster's NodePort. Door open.


And then the game *didn't load*.

## The outage I gave myself (this is the useful bit)

Everything was green:

- `kubectl get svc` — LoadBalancer, VIP assigned
- `kubectl get endpoints` — pod IPs present
- NSX — virtual server up, pool members healthy
- `iptables` on the node — NodePort rules identical to a working
  neighbour service

Five layers, all green, and `curl` hung. The control experiment was the
manually-built cluster's Pac-Man at `.15`, untouched throughout, still
playing.

The cause: my "harmless" `ClusterIP` patch earlier had included a `ports`
list. `kubectl patch` with a merge patch **replaces arrays**, it doesn't
merge them — and my array said `targetPort: 80`. Pac-Man listens on
**8080**. Every layer above was faithfully forwarding traffic to a port
nothing was listening on, and every layer reported success because *its*
job was done.

```
$ kubectl patch svc pacman -n pacman --type=json \
    -p '[{"op":"replace","path":"/spec/ports/0/targetPort","value":8080}]'
service/pacman patched
$ curl -s http://192.168.144.23/ | grep -o '<title>.*</title>'
<title>Pacman in HTML 5 Canvas</title>
```

Instant recovery. The diagnosis walked the entire paravirtual chain —
VIP → supervisor `VirtualMachineService` → NSX VS/pool → NodePort
`iptables` → pod — and it's exactly the walk you'll need one day:

| Layer | Check | What "green" hides |
|---|---|---|
| VIP | `kubectl get svc` EXTERNAL-IP | nothing about the backend |
| NSX LB | virtual server + pool status | pool health is TCP to the *NodePort*, not the pod |
| Endpoints | `kubectl get endpoints` | it lists pod IP:**targetPort** — read the number |
| Node | `iptables -t nat -L KUBE-SERVICES` | rules can be perfect and point at the wrong port |
| Pod | `kubectl exec ... ss -ltn` | the only place the truth lives |

Bonus find on the way: kube-proxy *and* Antrea on that cluster had dropped
their API watches days earlier (`http2: client connection lost`) and never
re-established informers until restarted. It didn't cause this outage, but
it's the kind of thing you only find when you're forced to look.

## Rules learned

- A VPC's boundary is **the absence of a route**, not a rule. `Private`
  subnets are unreachable from outside by construction — which is also why
  identical CIDRs across VPCs just work.
- A `LoadBalancer` service is the *deliberate* door: NSX VIP from the
  external block, programmed per service. Flip the type and the door
  closes with nothing else to clean up.
- `kubectl patch` (merge) **replaces `spec.ports`**, it doesn't merge it.
  Patch a single field with `--type=json`, or don't include the array.
- Five green layers can hide one wrong integer. Keep a *working control*
  (here: the untouched `.15` instance) and compare layer by layer.
- Read `kubectl get endpoints` as `IP:targetPort` — the port is the part
  people skim.

*Next in the Pod Papers: [nested ESXi inside a VPC](/posts/nested-esxi-nsx-vpc/) —
where "private by default" meets a host that fakes its own MAC address.*

---
*Lab environment; opinions my own. Output captured live, trimmed for length,
never edited for outcome — including the outage.*
