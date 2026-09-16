---
title: "A datacenter in a catalog tile: nested ESXi pods via VCF Automation All Apps"
date: 2026-09-16T07:40:00+01:00
draft: false
tags: [vcf, vcf-automation, all-apps, cci, blueprint, nested-esxi, vpc]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/post6-hero-blueprint.svg"
  alt: "One blueprint: namespace, trunk topology, two nested hosts, two VIPs — requested as a catalog item"
  hidden: false
summary: "The whole isolated pod — namespace, trunk subnets, binding maps, two dual-NIC nested ESXi hosts with an ISO attached, SSH/HTTPS VIPs — as one VCF Automation blueprint, published to the catalog. Anatomy of the blueprint, the ordering it enforces, and the three things it can't express."
---

Everything in this series so far was built with `kubectl` and API calls.
That proves the platform. It doesn't make a *product*. This post turns the
pod into a **catalog item**: fill in a name, pick a VPC, click Request, and
a few minutes later there's a datacenter-in-miniature with two SSH prompts
waiting.

![VCFA catalog: the nested-esxi-pod tile](/images/ui/u1-catalog-tile.jpg)

## All Apps in one paragraph

VCF Automation 9.1 has two provisioning models side by side. **VM Apps** is
the classic Aria Automation path — cloud templates through an IaaS engine
that drives vCenter. **All Apps** is the supervisor-native path: the
blueprint composes Kubernetes objects (a Supervisor Namespace, VM Service
VMs, NSX subnets, VKS clusters) and the vSphere Supervisor's controllers
reconcile them. A blueprint is `formatVersion: 2`; its resources are
`CCI.Supervisor.Namespace` and `CCI.Supervisor.Resource` — the latter is
literally "here's a manifest, apply it in that namespace."

That makes the blueprint a *composition* of the manifests from the earlier
posts, with two additions: inputs, and `dependsOn`.

## The blueprint, section by section

### Inputs — the form

```yaml
inputs:
  podName:  {type: string, default: nested-pod, pattern: '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'}
  vpcName:  {type: string, description: Must exist and be Realized before deploying.}
  esxOva:   {type: string, default: vmi-61bb062ddfc506b79}   # Nested ESXi 9.1 appliance
  isoImage: {type: string, default: vmi-39f562e2ae9e9c501}   # the ISO to attach
  vmClass:  {type: string, default: best-effort-large, enum: [best-effort-large, best-effort-xlarge, best-effort-2xlarge]}
```

![The request form](/images/ui/u2-request-form.jpg)

### The namespace — with libraries attached

```yaml
namespace:
  type: CCI.Supervisor.Namespace
  properties:
    generateName: ${input.podName}-        # NOT name — new namespaces get a suffix
    className: large
    regionName: f06
    vpcName: ${input.vpcName}              # pins the namespace to the pod's VPC
    storageClasses: [{name: vSAN Default Storage Policy, limit: 400000Mi}]
    zones: [{name: domain-c9, cpuLimit: 40000M, memoryLimit: 64000Mi, ...}]
    contentSources:
      - {name: ISO, type: ContentLibrary}
      - {name: f06-vks-lib01, type: ContentLibrary}
```

`contentSources` is the line that closes the gap a lot of first attempts
hit: a VCFA-created namespace has **no content library**, so there are no
`VirtualMachineImage`s and nothing can be deployed. Declaring the libraries
here attaches them at creation.

### The topology — ordered on purpose

```yaml
snTrunk:   {type: CCI.Supervisor.Resource, properties: {context: ${resource.namespace.id}, manifest: <Subnet sn-trunk>}}
snMgmt:    {dependsOn: [snTrunk], ...  manifest: <Subnet sn-mgmt>}
snVmotion: {dependsOn: [snMgmt],  ...  manifest: <Subnet sn-vmotion>}
bmMgmt:    {... manifest: <SubnetConnectionBindingMap sn-mgmt -> sn-trunk, vlan 1610>}
bmVmotion: {... manifest: <SubnetConnectionBindingMap sn-vmotion -> sn-trunk, vlan 1611>}
```

The `dependsOn` chain is the whole reason [every pod has identical
CIDRs](/posts/three-datacenters-one-ip-plan/): fresh VPCs realize subnets
in creation order, and the blueprint fixes that order.

![Blueprint canvas and YAML side by side](/images/ui/u3-blueprint-canvas-yaml.jpg)

### The hosts — dual-NIC, ISO attached, bootstrapped by OVF

```yaml
esx01:
  type: CCI.Supervisor.Resource
  dependsOn: [bmMgmt]                    # no point booting before VLAN 1610 exists
  properties:
    context: ${resource.namespace.id}
    manifest:
      apiVersion: vmoperator.vmware.com/v1alpha5
      kind: VirtualMachine
      spec:
        image: {kind: VirtualMachineImage, name: ${input.esxOva}}
        className: ${input.vmClass}
        guestID: vmkernel8Guest
        hardware:
          cdrom:
            - {name: cdrom0, image: {kind: VirtualMachineImage, name: ${input.isoImage}}, connected: true}
        network:
          interfaces:
            - {name: eth0, network: {kind: Subnet, name: sn-trunk, apiVersion: crd.nsx.vmware.com/v1alpha1}}
            - {name: eth1, network: {kind: Subnet, name: sn-trunk, apiVersion: crd.nsx.vmware.com/v1alpha1}}
        bootstrap:
          vAppConfig:
            properties:
              - key: guestinfo.hostname
                value:
                  value: esx01.${input.podName}.res.lab
              - {key: guestinfo.ipaddress, value: {value: "172.30.0.40"}}
              - {key: guestinfo.vlan,      value: {value: "1610"}}
              # ... netmask, gateway, dns, ntp, ssh=True
  wait:
    fields: [{path: status.powerState, value: PoweredOn}]
```

Two vNICs, both on the trunk — [the nested equivalent of a VCF host's two
pNICs](/series/the-vpc-pod-papers/). The ISO rides along as a declarative
CD-ROM. And the `wait` block makes the deployment's *completion* mean
something: the request doesn't finish until the host is powered on.

### The doors — one VIP per host

```yaml
esx01Access:
  type: CCI.Supervisor.Resource
  properties:
    context: ${resource.namespace.id}
    manifest:
      apiVersion: vmoperator.vmware.com/v1alpha5
      kind: VirtualMachineService
      spec:
        type: LoadBalancer
        selector: {app: esx01}
        ports: [{name: https, port: 443, targetPort: 443}, {name: ssh, port: 22, targetPort: 22}]
outputs:
  esx01Ssh: {value: "ssh root@${resource.esx01Access.object.status.loadBalancer.ingress[0].ip}"}
```

The outputs surface in the deployment view — the requester gets the SSH
command, not a scavenger hunt.

![Deployment topology after a successful request](/images/ui/u4-deployment-topology.jpg)

![Request → deployment in progress → complete](/images/u7-catalog-request-flow.gif)
*The request flow, end to end.*


## What the blueprint cannot express (yet)

Three cluster-scoped objects have **no blueprint resource type**, and they
must exist *before* the request — [in this order](/posts/the-lb-that-must-exist-first/):

1. `VPC` — `privateIPs: 172.30.0.0/16`, same in every pod
2. `VPCAttachment` — connectivity profile with the service gateway; the LB
   creation fails loudly without it
3. `LoadBalancer` — silently, permanently required before the namespace

Today that's a short script or a runbook step per pod. The honest framing:
the blueprint is the *pod*; the VPC is the *tenancy*, and tenancy is
still created one layer up. I'd expect that layer to become blueprintable;
until then, keep the three calls next to the blueprint in version control.

## Publishing: one version at a time

Blueprint → `BlueprintVersion` → release. Validation happens at *version*
time, not create time, and the result lives in `status.validationMessages`
rather than the HTTP code — a 200 with `ContentValid: False` is a thing.
And only **one** version can be published: unrelease 1.0.0 before releasing
1.1.0, or you get a 409. (The full list of sharp edges is
[its own post](/series/the-vpc-pod-papers/).)

## Rules learned

- All Apps blueprints are **compositions of manifests**: `CCI.Supervisor.Namespace`
  plus `CCI.Supervisor.Resource` per object. If it works with `kubectl`, it
  works in a blueprint.
- `generateName`, not `name`, for the namespace; `contentSources` to attach
  libraries at creation; `zones`/`storageClasses` flat, not wrapped.
- `dependsOn` is how you get **deterministic CIDRs** — order the subnets.
- `wait.fields` turns "request complete" into "host is powered on".
- VPC / VPCAttachment / LoadBalancer are **prerequisites outside the
  blueprint**, in that order, before every request.
- One published version per blueprint; validation in `status`, not the
  HTTP response.

*Previously: [shared services for isolated tenants](/posts/shared-services-for-isolated-tenants/).
This closes the Pod Papers' core arc — the companion posts on
[dual-NIC](/series/the-vpc-pod-papers/), [no-DHCP bootstrap](/series/the-vpc-pod-papers/)
and [blueprint gotchas](/series/the-vpc-pod-papers/) fill in the details.*

---
*Lab environment; opinions my own. Blueprint `nested-esxi-pod` 1.1.0 is
live in the lab catalog; YAML above trimmed for length.*
