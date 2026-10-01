---
title: "Blueprinting the supervisor: seven CCI blueprint gotchas"
date: 2026-09-16T07:10:00+01:00
draft: false
tags: [vcf, vcf-automation, all-apps, cci, blueprint, troubleshooting]
products: ["VCF Automation"]
series: ["The VPC Pod Papers"]
seriesPart: 9
cover:
  image: "/images/post8-hero-gotchas.svg"
  alt: "ContentValid: False — and the seven reasons why"
  hidden: false
summary: "Everything that made the nested-esxi-pod blueprint fail validation before it worked: ${input} inside flow mappings, name vs generateName, flat zones, contentSources, one-published-version, validation-in-status, and the image-sync race. Short, specific, and each one cost me a cycle."
---

The [nested-esxi-pod blueprint](/posts/nested-esxi-via-vcfa-all-apps/)
works. Getting there took seven distinct "ContentValid: False" (or worse:
a 200 that quietly did nothing). None of them are in the docs I could
find; all of them are five-minute fixes once you know. Here they are, in
the order they bit.

## 1. `${input.x}` is illegal inside a flow mapping

This looks like valid YAML and valid blueprint syntax:

```yaml
- {key: guestinfo.hostname, value: {value: "esx01.${input.podName}.res.lab"}}
```

It fails content validation. The expression parser doesn't reach into
flow-style (`{...}`) mappings. Block style is fine:

```yaml
- key: guestinfo.hostname
  value:
    value: esx01.${input.podName}.res.lab
```

Mixed style in the same list is fine too — only the entries that carry an
expression need to be block-style. (This is why the blueprint's
`vAppConfig` list looks inconsistent; it's deliberate.)

## 2. `name` vs `generateName` for a new namespace

A `CCI.Supervisor.Namespace` you're *creating* must use `generateName`.
`metadata.name` is rejected by the CCI API — the platform appends a random
suffix, so `pod-a-` becomes `pod-a-dgf5p`. Everything downstream should
reference `${resource.namespace.id}`, never a literal name.

## 3. Zones and storage classes are flat

Early attempts wrapped them the way the raw CCI API does:

```yaml
initialClassConfigOverrides:
  zones: [...]
```

In a blueprint they're top-level properties of the namespace resource:

```yaml
zones:
  - name: domain-c9
    cpuLimit: 40000M
    memoryLimit: 64000Mi
storageClasses:
  - name: vSAN Default Storage Policy
    limit: 400000Mi
```

And zones are **required** — omit them and the API says "Zone should be
specified", which at least is a clear message.

## 4. A new namespace has no content library

Deploy the namespace, deploy a VM, and get: no `VirtualMachineImage`
found. Our libraries were plain vCenter libraries, and a VCFA-created
namespace attached **none** of them. (The 9.1 docs say a
[namespace class](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-projects-in-vcfa/create-a-namespace-class.html)
is assigned a content library automatically, and provider libraries are
shared with every namespace.) The fix is one block:

```yaml
contentSources:
  - {name: ISO, type: ContentLibrary}
  - {name: f06-vks-lib01, type: ContentLibrary}
```

Without it you're in the vSphere Client attaching libraries to a namespace
by hand, which rather defeats the catalog.

## 5. Images sync *after* attach — wait for `status.disks`

Even with libraries attached at creation, the first VM create in a fresh
namespace can be rejected:

```
no disks found in image ... status.disks
```

The image objects appear immediately; their disk metadata syncs over the
next 1–3 minutes. The quota webhook checks `status.disks` and refuses
until it's populated. In a blueprint, put the hosts `dependsOn` something
that takes a couple of minutes (the binding maps did the job here), or add
an explicit wait. In a script, poll:

```
kubectl get virtualmachineimage -n <ns> <vmi> -o jsonpath='{.status.disks}'
```

## 6. Validation lives in `status`, not the HTTP code

Creating a `BlueprintVersion` returns 200 whether or not the content is
valid. Read the object back:

```
status:
  contentValid: false
  validationMessages:
    - "... unexpected token ..."
```

If your pipeline checks the response code, it will happily publish a
broken blueprint. Check `status.contentValid` and print the messages.

## 7. Only one published version — 409 on the second

Release 1.1.0 while 1.0.0 is released and you get a 409. It isn't a
transient conflict; it's the rule. **Unrelease** the current version, then
release the new one. Practically that means a publish step is
`unrelease old → release new`, and there's a short window where the
catalog item has no released version. Do it when nobody's requesting.

## Bonus: the things that aren't blueprint problems

Three prerequisites have to exist before the request — VPC,
VPCAttachment, LoadBalancer, [in that
order](/posts/the-lb-that-must-exist-first/). VCF Automation 9.1 has
blueprint types for the first two, `CCI.VPC` and `CCI.VPC.Configuration`
with `kind: VPCAttachment` (see its
[sample blueprints](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html)),
but none for the load balancer, and a VPC created that way comes up with
load balancing off. So we create all three before the request. The
blueprint's `vpcName` input says "must exist and be Realized", and it
means it. Nothing in the
blueprint fails if they're missing; the deployment just never gets a VIP.

## Why this matters outside the lab

VCF Automation's All Apps model is new, and new platforms have edges. Most
of these seven are not documented; all of them stall a first project by days if
you meet them cold. The value of a delivery partner who has already built
on the platform isn't the YAML — it's that a customer's first blueprint
publishes on day one instead of week two, and that the sharp edges are
encoded into templates and provisioning scripts where users never meet
them.

## Rules learned

- Expressions need **block-style YAML**; flow mappings don't get parsed.
- `generateName`, and reference the namespace by `${resource.x.id}`.
- `zones` and `storageClasses` are **flat** and zones are required.
- `contentSources` on the namespace for vCenter libraries, or nothing can
  be deployed.
- Wait for image `status.disks` before the first VM (1–3 min).
- Check `status.contentValid` — the HTTP code lies by omission.
- One released version per blueprint: unrelease, then release.

## Broadcom documentation

- [Sample Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html): a new namespace with `generateName`, and resources placed in it with `context`.
- [Create a Namespace Class in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-projects-in-vcfa/create-a-namespace-class.html): VM and storage classes, per-zone limits, and the content libraries a namespace gets.
- [Creating and Managing Content Libraries for Stand-Alone VMs in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/creating-and-managing-content-libraries-for-stand-alone-vms-in-iaas-platform.html): associating VM content libraries with a namespace.
- [Creating bindings and dependencies between resources in blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/bindings-and-dependencies.html): `dependsOn`, the explicit build order.
- [Versioning Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html): versions, and releasing one to the catalog.

*Companion to [a datacenter in a catalog tile](/posts/nested-esxi-via-vcfa-all-apps/).*

---
*Lab environment; opinions my own. Error text captured live.*
