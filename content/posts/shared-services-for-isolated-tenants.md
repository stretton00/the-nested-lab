---
title: "Shared services for isolated tenants: PrivateTGW subnets"
date: 2026-09-16T07:50:00+01:00
draft: false
tags: [vcf, nsx, vpc, transit-gateway, multi-tenancy, wsus]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/post5-hero-tgw.svg"
  alt: "Hub-and-spoke: three private pods reach one shared-services VPC over the transit gateway; the service cannot reach back"
  hidden: false
summary: "Three pods with identical private addressing all need the same WSUS, repo and AD. One shared-services VPC with a PrivateTGW subnet serves all of them over the transit gateway — and can't reach back into any of them. The directional test, and why SNAT is what makes it work."
---

The pods from [the last post](/posts/three-datacenters-one-ip-plan/) are
perfectly isolated. That's the requirement — and immediately the problem.
Every one of them needs Windows updates, a package repo, DNS, maybe a
domain controller. Do I really run a WSUS *per pod*?

No. There's a third subnet access mode for exactly this, and the design it
enables is hub-and-spoke with a very specific property: **spokes reach the
hub; the hub cannot reach the spokes; spokes never reach each other.**

## The three access modes

Everything in this series comes down to one field on a VPC subnet:

| `accessMode` | Advertised to | Use |
|---|---|---|
| `Private` | nobody outside the VPC | workloads — isolation *and* overlapping CIDRs |
| `PrivateTGW` | every VPC attached to the org's transit gateway | shared services |
| `Public` | the external network | internet/corp-facing endpoints |

`PrivateTGW` subnets draw their addresses from a **separate transit
block** (here `172.31.0.0/…`), not from the VPC's own `privateIPs`. That's
the key: the shared range can't collide with the pods' `172.30.0.0/16`
because it comes from a different pool that all VPCs agree on.

## The build

One more VPC, `shared-svc`, with the same ordering rules as any other
(VPC → VPCAttachment → LoadBalancer → namespace), then a single subnet:

```yaml
apiVersion: crd.nsx.vmware.com/v1alpha1
kind: Subnet
metadata: {name: sn-services}
spec: {accessMode: PrivateTGW, ipv4SubnetSize: 32}
```

It realized as `172.31.0.0/27`, and a VM on it — `svc-repo01`,
`172.31.0.2`, serving HTTP — became the shared repo.

![Architecture: VPC per pod, transit gateway, shared-services VPC](/images/product-02-architecture.jpg)

## The test that matters is directional

Reachability *to* the service is the easy claim. From `esx01` in each of
the three pods (ESXi ships python3, so `urllib` is the test client):

```
pod-a esx01 -> http://172.31.0.2/   200  shared-svc repo01
pod-b esx01 -> http://172.31.0.2/   200  shared-svc repo01
pod-c esx01 -> http://172.31.0.2/   200  shared-svc repo01
default-vpc  -> http://172.31.0.2/   200  shared-svc repo01
```

Three pods with **identical source addresses** (`172.30.0.40`) all hit
one service and all get answers. How does the reply find its way back to
the right pod when three of them claim `.40`? Because pod traffic crosses
the transit gateway **SNAT'd to a per-VPC transit address**. The service
never sees `172.30.0.40`; it sees three distinct transit IPs. Ambiguity
never arises.

Now the other direction — from `svc-repo01` back toward a pod:

```
svc-repo01 -> 172.30.0.40   unreachable
svc-repo01 -> 172.30.0.41   unreachable
```

Not "blocked" — *unroutable*. Pod subnets are `Private`, so they were never
advertised to the transit gateway, and even if they had been, `172.30.0.40`
would be ambiguous across three VPCs. The hub literally cannot initiate
into a spoke. For a shared service that will one day be compromised,
that's the property you want.


## What goes in the hub

Anything that's *consumed* by pods and *stateless about which pod is
asking*: WSUS/patch mirrors, OS and package repos, container registries,
NTP, DNS forwarders, license servers. Domain controllers work too, with
the usual caveat that identical hostnames across pods need per-pod domains
or a naming scheme.

What does **not** go in the hub: anything that needs to *reach into* a pod
(monitoring pollers, backup agents pulling, jump hosts). Those either live
in the pod, or the pod publishes a `LoadBalancer` VIP for them — the
deliberate door from [part 0](/posts/whats-a-vpc-with-pacman/).

## Tightening further

The transit gateway gives you reachability; policy gives you precision. A
`VPCGatewayFirewallPolicy` on `shared-svc` can restrict inbound to
`tcp/80,443` from the transit range and nothing else, so the repo is a
repo and not a foothold. I left it open for the test; you shouldn't.

## Why this matters outside the lab

This is the pattern that makes isolated tenants *affordable*. Without it,
every isolated environment needs its own patch server, repository, DNS and
directory — cost and drift that quietly kill the idea. With it, a customer
runs one set of shared services for dozens of tenants, keeps them patched in
one place, and can still show a security reviewer that the shared service
has no path back into any tenant.

The same hub serves well beyond patching: central logging and monitoring
collectors, licence servers, artifact registries, build agents — anything
tenants consume but shouldn't be able to be reached *by*.

## Rules learned

- `PrivateTGW` is the shared-services mode: addresses from the **transit
  block**, advertised to every attached VPC, no collision with pod space.
- Access is **one-way by construction**: pods → service works (SNAT'd
  per VPC), service → pod has no route. Test both directions and write
  down both results.
- Identical pod addressing and shared services coexist *because* of the
  SNAT — the hub sees per-VPC transit addresses, never the overlapping
  private ones.
- Same ordering rules apply to the hub VPC (VPC → attachment → LB →
  namespace → subnets → wait for image sync → workloads).
- Add a gateway firewall policy on the hub. Reachability is not
  authorisation.

*Previously: [three datacenters, one IP plan](/posts/three-datacenters-one-ip-plan/).
Next: the whole pod as a single catalog item.*

---
*Lab environment; opinions my own. Output captured live, trimmed for length,
never edited for outcome.*
