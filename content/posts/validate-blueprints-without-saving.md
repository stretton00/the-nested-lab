---
title: "Validate a VCF Automation blueprint without saving it"
date: 2027-02-10
draft: false
tags: [vcf, vcf-automation, blueprints, api, property-groups, supervisor]
products: ["VCF Automation"]
series: ["The Lab Factory"]
seriesPart: 9
tldr:
  - "One VCF Automation API call checks a blueprint's resource types, inputs, property groups and expressions, and leaves nothing behind."
  - "It answers HTTP 200 to good and bad blueprints alike, so trust `valid`, not the cheerful status code."
  - "It misses unknown properties in existing groups and unknown manifest fields, so check `propgroup` paths and dry-run manifests on the Supervisor."
tested: "VCF 9.1"
cover:
  image: "/images/post41-hero-validate-blueprints.svg"
  alt: "Three checks before a request: the blueprint validation call, a Supervisor dry run of each manifest, and the released version diffed with the generator's output"
  hidden: false
summary: "One VCF Automation API call checks a blueprint without saving anything: a misspelt resource type, a missing input, an absent property group or a broken expression, anywhere in it. What that call does not check, and the three small checks we run beside it before a catalog goes anywhere."
---

The first person to find a typo in a blueprint is usually whoever requests it.
In our lab catalog, that can be a trainer at eight in the morning with a class
waiting, which is not when I want my typos found. Depending on the mistake, the
failure turns up when they submit, or a few minutes in, after the namespace
already exists.

Our eight lab blueprints are written by a generator from a site file, so a new
platform means eight new blueprints at once. I wanted proof that they resolve
before anyone imports them, without leaving drafts behind in somebody's
catalog.

VCF Automation 9.1 will do that for you in one API call. This post covers what
the call catches, what it doesn't, and the three checks we now run beside it.

## One call, nothing saved

The blueprint service validates a blueprint you send it, and stores nothing:
no blueprint, no draft, no version. The body is the YAML as a string, plus the
project to resolve it in. Our tools wrap the organization token in a small
session helper, so the call is one line:

```python
code, r = call("POST", "/blueprint/api/blueprint-validation",
               {"content": blueprint_yaml, "projectId": project_id})
```

Against our generated Phase 6 blueprint, 1,238 lines and 25 resources:

```text
== lab-phase-6-ad-integration as generated: HTTP 200
{
 "valid": true,
 "validationMessages": []
}
```

Nothing is left behind. I counted, being the trusting sort. Three calls
later, even with a `name` in the body:

```text
== blueprints before 9, after three validation calls 9; new: none; changed: none
```

## What it catches

Then copies of the same blueprint, each with one mistake. Deliberate ones, for
once:

| Mistake | `message` | `path` |
|---|---|---|
| `CCI.Supervisor.Namespaze` | `Resource type CCI.Supervisor.Namespaze not found` | `$.resources.namespace` |
| `${input.labNme}` | `Missing 'labNme' property in 'input' object` | `$.resources.dcConfig.properties.manifest.stringData.user-data` |
| `propgroup.nestedLabSyte...` | `Property group nestedLabSyte of type Constant not found` | `$.resources.namespace.properties.className` |
| `${resource.namespaec.id}` | `Blueprint resource namespaec not found` | `$.resources.snTrunk.properties.context` |
| `${'dc01-' + input.labName` | `Unable to compile expression ... syntax error missing EXPR_END_TAG at '<EOF>' at position 25` | `$.resources.dc01.properties.manifest.metadata.name` |

Three things to notice. Every answer is HTTP 200, good blueprint or bad, so
read `valid`, not the status code. A message has a `resourceName`, a `path`
and a `message`, and no severity field: one message is one failure. And the
second row is deep inside a Supervisor manifest, in a Secret's cloud-init
`user-data`. References and expressions are resolved everywhere, manifests
included.

## What it does not catch

Two gaps showed up, and both pass with flying colours.

**A property that a group does not have.** `propgroup.nestedLabSite.labDomian`,
one letter swapped, in a group that exists:

```text
== a property that does not exist in an existing group: HTTP 200
{
 "valid": true,
 "validationMessages": []
}
```

The call checks that the group exists, not the property. That gap is a few
lines of script: list each group's properties from the property-groups API,
then check every `propgroup.<group>.<property>` path in the blueprint against
them:

```text
lab-phase-6-ad-integration.yaml       21 distinct references, 0 unknown
nested-esxi-lab-jump.yaml             18 distinct references, 0 unknown
phase6-typo.yaml                      22 distinct references, 1 unknown
    propgroup.nestedLabSite.labDomian: nestedLabSite has no property labDomian
```

**A field the manifest's own schema does not have.** A VirtualMachine with
`spec.classNmae` passes too:

```text
== a VirtualMachine manifest with spec.classNmae: HTTP 200
{
 "valid": true,
 "validationMessages": []
}
```

VCF Automation passes Supervisor manifests through as they are. The schema
lives on the Supervisor, and the Supervisor will check a manifest without
creating anything:

```bash
kubectl apply --dry-run=server --validate=strict -n ns-student03-tj4cc -f dc01.yaml
```

```text
Error from server (BadRequest): error when creating "STDIN": VirtualMachine in version "v1alpha5" cannot be handled as a VirtualMachine: strict decoding error: unknown field "spec.classNmae"
```

With the field spelt right:

```text
virtualmachine.vmoperator.vmware.com/dryrun-dc01 created (server dry run)
```

`created (server dry run)` means the request also went through the VM
Operator's admission checks in that namespace, with nothing created. There are
two catches. The dry run needs a namespace that exists (any lab's will do), and
a manifest full of `${...}` has to be rendered first. We fill the expressions
with the property groups' values and sample inputs.

## Is the catalog running what the generator writes?

The catalog serves released versions, not the YAML on disk. One fix typed into
the designer, or a release made from an older checkout, and the two drift
apart without a sound. Each released version's content is one GET away, at
`/blueprint/api/blueprints/{id}/versions/{version}`, so we diff it with what
the generator writes today:

```text
== released versions against the generator's output
lab-phase-3-esxi-hosts       released 2.1.10  0 line(s) differ
lab-phase-4-vcenter          released 2.1.10  0 line(s) differ
lab-phase-5-ops              released 2.1.10  0 line(s) differ
lab-phase-6-ad-integration   released 2.1.10  0 line(s) differ
nested-esxi-lab-dc           released 2.1.10  0 line(s) differ
nested-esxi-lab-jump         released 2.1.10  0 line(s) differ
lab-phase-1-dc-build         released 2.1.10  0 line(s) differ
lab-phase-2-blank-hosts      released 2.1.10  0 line(s) differ
```

Zero is the only good answer. Anything else means someone decides which side is
right before the next release, instead of finding out from a request.

## Property groups: round-trip them

Property groups have no validation call. Ours are generated as JSON bodies,
so the check is a round trip: post the body under a throwaway name, read it
back, compare, delete.

```text
== POST property group copy: HTTP 201
defaultRelease  sent keys ['const', 'description', 'type'] | back keys ['const', 'description', 'encrypted', 'type'] | encrypted=False
defaultRelease  identical apart from 'encrypted': True
releases        sent keys ['const', 'description', 'type'] | back keys ['const', 'description', 'encrypted', 'type'] | encrypted=False
releases        identical apart from 'encrypted': True
== DELETE: HTTP 204
```

The server adds `encrypted: false` to every property, just to be sure.
Everything else comes back as sent, so compare with that one key ignored.

## The order we run them

1. Generate the blueprints and the property-group bodies from the site file.
2. Round-trip the property groups, then the validation call on every
   blueprint: `valid` must be `true`.
3. Check every `propgroup` path against the groups' properties.
4. Dry-run every rendered manifest on the Supervisor.
5. After a release, diff each released version with the generator's output.

Each check is a few lines of Python against the same two APIs and `kubectl`,
so all five can sit in one script beside the generator.

## Why this matters outside the lab

A blueprint is code that runs against a shared platform. Testing it by
requesting it costs a namespace, quota, a few minutes and sometimes a
clean-up. These checks cost a handful of API calls and leave nothing behind.
So they fit wherever blueprints change: a pipeline on every commit, a review
before a release, or a new site's generated catalog before it is imported.

The split is the useful part to remember. VCF Automation knows the blueprint's
references. The Supervisor knows the manifests' schemas. Only you know what
you meant to release.

## Rules learned

- `blueprint-validation` answers HTTP 200 for good and bad blueprints alike:
  read `valid`.
- Its messages carry no severity. One message is one failure.
- It resolves references and expressions everywhere, manifests included, but
  checks only that a property group exists, not its properties: check
  `propgroup.<group>.<property>` paths yourself.
- It never checks a manifest against its schema. Use
  `kubectl apply --dry-run=server --validate=strict` in a real namespace.
- The catalog runs what was released, not what is on disk: diff released
  versions with the generator's output.
- Property groups have no validation call. Round-trip them under a throwaway
  name and expect only `encrypted: false` added.

## Broadcom documentation

- [Managing Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation.html): blueprints, the designer, inputs, versions, property groups and custom forms
- [Versioning Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html): blueprint versions and releasing one to the catalog
- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): input and constant property groups, shared with the organization or kept to one project
- [Constant Property Groups in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups/constant-property-groups-in-vcf-automation-for-all-apps.html): constant values that blueprints read through the `propgroup` binding
- [Deploying and Managing Virtual Machines in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane.html): VM classes, images and storage classes behind a VirtualMachine manifest

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
