---
title: "Every resource in the VCF Automation 9.1 blueprint designer: the complete guide"
date: 2026-10-01
draft: false
tags: [vcf, vcf-automation, blueprints, vm-service, vks, nsx, vpc, reference]
products: ["VCF Automation", "VKS", "NSX"]
ShowToc: true
ShowReadingTime: false
TocOpen: false
tldr:
  - "Behind the designer's sixteen palette items sit only five resource types, documented field by field and checked on a live platform."
  - "Mistakes show up late: the designer saves, the validator nods, and the request fails ten minutes in."
  - "Where the designer and the platform disagree, the platform wins, so dry-run every manifest on the Supervisor first."
tested: "VCF 9.1"
cover:
  image: "/images/post40-hero-blueprint-reference.svg"
  alt: "The blueprint designer's palette, Supervisor Namespace, VPC and Workload groups, unfolding into five YAML types and the Kubernetes kinds behind each item"
  hidden: false
summary: "A complete guide to the VCF Automation 9.1 blueprint designer: every palette item, the YAML behind it, every field the platform accepts, recipes and traps. Every snippet validated, dry-run or deployed."
---

The blueprint designer in a VCF Automation 9.1 All Apps organization offers
sixteen items in three groups. Drag one onto the canvas and you get a few
lines of YAML. What you may write underneath them is spread across the VM
Service, VKS, NSX VPC and Automation guides. For some items, it's written
down nowhere at all.

This guide puts it in one place. For each item, you get:

- what it creates, and the YAML behind it;
- every field the platform accepts;
- a minimal snippet, and recipes for the common jobs;
- the status fields worth reading;
- the traps we hit.

Three things make it more than a list from memory, which, given my memory,
is just as well:

- **The field lists come from the platform.** VCF Automation publishes the
  schema of every blueprint resource type through its API. The designer
  carries the schema of every palette item. The Supervisor publishes the
  definition of every Kubernetes kind it serves, and VCF Automation's VPC API
  publishes its own. Where they disagree (and they do), the tables follow
  what the platform enforces.
- **Every snippet was checked.** Each one went through VCF Automation's
  validation API, and every Kubernetes manifest through a server-side dry
  run on the Supervisor. Five test blueprints (all of them in the downloads)
  deployed every item for real. The remaining recipes are ones our lab
  catalog deploys every day.
- **The traps are real.** Several of the most useful lines in this guide come
  from things that went wrong while testing: a NAT rule that ignored its
  port, a firewall rule that grew an "Any", a request that waits for an
  address that can never come.

We checked it on our lab platform, f06:

- VCF Automation 9.1.0;
- a Supervisor on Kubernetes 1.32.9, with the VM Operator API at `v1alpha5`;
- VKS with ClusterClasses up to `builtin-generic-v3.6.0`, and Kubernetes
  releases up to 1.35.5;
- NSX VPCs.

Names in the examples (`f06`, `nested-pod`, `vpc-student05`,
`vsan-default-storage-policy`) are ours; use yours.

In the field tables, **Values** gives a field's choices and default. Where the
schema has neither, it gives an example, marked *e.g.*: the value from our
tested blueprints wherever one of them set the field, otherwise a typical one.
For an object or a list, the example is a short YAML flow value built from its
fields (`...` marks the ones left out). And `<...>` stands for a name of yours.

## The shape of a blueprint

An All Apps blueprint is YAML with `formatVersion: 2`, its inputs, its
resources and its outputs:

```yaml
formatVersion: 2
inputs:
  vmName:
    type: string
    title: VM name
    default: web-01
    pattern: '^[a-z0-9]([-a-z0-9]*[a-z0-9])?$'
  size:
    type: string
    title: Size
    default: small
    oneOf:
      - {title: Small, const: small}
      - {title: Medium, const: medium}
resources:
  namespace:
    type: CCI.Supervisor.Namespace
    properties:
      name: team-a-dev
      existing: true
  vm1:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: vmoperator.vmware.com/v1alpha5
        kind: VirtualMachine
        metadata:
          name: ${input.vmName}
        spec:
          className: ${'best-effort-' + input.size}
          imageName: ubuntu-24.04-server-cloudimg-amd64
          storageClass: vsan-default-storage-policy
outputs:
  vmName:
    value: ${resource.vm1.object.metadata.name}
```

What the expressions can read:

| Expression | Value |
|---|---|
| `${input.<name>}` | A request input. An input group from a property group is `${input.<group>.<property>}`. |
| `${resource.<name>.<property>}` | Another resource's property; this also orders the two. `object` holds the live Kubernetes object of a Supervisor Resource. |
| `${propgroup.<group>.<property>}` | A constant property group's value. |
| `${secret.<name>}` | A VCF Automation secret, from the organization or the project. |
| `${env.deploymentName}`, `${count.index}` | The deployment's name; the instance number in a counted resource. |
| `${to_k8s_name(env.deploymentName, 63)}` | A string made safe for a Kubernetes name, as Broadcom's own samples use for `generateName`. |

Besides `type` and `properties`, each resource has `dependsOn` (an explicit
order) and `allocatePerInstance` (see `count` below). `formatVersion: 2` also
allows `metadata`, `variables`, and an output named `__deploymentOverview`,
whose Markdown value becomes the deployment's overview page.

## How the palette maps to YAML

Behind the sixteen items there are only five resource types, and one of them
isn't in the palette. Most items are a type with part of its YAML already
filled in. For the workload items, that's a Kubernetes `apiVersion` and
`kind`; for the VPC items, it's a VPC configuration `kind`.

| Palette item | YAML `type` | Pre-filled |
|---|---|---|
| Supervisor Namespace | `CCI.Supervisor.Namespace` | |
| **VPC group** | | |
| VPC | `CCI.VPC` | |
| VPC Configuration | `CCI.VPC.Configuration` | nothing: you set `kind` |
| Attachment | `CCI.VPC.Configuration` | `kind: VPCAttachment` |
| IP Address Allocation | `CCI.VPC.Configuration` | `kind: VPCIPAddressAllocation` |
| NAT Rule | `CCI.VPC.Configuration` | `kind: VPCNATRule` |
| Group | `CCI.VPC.Configuration` | `kind: VPCNetworkSecurityGroup` |
| Gateway Firewall Policy | `CCI.VPC.Configuration` | `kind: VPCGatewayFirewallPolicy` |
| **Workload group** | | |
| Supervisor Resource | `CCI.Supervisor.Resource` | nothing: any manifest |
| Virtual Machine | `CCI.Supervisor.Resource` | `vmoperator.vmware.com/v1alpha5` `VirtualMachine` |
| Virtual Machine Group | `CCI.Supervisor.Resource` | `vmoperator.vmware.com/v1alpha5` `VirtualMachineGroup` |
| Virtual Machine Service | `CCI.Supervisor.Resource` | `vmoperator.vmware.com/v1alpha3` `VirtualMachineService` |
| Subnet | `CCI.Supervisor.Resource` | `crd.nsx.vmware.com/v1alpha1` `Subnet` |
| Persistent Volume Claim | `CCI.Supervisor.Resource` | `v1` `PersistentVolumeClaim` |
| Secret | `CCI.Supervisor.Resource` | `v1` `Secret` |
| Kubernetes Cluster | `CCI.Supervisor.Resource` | `cluster.x-k8s.io/v1beta1` `Cluster` |
| *(not in the palette)* | `Util.PasswordEntry` | |

Four consequences, worth knowing before any of the detail:

- **Anything the Supervisor understands can go in a blueprint.** The workload
  items are shortcuts. The generic Supervisor Resource takes any manifest the
  namespace accepts. Our lab blueprints rely on a kind the palette doesn't
  offer, `SubnetConnectionBindingMap`, to carry VLANs.
- **The VPC items are a closed list.** `CCI.VPC.Configuration` takes exactly
  the five kinds above. A VPC's load balancer is a sixth kind in VCF
  Automation's VPC API, and a blueprint can't make one (see
  [VPC](#vpc)).
- **VCF Automation validates the outside, the platform the inside.** The
  validation API checks the resource type's own properties: required fields,
  patterns, the namespace's two shapes. It doesn't look inside a `manifest`
  or a `configs[].spec`: in our test, `powerState: Sideways` passed
  validation. Those are checked when the request runs.
- **The designer's schemas are not the platform's.** The palette's forms
  come from schemas bundled with VCF Automation, while the Supervisor and
  the VPC API check against their own. They disagree in a handful of
  places, listed next.

## Where the designer and the platform disagree

We compared each palette item's schema with the platform's definition of the
same `apiVersion` and `kind`. We went field by field (every bit as gripping
as it sounds) and tested every difference:

| Item | The designer offers | What the platform does |
|---|---|---|
| Virtual Machine | `affinity.zoneAffinity`, `affinity.zoneAntiAffinity`, and VM affinity terms named `...IgnoredDuringExecution` | Rejects them as unknown fields. VM affinity and anti-affinity take `requiredDuringSchedulingPreferredDuringExecution` and `preferredDuringSchedulingPreferredDuringExecution`. |
| Virtual Machine | no `linuxPrep.password`, `linuxPrep.scriptText`, `crypto.vTPMMode`, `currentSnapshotName`, or disk options at volume level | Accepts all of them. |
| Virtual Machine | `bootOptions.firmware` as `BIOS` or `EFI`, and `bootOptions.enterBootSetup` | `spec.bootOptions.firmware: Unsupported value: "BIOS": supported values: "bios", "efi"`, and `strict decoding error: unknown field "spec.bootOptions.enterBootSetup"`. |
| Virtual Machine `v1alpha4`, `v1alpha3` | `network.nameServers` | The field is `nameservers`, lower case. |
| Subnet | `regionName`, `ipBlockNames`, `description` | Rejects them. Accepts `vlanConnectionName`, which the designer doesn't show. |
| Persistent Volume Claim | `accessMode` | `strict decoding error: unknown field "spec.accessMode"`. The field is `accessModes`. |
| Kubernetes Cluster | `cluster.x-k8s.io/v1beta1` | Serves it, with `cluster.x-k8s.io/v1beta1 Cluster is deprecated; use cluster.x-k8s.io/v1beta2 Cluster`. |
| Group | `vmSelectors[].selector`, `podSelectors[].selector` | `spec.vmSelectors[0]: Required value: must specify at least one selector`. The field is `labelSelector`; the API also offers `propertySelector`. |
| Gateway Firewall Policy | `ruleCount` | Computed by the API; not accepted. A rule's `from` is required, though the schema says empty means any. |

None of this stops the designer from saving a blueprint. It surfaces when the
request runs.

## What every resource shares

### Properties on every type

| Property | On | What it does |
|---|---|---|
| `count` | all | How many instances to create. Default 1. |
| `allocatePerInstance` | all (beside `type`) | Required for `${count.index}`: without it the validator refuses the blueprint with `should have allocatePerInstance property set to True`. |
| `dependsOn` | all (beside `type`) | Explicit order. A reference to another resource orders the two already. |
| `context` | Supervisor Resource items | **Required.** The namespace the manifest goes into: `${resource.<namespace>.id}`. |
| `existing` | Namespace, Supervisor Resource items | `true` adopts what already exists instead of creating it. |
| `wait` | Supervisor Resource items, VPC Configuration | When the resource counts as done. |

Recipe, two Secrets from one resource:

```yaml
  sec:
    type: CCI.Supervisor.Resource
    allocatePerInstance: true
    properties:
      count: 2
      context: ${resource.ns.id}
      manifest:
        apiVersion: v1
        kind: Secret
        metadata:
          name: ${'ref-s-' + count.index}
        type: Opaque
        stringData:
          note: created by instance ${count.index}
```

The deployment then holds `sec[0]` and `sec[1]`, and the namespace
`ref-s-0` and `ref-s-1`.

### `wait`: when a resource is finished

Without a `wait`, a Supervisor Resource is finished as soon as the Supervisor
accepts the manifest. That's fine for a Secret, and wrong for a VM whose
address an output needs. `wait` takes conditions, fields, or both:

```yaml
      wait:
        conditions:                      # status.conditions[] of the object
          - type: Ready
            status: "True"
          - type: Ready
            status: "False"
            reason: Failed
            indicatesFailure: true       # this one fails the resource instead of finishing it
        fields:                          # any field of the object, by path
          - path: status.powerState
            value: PoweredOn
        skipWaitOnDelete: false          # true: deletion does not wait for the object to be gone
```

A Supervisor Resource can also watch log output with `executionLogs`:
`progressMessagePattern` while a matching message appears, and
`failureMessagePattern` to fail the resource.

The designer pre-fills a `wait` for some items:

| Item | Designer's default `wait` |
|---|---|
| Virtual Machine | condition `VirtualMachineCreated` = `True` |
| Virtual Machine Group | condition `Ready` = `True` |
| NAT Rule, Group | condition `Realized` = `True` |
| everything else | none |

The VM's default came from a 9.0 problem: VM status could come back empty,
and Broadcom's KB 435137 gave this `wait` as the workaround. That condition
is true before the VM is even on, let alone has an address.

VCF Automation also waits by itself in one place: **a Virtual Machine Service
of type `LoadBalancer` is not finished until it has an external address**,
with or without a `wait`. In a VPC without a load balancer, that address
never comes, and the request stays in progress until it times out. Ours was
still `PARTIAL` after ten minutes, with the service `<pending>` on the
Supervisor.

### Reading a resource's live state

Every Supervisor Resource exposes the object as the Supervisor sees it under
`object`, and a VPC Configuration exposes its objects under `configs`:

```yaml
outputs:
  vmIp:
    value: ${resource.vm1.object.status.network.primaryIP4}
  vmHost:
    value: ${resource.vm1.object.status.nodeName}
  lbIp:
    value: ${resource.webLb.object.status.loadBalancer.ingress[0].ip}
  publicIp:
    value: ${resource.publicIp.configs[0].spec.allocationIPs}
```

**Outputs are computed once, when the request finishes**, and not refreshed
afterwards. A VM that waited only for `PoweredOn` finished before its guest
reported an address, and its IP output stayed empty for good. Waiting on the
condition that marks the guest's network as configured fixes it. This one
gave the output `172.30.0.2`:

```yaml
      wait:
        conditions:
          - type: VirtualMachineGuestNetworkConfigSynced
            status: "True"
```

### Checking a manifest before you deploy it

The fastest check we found is a server-side dry run with strict field
validation, against the namespace the blueprint will use:

```text
kubectl apply --dry-run=server --validate=strict -n <namespace> -f vm.yaml
```

It runs the Supervisor's schema checks and admission webhooks, flags unknown
fields, and creates nothing. It works for every workload kind. It does **not**
work for the VPC kinds: VCF Automation's VPC API ignores `dryRun` and creates
the object, as one of our probes found.

## Supervisor Namespace

`type: CCI.Supervisor.Namespace`. Creates a vSphere Namespace through VCF
Automation, inside the project's allocation, or adopts one that exists.
Everything in the Workload group needs one: their `context` points at it.

The schema has two shapes, and the validator enforces them: an existing
namespace takes `name` and `existing: true` and nothing else; a new one needs
`generateName`, `className`, `regionName` and `vpcName`.

| Property | Notes |
|---|---|
| `generateName` | **New namespace.** Prefix; VCF Automation adds `-` and five random characters (`ns-ref-bstk7`). Must match `^[a-z0-9]([-a-z0-9]*[a-z0-9])?$`, so it cannot end in a hyphen. |
| `className` | **New namespace.** The namespace class: limits, VM classes, storage classes and content libraries. |
| `regionName` | **New namespace.** The region. |
| `vpcName` | **New namespace.** The VPC its workloads use: an existing VPC's name, or `${resource.<vpc>.name}`. |
| `name` + `existing: true` | **Existing namespace.** `name` alone matches neither shape. |
| `zones[]` | Per vSphere Zone: `name`, `cpuLimit`, `cpuReservation`, `memoryLimit`, `memoryReservation`, all five required. |
| `storageClasses[]` | `name` (the storage policy as the namespace names it) and `limit`. |
| `vmClasses[]`, `contentSources[]` | VM classes and image sources beyond the class's own. |
| `sharedSubnetNames[]`, `infraPolicyNames[]`, `segName`, `description` | Shared subnets, extra infrastructure policies, an Avi Service Engine Group, a description. |

<!-- FIELDS:namespace -->
{{< collapse summary="Every field the platform accepts (25)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `name` | string |  | e.g. `team-a-dev` | Supervisor namespace name |
| `count` | integer |  | default `1` | The number of resource instances to be created. |
| `zones` | array of object |  | e.g. `[{name: domain-c9, cpuLimit: 4000M}]` | Zone overrides for the namespace |
| `zones[].name` | string | yes | e.g. `domain-c9` | Name of the zone |
| `zones[].cpuLimit` | string | yes | e.g. `4000M` | CPU limit in M or G |
| `zones[].memoryLimit` | string | yes | e.g. `8192Mi` | Memory limit in Mi, Gi, or Ti |
| `zones[].cpuReservation` | string | yes | e.g. `0M` | CPU reservation in M or G |
| `zones[].memoryReservation` | string | yes | e.g. `0Mi` | Memory reservation in Mi, Gi, or Ti |
| `segName` | string |  | e.g. `Default-Group` | Name of the Service Engine Group |
| `vpcName` | string |  | e.g. `vpc-student05` | Name of the vpc |
| `existing` | boolean |  | default `false` | Use existing supervisor namespace |
| `className` | string |  | e.g. `nested-pod` | Name of the supervisor namespace class |
| `vmClasses` | array of object |  | e.g. `[{name: best-effort-small}]` | VM Class overrides for the namespace |
| `vmClasses[].name` | string | yes | e.g. `best-effort-small` | Name of the vm class |
| `regionName` | string |  | e.g. `f06` | Name of the region |
| `description` | string |  | e.g. `Team sandbox` | Description of the supervisor namespace |
| `generateName` | string |  | e.g. `ns-demo` | Supervisor namespace generateName |
| `contentSources` | array of object |  | e.g. `[{name: my-library, type: ContentLibrary}]` | Content Source overrides for the namespace |
| `contentSources[].name` | string | yes | e.g. `my-library` | Name of the content source |
| `contentSources[].type` | string | yes | default `ContentLibrary` | Type of the content source |
| `storageClasses` | array of object |  | e.g. `[{name: vSAN Default Storage Policy, limit: 100Gi}]` | Storage Class overrides for the namespace |
| `storageClasses[].name` | string | yes | e.g. `vSAN Default Storage Policy` | Name of the storage class |
| `storageClasses[].limit` | string | yes | e.g. `100Gi` | Storage Class limit in Mi, Gi, or Ti |
| `infraPolicyNames` | array of string |  | e.g. `[<infrastructure policy>]` | Non-mandatory Infra Policy names |
| `sharedSubnetNames` | array of string |  | e.g. `[<shared subnet>]` | Name of subnets |
{{< /collapse >}}
<!-- /FIELDS:namespace -->

Minimal, a new namespace with the zone and storage our class doesn't set:

```yaml
  namespace:
    type: CCI.Supervisor.Namespace
    properties:
      generateName: ns-demo
      className: nested-pod
      regionName: f06
      vpcName: vpc-student05
      storageClasses:
        - name: vSAN Default Storage Policy
          limit: 100Gi
      zones:
        - name: domain-c9
          cpuLimit: 4000M
          cpuReservation: 0M
          memoryLimit: 8192Mi
          memoryReservation: 0Mi
```

**Recipes**

- *A quota sized from the request*, so a namespace never outgrows what was
  asked for. Our lab blueprints compute the limits from the requested sizes:

  ```yaml
      storageClasses:
        - name: vSAN Default Storage Policy
          limit: "${input.hosts * 200 + 'Gi'}"
      zones:
        - name: domain-c9
          cpuLimit: "${input.hosts * 8000 + 'M'}"
          cpuReservation: 0M
          memoryLimit: "${input.hosts * 32768 + 'Mi'}"
          memoryReservation: 0Mi
  ```

- *Deploy into a namespace that already exists*, for example one an
  administrator prepared:

  ```yaml
  namespace:
    type: CCI.Supervisor.Namespace
    properties:
      name: team-a-dev
      existing: true
  ```

**Status worth reading:** `${resource.<ns>.id}` is
`cci:<project>:<namespace>`, which `context` takes.

**Gotchas**

- Whether `zones` and `storageClasses` are optional depends on the namespace
  class. Ours sets neither, and VCF Automation refused the minimal shape in
  turn: `Zone should be specified in Namespace or in Namespace class`, then
  `Storage Class should be specified in Namespace or in Namespace class`.
- The zone `name` is the vSphere Zone. A Supervisor without zones still has
  one, named after its cluster (`domain-c9` on f06).
- A VM can only use a VM class the namespace allows and an image from its
  content sources. The validator cannot know either; the request finds out.

## VPC

`type: CCI.VPC`. Creates an NSX VPC in a region. Most blueprints use an
existing VPC, through the namespace's `vpcName`. This item is for a
blueprint that brings its own network.

| Property | Notes |
|---|---|
| `generateName` | **Required.** VCF Automation names the VPC `<generateName>-<project>-<5 characters>`: `vpc-ref-default-project-y3698`. |
| `regionName` | **Required.** The region. |
| `privateIPs[]` | The VPC's private CIDRs. Empty uses the project's default. |

<!-- FIELDS:vpc -->
{{< collapse summary="Every field the platform accepts (4)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `count` | integer |  | default `1` | The number of resource instances to be created. |
| `privateIPs` | array of string |  | e.g. `[10.200.0.0/20]` | List of private IPs to be used in the VPC |
| `regionName` | string | yes | e.g. `f06` | Region name for the VPC |
| `generateName` | string | yes | e.g. `vpc-app` | Prefix for the generated name of the VPC |
{{< /collapse >}}
<!-- /FIELDS:vpc -->

```yaml
  vpc:
    type: CCI.VPC
    properties:
      generateName: vpc-app
      regionName: f06
      privateIPs:
        - 10.200.0.0/20
```

**Status worth reading:** `id` (`cci:vpc:<project>:<name>`), which every VPC
Configuration takes as `vpc`, and `name`, which a namespace takes as
`vpcName`.

**Gotchas**

- A new VPC reaches nothing outside itself until it has an
  [Attachment](#attachment) to a VPC connectivity profile; give the namespace
  `dependsOn` on the attachment.
- `privateIPs` must not overlap the connectivity profile's Private Transit
  Gateway blocks, and the error only comes at attachment time: `private IP
  CIDR 172.31.64.0/20 overlaps with private TGW IP block CIDR 172.31.0.0/16`.
- **A blueprint cannot give its VPC a load balancer.** In VCF Automation's
  VPC API the load balancer is its own kind, `LoadBalancer`, and
  `CCI.VPC.Configuration` refuses it: `Failed to match exactly one schema
  (matched 0 out of 5)`. Without one, a LoadBalancer service never gets an
  address (and its request never finishes, see [`wait`](#wait-when-a-resource-is-finished)),
  and Broadcom's VPC page warns that a VPC without load balancing cannot run
  VKS. For either, use a VPC made in the UI with **Enable load balancing**
  on, and name it in the namespace's `vpcName`.

## VPC Configuration

`type: CCI.VPC.Configuration`. One item for every object that lives inside a
VPC, and `kind` chooses which. The five palette entries below are this item
with `kind` filled in. Each `configs[]` entry becomes one object, so one
resource can create several rules or groups of the same kind.

| Property | Notes |
|---|---|
| `vpc` | **Required.** The VPC's id: `${resource.vpc.id}`, or an existing VPC's `cci:vpc:<project>:<name>`. |
| `kind` | **Required.** `VPCAttachment`, `VPCIPAddressAllocation`, `VPCNATRule`, `VPCNetworkSecurityGroup` or `VPCGatewayFirewallPolicy`, and nothing else. |
| `apiVersion` | `vpc.nsx.vmware.com/v1alpha1`. |
| `configs[]` | **Required.** Per object: `generateName` (**required**), `spec`, `labels`, `annotations`. |
| `wait` | Applies to every object in `configs`. |

<!-- FIELDS:vpc-configuration -->
{{< collapse summary="Every field the platform accepts (20)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `vpc` | string | yes | e.g. `${resource.vpc.id}` | ID of the parent VPC this resource is associated with. |
| `kind` | string | yes | e.g. `VPCNATRule` | The kind of the resource (e.g., VPCNetworkSecurityGroup, VPCIPAddressAllocation, VPCNATRule, VPCAttachment). |
| `wait` | object |  | e.g. `{fields: [{path: status.conditions[0].status, value: True}], ...}` | Wait conditions applied to all config resources. All resources must satisfy these conditions before the operation is considered complete. |
| `wait.fields` | array of object |  | e.g. `[{path: status.conditions[0].status, value: True}]` | List of field conditions to wait for. |
| `wait.fields[].path` | string | yes | e.g. `status.conditions[0].status` | JSONPath to the field to check (e.g., status.phase). |
| `wait.fields[].value` | string | yes | e.g. `True` | The expected value of the field. Use '*' for any non-null value. |
| `wait.fields[].indicatesFailure` | boolean |  | default `false` | Whether this field condition indicates a failure state. |
| `wait.conditions` | array of object |  | e.g. `[{type: Realized, reason: <condition reason>}]` | List of status conditions to wait for. |
| `wait.conditions[].type` | string | yes | e.g. `Realized` | The type of the condition (e.g., Ready, Realized). |
| `wait.conditions[].reason` | string |  | e.g. `<condition reason>` | Optional reason for the condition. |
| `wait.conditions[].status` | string | yes | e.g. `True` | The expected status of the condition (e.g., True, False). |
| `wait.conditions[].indicatesFailure` | boolean |  | default `false` | Whether this condition indicates a failure state. |
| `wait.skipWaitOnDelete` | boolean |  | default `false` | Whether to skip waiting for conditions during delete operations. |
| `count` | integer |  | default `1` | The number of resource instances to be created. |
| `configs` | array of object | yes | e.g. `[{generateName: dnat-web, spec: {action: DNAT, translatedNetwork: 10.200.0.10}}]` | List of resources associated with the VPC. |
| `configs[].spec` | object |  | e.g. `{action: DNAT, translatedNetwork: 10.200.0.10}` | The specification of the associated resource. |
| `configs[].labels` | object |  | e.g. `{app: web}` | Labels for categorizing the resource. |
| `configs[].annotations` | object |  | e.g. `{owner: team-a}` | Annotations for additional metadata about the resource. |
| `configs[].generateName` | string | yes | e.g. `dnat-web` | A prefix for generating a unique name for the resource. |
| `apiVersion` | string |  | e.g. `vpc.nsx.vmware.com/v1alpha1` | The API version of the resource. |
{{< /collapse >}}
<!-- /FIELDS:vpc-configuration -->

Three things hold for all five kinds:

- **`generateName` is the name, not a prefix.** VCF Automation names the
  object `<vpc>:<generateName>`, as written: our group was
  `vpc-ref-default-project-y3698:web`. Keep it unique per kind in the VPC.
- **VCF Automation fills in `spec.vpcName` and `spec.regionName`** from the
  `vpc` property; leave them out.
- **Another resource reads an object as `configs[n]`**:
  `${resource.webGroup.configs[0].name}` is the full name a firewall rule
  needs, and `${resource.publicIp.configs[0].spec.allocationIPs}` is the
  address an allocation got.

The shape, for every kind:

```yaml
  natRules:
    type: CCI.VPC.Configuration
    properties:
      vpc: ${resource.vpc.id}
      apiVersion: vpc.nsx.vmware.com/v1alpha1
      kind: VPCNATRule
      configs:
        - generateName: dnat-web
          spec: { ... }
        - generateName: dnat-ssh
          spec: { ... }
```

### Attachment

`kind: VPCAttachment`. Attaches the VPC to a VPC connectivity profile, which
decides its transit gateway, its external IP blocks and whether it gets a
default outbound NAT.

| `spec` field | Notes |
|---|---|
| `vpcConnectivityProfileName` | **Required.** The profile, as NSX names it (f06's is `default--f06`). |
| `preferredDefaultSNATIP` | The address for the VPC's automatic SNAT. It must be free in the external block; empty lets NSX choose. |

<!-- FIELDS:attachment -->
{{< collapse summary="Every field the platform accepts (2)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.preferredDefaultSNATIP` | string |  | e.g. `192.168.144.30` | PreferredDefaultSNATIP specifies the translated IP for VPC auto SNAT rules. The specified IP must be available. |
| `spec.vpcConnectivityProfileName` | string | yes | e.g. `default--f06` | VPCConnectivityProfileName specifies the name of the VPC Connectivity Profile associated with the VPC. |
{{< /collapse >}}
<!-- /FIELDS:attachment -->

```yaml
  attach:
    type: CCI.VPC.Configuration
    properties:
      vpc: ${resource.vpc.id}
      apiVersion: vpc.nsx.vmware.com/v1alpha1
      kind: VPCAttachment
      configs:
        - generateName: attach
          spec:
            vpcConnectivityProfileName: default--f06
```

With the attachment realized, NSX adds the VPC's default SNAT rule and its
address by itself (ours: `10.200.0.0/20` to `192.168.144.14`).

### IP Address Allocation

`kind: VPCIPAddressAllocation`. Reserves addresses from one of the VPC's IP
blocks, typically an external address for a NAT rule.

| `spec` field | Notes |
|---|---|
| `ipAddressBlockVisibility` | `Private` (default), `PrivateTGW` or `External`. The NSX API's own default is `External`. |
| `allocationSize` | How many addresses, a power of 2. Either this or `allocationIPs`. |
| `allocationIPs` | Specific addresses, as a CIDR (`192.168.0.1/32`). |
| `ipBlockName` | A particular block, when the visibility has more than one. |

<!-- FIELDS:ip-allocation -->
{{< collapse summary="Every field the platform accepts (4)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.allocationIPs` | string |  | e.g. `192.168.144.18` | The specific IP addresses from IPBlock that needs to be requested. If specified, it should be passed like 192.168.0.0/24 or 192.168.0.1/32. |
| `spec.allocationSize` | integer |  | e.g. `1` | Allocation IP address size for auto allocating IPs from IPBlock. The IP addresses will be auto allocated from unused IP addresses based on allocation size. |
| `spec.ipAddressBlockVisibility` | string |  | e.g. `External` | Visibility of IP address block. Must be External, Private or PrivateTGW. Note: the default Private Visibility is different from NSX API's default External Visibility. |
| `spec.ipBlockName` | string |  | e.g. `:f06-vpc-ext02` | IPBlock name for allocating IP address. |
{{< /collapse >}}
<!-- /FIELDS:ip-allocation -->

```yaml
  publicIp:
    type: CCI.VPC.Configuration
    dependsOn: [attach]
    properties:
      vpc: ${resource.vpc.id}
      apiVersion: vpc.nsx.vmware.com/v1alpha1
      kind: VPCIPAddressAllocation
      configs:
        - generateName: web-ip
          spec:
            ipAddressBlockVisibility: External
            allocationSize: 1
```

The allocated address appears in the object's own spec:
`${resource.publicIp.configs[0].spec.allocationIPs}` gave `192.168.144.18`.
An external allocation needs the attachment first, hence the `dependsOn`.

### NAT Rule

`kind: VPCNATRule`. A NAT rule on the VPC's gateway. The designer's default
`wait` is `Realized`.

| `spec` field | Notes |
|---|---|
| `action` | **Required.** `SNAT`, `DNAT`, `Reflexive`, `NoSNAT` or `NoDNAT`. |
| `translatedNetwork` | **Required.** For SNAT, one address from the VPC's external block. |
| `sourceNetwork` | One address, a comma-separated list, or a CIDR. Mandatory for SNAT. |
| `destinationNetwork` | One address; empty means any. |
| `serviceEntry` | `protocol` (`TCP`, `UDP`, `ICMP`), `sourcePorts`, `destinationPorts`, `translatedPorts`. See the warning. |
| `sequenceNumber` | Priority, default 0. |
| `firewallMatch` | `MatchInternalAddress` (default), `MatchExternalAddress` or `ByPass`. |
| `enabled`, `logging` | Defaults `true` and `false`. |

<!-- FIELDS:nat-rule -->
{{< collapse summary="Every field the platform accepts (13)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.action` | string | yes | e.g. `DNAT` | Action represents action of NAT Rule. Valid values: SNAT, DNAT, Reflexive, NoSNAT and NoDNAT. |
| `spec.destinationNetwork` | string |  | e.g. `192.168.144.18` | DestinationNetwork represents the destination network. The value can be a single IPv4 address or CIDR, or a comma separated list of IPv4 addresses. |
| `spec.enabled` | boolean |  | e.g. `true` | NAT Rule enabled flag Enabled indicates whether the NAT rule is enabled or disabled. The default is True. |
| `spec.firewallMatch` | string |  | e.g. `MATCH_INTERNAL_ADDRESS` | FirewallMatch indicates how the firewall matches the address after NATing if firewall stage is not skipped. |
| `spec.logging` | boolean |  | e.g. `true` | NAT Rule logging flag Logging indicates whether the logging of NAT rule is enabled or disabled. The default is False. |
| `spec.sequenceNumber` | integer |  | default `0` | SequenceNumber decides the priority of a NAT rule. Valid range is [0, 2147481599]. Default is 0. |
| `spec.serviceEntry` | object |  | e.g. `{destinationPorts: "22", protocol: TCP}` |  |
| `spec.serviceEntry.destinationPorts` | string |  | e.g. `"22"` | The destination ports to match. If specified, it must be either a single port (e.g. "8080") or a port range (e.g. "8090-8095"). |
| `spec.serviceEntry.protocol` | string | yes | e.g. `TCP` | Protocol supports TCP, UDP and ICMP v4. |
| `spec.serviceEntry.sourcePorts` | string |  | e.g. `1024-65535` | The source ports to match. If specified, it must be either a single port (e.g. "8080") or a port range (e.g. "8090-8095"). |
| `spec.serviceEntry.translatedPorts` | string |  | e.g. `"2222"` | The translated ports. If specified, it must be either a single port (e.g. "8080") or a port range (e.g. "8090-8095"). |
| `spec.sourceNetwork` | string |  | e.g. `10.200.0.0/28` | SourceNetwork represents the source network address. The value can be a single IPv4 address or CIDR, or a comma separated list of IPv4 addresses. |
| `spec.translatedNetwork` | string | yes | e.g. `10.200.0.10` | TranslatedNetwork represents the translated network address. The field is required and must contain a single IPv4 address for SNAT, DNAT and Reflexive. |
{{< /collapse >}}
<!-- /FIELDS:nat-rule -->

```yaml
  dnatSsh:
    type: CCI.VPC.Configuration
    properties:
      vpc: ${resource.vpc.id}
      apiVersion: vpc.nsx.vmware.com/v1alpha1
      kind: VPCNATRule
      configs:
        - generateName: dnat-ssh
          spec:
            action: DNAT
            destinationNetwork: ${resource.publicIp.configs[0].spec.allocationIPs}
            translatedNetwork: 10.200.0.10
            serviceEntry:
              protocol: TCP
              destinationPorts: "22"
```

**Warning: the port did not reach NSX.** VCF Automation's API kept the
`serviceEntry` (TCP 22), but the rule NSX realized had `service: null`: a
DNAT of every port on `192.168.144.18` to the private address. Treat a NAT
rule as a whole-address mapping. To publish one port, use a
[Virtual Machine Service](#virtual-machine-service) of type `LoadBalancer`,
which forwards only its ports and follows the VM's address.

### Group

`kind: VPCNetworkSecurityGroup`. A group of addresses, VMs or pods that
firewall rules can name. Default `wait`: `Realized`.

| `spec` field | Notes |
|---|---|
| `ipAddresses[]` | Addresses, ranges or CIDRs. |
| `vmSelectors[]` | `labelSelector` (VMs by label, so new VMs with the label join), `namespaceSelector`, and `propertySelector` (VMs by `Name`, `OSName` or `ComputerName`, with `Equals`, `Contains`, `StartsWith`, `EndsWith`, `NotEquals`). |
| `podSelectors[]` | `labelSelector` and `namespaceSelector` for pods. |
| `vms[]` | Specific VMs, by `instanceUUID`. |
| `vpcNetworkSecurityGroupNames[]` | Other groups, nested. |

<!-- FIELDS:group -->
{{< collapse summary="Every field the platform accepts (35)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.ipAddresses` | array of string |  | e.g. `[10.200.0.0/28]` | List of IPs or CIDRs to be included in this VPCNetworkSecurityGroup. Each entry can be a single IP address, an IP range, or a subnet in CIDR notation. |
| `spec.podSelectors` | array of object |  | e.g. `[{labelSelector: {matchLabels: {app: web}}, ...}]` | List of Pod label selectors that will dynamically select Pods to include in this VPCNetworkSecurityGroup. |
| `spec.podSelectors[].labelSelector` | object |  | e.g. `{matchLabels: {app: web}}` | A label selector is a label query over a set of resources. The result of matchLabels and matchExpressions are ANDed. |
| `spec.podSelectors[].labelSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.podSelectors[].labelSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.podSelectors[].labelSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.podSelectors[].labelSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.podSelectors[].labelSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.podSelectors[].namespaceSelector` | object |  | e.g. `{matchExpressions: [{key: app, operator: In}], matchLabels: {app: web}}` | A label selector is a label query over a set of resources. The result of matchLabels and matchExpressions are ANDed. |
| `spec.podSelectors[].namespaceSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.podSelectors[].namespaceSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.podSelectors[].namespaceSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.podSelectors[].namespaceSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.podSelectors[].namespaceSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.vmSelectors` | array of object |  | e.g. `[{labelSelector: {matchLabels: {app: web}}, ...}]` | List of Virtual Machine label selectors that will dynamically select VMs to include in this VPCNetworkSecurityGroup. |
| `spec.vmSelectors[].labelSelector` | object |  | e.g. `{matchLabels: {app: web}}` | A label selector is a label query over a set of resources. The result of matchLabels and matchExpressions are ANDed. |
| `spec.vmSelectors[].labelSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.vmSelectors[].labelSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.vmSelectors[].labelSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.vmSelectors[].labelSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.vmSelectors[].labelSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.vmSelectors[].namespaceSelector` | object |  | e.g. `{matchExpressions: [{key: app, operator: In}], matchLabels: {app: web}}` | A label selector is a label query over a set of resources. The result of matchLabels and matchExpressions are ANDed. |
| `spec.vmSelectors[].namespaceSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.vmSelectors[].namespaceSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.vmSelectors[].namespaceSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.vmSelectors[].namespaceSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.vmSelectors[].namespaceSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.vmSelectors[].propertySelector` | object |  | e.g. `{matchExpressions: [{key: Name, operator: StartsWith}]}` | PropertySelector represents a set of conditions on VM properties. All MatchExpressions are ANDed; a VM must satisfy all expressions to match. |
| `spec.vmSelectors[].propertySelector.matchExpressions` | array of object |  | e.g. `[{key: Name, operator: StartsWith}]` | MatchExpressions is a list of property selector requirements. Each requirement consists of a key, operator, and value. |
| `spec.vmSelectors[].propertySelector.matchExpressions[].key` | string | yes | e.g. `Name` | Key is the VM property to match. Valid keys are Name, OSName and ComputerName. |
| `spec.vmSelectors[].propertySelector.matchExpressions[].operator` | string | yes | e.g. `StartsWith` | Operator defines how the Key is compared against Value. Valid operators are Equals, Contains, StartsWith, EndsWith and NotEquals. |
| `spec.vmSelectors[].propertySelector.matchExpressions[].value` | string | yes | e.g. `web-` | Value is the target value to match against the VM property. |
| `spec.vms` | array of object |  | e.g. `[{instanceUUID: 5010c9b4-1f2e-4d3c-8b7a-6e5f4d3c2b1a}]` | List of Virtual Machine references that will be included in this VPCNetworkSecurityGroup. |
| `spec.vms[].instanceUUID` | string | yes | e.g. `5010c9b4-1f2e-4d3c-8b7a-6e5f4d3c2b1a` | InstanceUUID of the VM being referenced. |
| `spec.vpcNetworkSecurityGroupNames` | array of string |  | e.g. `[db-servers]` | List of VPCNetworkSecurityGroup names that will be included in this VPCNetworkSecurityGroup. |
{{< /collapse >}}
<!-- /FIELDS:group -->

```yaml
  webGroup:
    type: CCI.VPC.Configuration
    properties:
      vpc: ${resource.vpc.id}
      apiVersion: vpc.nsx.vmware.com/v1alpha1
      kind: VPCNetworkSecurityGroup
      configs:
        - generateName: web
          spec:
            vmSelectors:
              - labelSelector:
                  matchLabels: {tier: web}
```

Every VPC also has a group named `default`, made by NSX.

### Gateway Firewall Policy

`kind: VPCGatewayFirewallPolicy`. Rules on the VPC's gateway, for traffic
entering and leaving the VPC. The distributed firewall inside the VPC is a
separate thing.

| `spec` field | Notes |
|---|---|
| `rules[]` | Per rule: `name` (unique in the policy), `action` (`Allow` default, `Drop`, `Reject`, `JumpToApplication`), `direction` (`InOut` default, `In`, `Out`), `from[]` and `to[]` (each entry `groupName` or `ipAddress`), `services[]` (`networkServiceName`, or `l4PortSet` with `l4Protocol`, `destinationPorts`, `sourcePorts`), `ipProtocol`, `log`, `disabled`, `notes`, `tag`, `sourcesExcluded`, `destinationsExcluded`, `appliedTo`. |
| `category` | `LocalGatewayRules` (default) or `Default`. |
| `priority` | Order against other policies, default 0. |
| `stateful`, `tcpStrict` | Stateful inspection; a full TCP handshake before data. |
| `description`, `locked` | |

<!-- FIELDS:gateway-firewall -->
{{< collapse summary="Every field the platform accepts (35)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.category` | string |  | e.g. `LocalGatewayRules` | Pre-defined categories for classifying a VPC Gateway Firewall policy.There are two pre-defined categories. They are "LocalGatewayRules" and "Default". |
| `spec.description` | string |  | e.g. `Inbound HTTPS` | Description for the firewall policy. |
| `spec.isDefault` | boolean |  | default `false` | A flag to indicate whether rule is a default rule |
| `spec.locked` | boolean |  | default `false` | Locked indicates whether a security policy should be locked |
| `spec.priority` | integer |  | default `0` | This field is used to resolve conflicts between multiple Rules under Security or Gateway Policy for a Domain. If no priority is specified in the payload, a value of 0 is assigned by default. |
| `spec.rules` | array of object |  | e.g. `[{action: Allow, name: https-in}]` | Rules that are a part of this FirewallPolicy |
| `spec.rules[].action` | string |  | e.g. `Allow` | Action to be applied to all the services |
| `spec.rules[].appliedTo` | object |  | e.g. `{gatewayAttachmentNames: [<transit gateway attachment>], ...}` |  |
| `spec.rules[].appliedTo.gatewayAttachmentNames` | array of string |  | e.g. `[<transit gateway attachment>]` | This field is only applicable when the rule is defined for Transit Gateway Firewall policy |
| `spec.rules[].appliedTo.gatewayNames` | array of string |  | e.g. `[<transit gateway>]` | This field is only applicable when the rule is defined for Transit Gateway Firewall policy |
| `spec.rules[].appliedTo.groupNames` | array of string |  | e.g. `[<group>]` | This field is only applicable when the rule is defined for Distributed Firewall policy |
| `spec.rules[].destinationsExcluded` | boolean |  | e.g. `true` | DestinationsExcluded indicates that the rule applies to all destinations *except* those specified in the 'To' field. |
| `spec.rules[].direction` | string |  | e.g. `In` | Direction defines direction of traffic. |
| `spec.rules[].disabled` | boolean |  | default `false` | Disabled indicates if the rule is enabled/disabled. |
| `spec.rules[].from` | array of object |  | e.g. `[{ipAddress: 0.0.0.0/0, groupName: admin-hosts}]` | From defines the source of the traffic. If empty, it defaults to "Any", matching all sources. |
| `spec.rules[].from[].groupName` | string |  | e.g. `admin-hosts` |  |
| `spec.rules[].from[].ipAddress` | string |  | e.g. `0.0.0.0/0` |  |
| `spec.rules[].ipProtocol` | string |  | e.g. `IPV4` | IpProtocol indicates type of IP packet that should be matched while enforcing the rule. Only IPV_4 protocol is supported for new rules, IPV4_IPV6 is only allowed for default rules. |
| `spec.rules[].isDefault` | boolean |  | default `false` | IsDefault is a flag to indicate whether rule is a default rule. |
| `spec.rules[].log` | boolean |  | e.g. `true` | Log indicates if traffic matching this rule should be logged. |
| `spec.rules[].name` | string | yes | e.g. `https-in` | Name for the rule. Must be unique within the policy. |
| `spec.rules[].notes` | string |  | e.g. `HTTPS from anywhere` | Notes for the rule. |
| `spec.rules[].services` | array of object |  | e.g. `[{l4PortSet: {destinationPorts: [443], l4Protocol: TCP}, networkServiceName: :HTTPS}]` | Services specifies the network services (protocols and ports) to which this rule applies. If empty or null ,it defaults to "Any" , then this rule applies to all services. |
| `spec.rules[].services[].l4PortSet` | object |  | e.g. `{destinationPorts: [443], l4Protocol: TCP}` | L4PortSetServiceEntry is a ServiceEntry that represents TCP or UDP protocol. |
| `spec.rules[].services[].l4PortSet.destinationPorts` | array of string |  | e.g. `[443]` | DestinationPorts defines the destination port or port range to match. For example: ["443"], ["8080-8090"]. If empty, matches any destination port. |
| `spec.rules[].services[].l4PortSet.l4Protocol` | string | yes | e.g. `TCP` | L4Protocol specifies the Layer 4 protocol (TCP or UDP). |
| `spec.rules[].services[].l4PortSet.sourcePorts` | array of string |  | e.g. `[1000-2000]` | SourcePorts defines the source port or port range to match. For example: ["80"], ["1000-2000"]. If empty, matches any source port. |
| `spec.rules[].services[].networkServiceName` | string |  | e.g. `:HTTPS` |  |
| `spec.rules[].sourcesExcluded` | boolean |  | e.g. `true` | SourcesExcluded indicates that the rule applies to all sources *except* those specified in the 'From' field. When true, the 'From' field acts as an exclusion list. |
| `spec.rules[].tag` | string |  | e.g. `web` | Tag applied on the rule. |
| `spec.rules[].to` | array of object |  | e.g. `[{groupName: ${resource.webGroup.configs[0].name}, ipAddress: 10.200.0.10}]` | To defines the destination of the traffic. If empty, it defaults to "Any", matching all destinations. |
| `spec.rules[].to[].groupName` | string |  | e.g. `${resource.webGroup.configs[0].name}` |  |
| `spec.rules[].to[].ipAddress` | string |  | e.g. `10.200.0.10` |  |
| `spec.stateful` | boolean |  | default `false` | Stateful or Stateless nature of security policy is enforced on all rules in this security policy. |
| `spec.tcpStrict` | boolean |  | default `false` | Ensures that a 3 way TCP handshake is done before the data packets are sent. tcp_strict=true is supported only for stateful security policies. |
{{< /collapse >}}
<!-- /FIELDS:gateway-firewall -->

Recipe, HTTPS from anywhere to the web group:

```yaml
  gwPolicy:
    type: CCI.VPC.Configuration
    dependsOn: [attach]
    properties:
      vpc: ${resource.vpc.id}
      apiVersion: vpc.nsx.vmware.com/v1alpha1
      kind: VPCGatewayFirewallPolicy
      configs:
        - generateName: web-in
          spec:
            stateful: true
            rules:
              - name: https-in
                action: Allow
                direction: In
                from:
                  - ipAddress: 0.0.0.0/0
                to:
                  - groupName: ${resource.webGroup.configs[0].name}
                services:
                  - networkServiceName: ":HTTPS"
```

**Gotchas**

- **`from` is required**, whatever the field's description says: without it,
  `spec.rules[0].from: Required value`. Write `0.0.0.0/0` for any source.
- **Name a service rather than a port set.** A rule that lists only an
  `l4PortSet` gets `networkServiceName: Any` added by the API, and NSX
  realizes it as services `ANY` beside the raw TCP 443 entry. With
  `networkServiceName: ":HTTPS"` NSX holds exactly `/infra/services/HTTPS`.
  The API lists 415 services, all with a leading colon (`:DNS`, `:HTTPS`,
  `:SSH`); without the colon it refuses: `Network service name must start
  with a colon (:), such as :HTTP`.
- `groupName` takes the group's full name, `<vpc>:<generateName>`, which
  `configs[0].name` supplies.
- The gateway firewall has to be active in the VPC's security profile for any
  of this to be enforced.

## Supervisor Resource

`type: CCI.Supervisor.Resource`. Any Kubernetes object in the namespace,
described by `manifest`. Every workload item that follows is this type with
`apiVersion` and `kind` filled in, so everything here applies to them.

| Property | Notes |
|---|---|
| `context` | **Required.** `${resource.<namespace>.id}`. |
| `manifest` | **Required.** The object: `apiVersion`, `kind`, `metadata`, `spec`. A change to `manifest` or `context` recreates the object. |
| `wait` | As above. |
| `existing` | `true` adopts an object that already exists. |
| `object` | Computed: the live object. |

<!-- FIELDS:supervisor-resource -->
{{< collapse summary="Every field the platform accepts (18)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `wait` | object |  | e.g. `{fields: [{path: status.powerState, value: PoweredOn}], ...}` | resource yaml |
| `wait.fields` | array of object |  | e.g. `[{path: status.powerState, value: PoweredOn}]` | List of fields for whose value needs to be waited for resource to be finished |
| `wait.fields[].path` | string | yes | e.g. `status.powerState` | The path of the field within the Kubernetes resource |
| `wait.fields[].value` | string | yes | e.g. `PoweredOn` | The value that needs to be met for the wait to be finished. |
| `wait.fields[].indicatesFailure` | boolean |  | e.g. `true` | When the condition is met, indicates failure if set to true |
| `wait.conditions` | array of object |  | e.g. `[{type: VirtualMachineGuestNetworkConfigSynced, status: True}]` | List of conditions that indicate success/failure of resource |
| `wait.conditions[].type` | string | yes | e.g. `VirtualMachineGuestNetworkConfigSynced` | The condition type for which to wait |
| `wait.conditions[].reason` | string |  | e.g. `<condition reason>` | The condition reason for which to wait |
| `wait.conditions[].status` | string | yes | e.g. `True` | The value of the condition that needs to be met |
| `wait.conditions[].indicatesFailure` | boolean |  | e.g. `true` | When the condition is met, indicates failure if set to true |
| `wait.executionLogs` | object |  | e.g. `{failureMessagePattern: (?i)error, progressMessagePattern: (?i)creating}` | The message to fetch from the logs while the resource is being created. This is only supported for Kubernetes Jobs. |
| `wait.executionLogs.failureMessagePattern` | string |  | e.g. `(?i)error` | The message pattern to check for to fail the resource creation. If the message is found in the logs, the resource creation will be marked as failed. |
| `wait.executionLogs.progressMessagePattern` | string | yes | e.g. `(?i)creating` | The message pattern to check for to indicate that the resource creation is in progress. If the message is found in the logs, it will be shown as part of the deployment. |
| `wait.skipWaitOnDelete` | boolean |  | e.g. `true` | If false, do not wait for resources to be gone before completing |
| `count` | integer |  | default `1` | The number of resource instances to be created. |
| `context` | string | yes | e.g. `${resource.namespace.id}` | The CCI.Supervisor.Namespace resource id |
| `existing` | boolean |  | default `false` | Use existing supervisor namespace |
| `manifest` | object | yes | e.g. `{apiVersion: vmoperator.vmware.com/v1alpha5, kind: VirtualMachine, spec: ...}` | The yaml representation of the Kubernetes resource |
{{< /collapse >}}
<!-- /FIELDS:supervisor-resource -->

Recipe, a kind the palette doesn't have. Our labs carry three VLANs over one
trunk subnet with binding maps:

```yaml
  bmMgmt:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: crd.nsx.vmware.com/v1alpha1
        kind: SubnetConnectionBindingMap
        metadata: {name: bm-mgmt}
        spec: {subnetName: sn-mgmt, targetSubnetName: sn-trunk, vlanTrafficTag: 1610}
```

On the 9.1 Supervisor the namespace's API also offers, among others,
`VirtualMachineReplicaSet`, `VirtualMachineSnapshot`, `VirtualMachineImage`,
`SubnetSet`, `ConfigMap` and, with Avi, the Gateway API kinds.

**Gotchas**

- `manifest` can be a string as well as a map. Our generator writes one per
  host as a string, because a VM with optional sections is easier to build as
  text: `manifest: "${...}"` works as long as the expression returns valid
  YAML.
- Broadcom's day-2 page warns that bindings don't work for Supervisor
  Resources in day-2 operations; a day-2 action has to take the resource as
  an input.

## Virtual Machine

`CCI.Supervisor.Resource` with `apiVersion: vmoperator.vmware.com/v1alpha5`,
`kind: VirtualMachine`. A VM Service VM: built from a VM class (CPU, memory,
devices) and an image, and configured on first boot by cloud-init, Sysprep,
LinuxPrep or vApp properties.

The most used fields; the complete list of 266 follows.

| `spec` field | Notes |
|---|---|
| `className` | The VM class. Changing it later resizes the VM. |
| `imageName` | The image: its resource name (`vmi-0f0136a489b21d06c`) or its display name (`ubuntu-24.04-server-cloudimg-amd64`), if that is unique among the namespace's and the cluster's images. |
| `storageClass` | The storage class for the VM's disks. |
| `powerState` | `PoweredOn` (default), `PoweredOff`, `Suspended`. |
| `guestID` | The guest OS identifier. **Required when the VM has a CD-ROM.** Immutable while powered on. |
| `network` | `hostName`, `domainName`, `nameservers`, `searchDomains`, `disabled`, and `interfaces[]`: `name` (required), `network` (a Subnet or SubnetSet), `addresses[]`, `gateway4`, `dhcp4`, `mtu`, `routes[]`, `nameservers[]`, `searchDomains[]`, `guestDeviceName`, `macAddr`. Without `interfaces`, the VM joins the namespace's default network. |
| `bootstrap` | One of `cloudInit` (inline `cloudConfig`, `rawCloudConfig` from a Secret, `sshAuthorizedKeys`), `sysprep` (inline or `rawSysprep` from a Secret), `linuxPrep` (`timeZone`, `hardwareClockIsUTC`, `password`, `scriptText`), `vAppConfig` (`properties`, `rawProperties`). |
| `volumes[]` | Extra disks from Persistent Volume Claims: `name`, `persistentVolumeClaim.claimName`, and per volume `controllerType` (`SCSI` default, `NVME`, `SATA`, `IDE`), `controllerBusNumber`, `unitNumber`, `diskMode`, `sharingMode`, `applicationType`, `removable`. |
| `hardware` | `cdrom[]` (an ISO image, `connected`, `allowGuestControl`) and the controllers: `scsiControllers[]`, `nvmeControllers[]`, `sataControllers[]`, `ideControllers[]`. |
| `advanced` | `bootDiskCapacity`, `defaultVolumeProvisioningMode` (`Thin`, `Thick`, `ThickEagerZero`), `changeBlockTracking`. |
| `promoteDisksMode` | `Online` (default), `Offline`, `Disabled`. See the gotchas. |
| `bootOptions` | `firmware` (`bios`, `efi`: lower case, whatever the designer suggests), `efiSecureBoot`, `bootOrder`, `bootDelay`, `bootRetry`, `bootRetryDelay`, `networkBootProtocol`. |
| `readinessProbe` | `tcpSocket.port`, `guestHeartbeat.thresholdStatus`, or `guestInfo[]`, with `periodSeconds` and `timeoutSeconds`. |
| `affinity` | `vmAffinity` and `vmAntiAffinity`, each `requiredDuringSchedulingPreferredDuringExecution` (must hold) or `preferredDuringSchedulingPreferredDuringExecution` (best effort): a `labelSelector` and a `topologyKey`. Needs `groupName`. |
| `groupName` | The Virtual Machine Group the VM belongs to; the group then places it. |
| `crypto` | `encryptionClassName`, `useDefaultKeyProvider` (default `true`), `vTPMMode`. |
| `minHardwareVersion` | A floor for the virtual hardware version: NVMe needs 14 or later. |
| `nextRestartTime` | Set to `now` to restart the VM, per `restartMode`. |
| `powerOffMode`, `suspendMode`, `restartMode` | `TrySoft` (default), `Soft`, `Hard`. |
| `currentSnapshotName`, `policies[]`, `biosUUID`, `instanceUUID` | Revert to a snapshot, attach policies, pin identifiers. |

<!-- FIELDS:vm -->
{{< collapse summary="Every field the platform accepts (266)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.advanced` | object |  | e.g. `{bootDiskCapacity: 40Gi, defaultVolumeProvisioningMode: Thin}` | Advanced describes a set of optional, advanced VM configuration options. |
| `spec.advanced.bootDiskCapacity` | int or string |  | e.g. `40Gi` | BootDiskCapacity is the capacity of the VM's boot disk -- the first disk from the VirtualMachineImage from which the VM was deployed. |
| `spec.advanced.changeBlockTracking` | boolean |  | e.g. `true` | ChangeBlockTracking is a flag that enables incremental backup support for this VM, a feature utilized by external backup systems such as VMware Data Recovery. |
| `spec.advanced.defaultVolumeProvisioningMode` | string |  | `Thin`, `Thick`, `ThickEagerZero` | DefaultVolumeProvisioningMode specifies the default provisioning mode for persistent volumes managed by this VM. |
| `spec.affinity` | object |  | e.g. `{vmAntiAffinity: {preferredDuringSchedulingPreferredDuringExecution: [{topologyKey: , ...}]}}` | Affinity describes the VM's scheduling constraints. |
| `spec.affinity.vmAffinity` | object |  | e.g. `{preferredDuringSchedulingPreferredDuringExecution: [{labelSelector: {matchLabels: {, ...}}}]}` | VMAffinity describes affinity scheduling rules related to other VMs. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution` | array of object |  | e.g. `[{labelSelector: {matchLabels: {app: web}}, topologyKey: kubernetes.io/hostname}]` | PreferredDuringSchedulingPreferredDuringExecution describes affinity requirements that should be met, but the VM can still be scheduled if the requirement cannot be satisfied. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector` | object |  | e.g. `{matchLabels: {app: web}}` | LabelSelector is a label query over a set of VMs. When omitted, this term matches with no VMs. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.affinity.vmAffinity.preferredDuringSchedulingPreferredDuringExecution[].topologyKey` | string | yes | e.g. `kubernetes.io/hostname` | TopologyKey describes where this VM should be co-located (affinity) or not co-located (anti-affinity). |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution` | array of object |  | e.g. `[{labelSelector: {matchLabels: {app: web}}, topologyKey: kubernetes.io/hostname}]` | RequiredDuringSchedulingPreferredDuringExecution describes affinity requirements that must be met or the VM will not be scheduled. |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector` | object |  | e.g. `{matchLabels: {app: web}}` | LabelSelector is a label query over a set of VMs. When omitted, this term matches with no VMs. |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.affinity.vmAffinity.requiredDuringSchedulingPreferredDuringExecution[].topologyKey` | string | yes | e.g. `kubernetes.io/hostname` | TopologyKey describes where this VM should be co-located (affinity) or not co-located (anti-affinity). |
| `spec.affinity.vmAntiAffinity` | object |  | e.g. `{preferredDuringSchedulingPreferredDuringExecution: [{topologyKey: kubernetes.io/hos, ...}]}` | VMAntiAffinity describes anti-affinity scheduling rules related to other VMs. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution` | array of object |  | e.g. `[{topologyKey: kubernetes.io/hostname, labelSelector: {matchLabels: {app: web}}}]` | PreferredDuringSchedulingPreferredDuringExecution describes anti-affinity requirements that should be met, but the VM can still be scheduled if the requirement cannot be satisfied. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector` | object |  | e.g. `{matchLabels: {app: web}}` | LabelSelector is a label query over a set of VMs. When omitted, this term matches with no VMs. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution[].labelSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.affinity.vmAntiAffinity.preferredDuringSchedulingPreferredDuringExecution[].topologyKey` | string | yes | e.g. `kubernetes.io/hostname` | TopologyKey describes where this VM should be co-located (affinity) or not co-located (anti-affinity). |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution` | array of object |  | e.g. `[{labelSelector: {matchLabels: {app: web}}, topologyKey: kubernetes.io/hostname}]` | RequiredDuringSchedulingPreferredDuringExecution describes anti-affinity requirements that must be met or the VM will not be scheduled. |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector` | object |  | e.g. `{matchLabels: {app: web}}` | LabelSelector is a label query over a set of VMs. When omitted, this term matches with no VMs. |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchExpressions[].values` | array of string |  | e.g. `[web]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution[].labelSelector.matchLabels` | object |  | e.g. `{app: web}` | matchLabels is a map of {key,value} pairs. |
| `spec.affinity.vmAntiAffinity.requiredDuringSchedulingPreferredDuringExecution[].topologyKey` | string | yes | e.g. `kubernetes.io/hostname` | TopologyKey describes where this VM should be co-located (affinity) or not co-located (anti-affinity). |
| `spec.biosUUID` | string |  | e.g. `4210d2a5-6d0e-4f6e-9c3a-0b1f2e3d4c5b` | BiosUUID describes the desired BIOS UUID for a VM. If omitted, this field defaults to a random UUID. |
| `spec.bootOptions` | object |  | e.g. `{bootDelay: 5s, bootOrder: [{name: <device name>, type: Disk}]}` | BootOptions describes the settings that control the boot behavior of the virtual machine. These settings take effect during the next power-on of the virtual machine. |
| `spec.bootOptions.bootDelay` | string |  | e.g. `5s` | BootDelay is the delay before starting the boot sequence. The boot delay specifies a time interval between virtual machine power on or restart and the beginning of the boot sequence. |
| `spec.bootOptions.bootOrder` | array of object |  | e.g. `[{name: <device name>, type: Disk}]` | BootOrder represents the boot order of the virtual machine. After list is exhausted, default BIOS boot device algorithm is used for booting. |
| `spec.bootOptions.bootOrder[].name` | string |  | e.g. `<device name>` | Name represents the name of the bootable device. It is required for Disk and Network device types, while ignored for CDRom device types. |
| `spec.bootOptions.bootOrder[].type` | string | yes | `Disk`, `Network`, `CDRom` | Type represents the type of bootable device. The available device types are: - Disk - Network - CDRom |
| `spec.bootOptions.bootRetry` | string |  | default `Disabled` | BootRetry specifies whether a virtual machine that fails to boot will try again. |
| `spec.bootOptions.bootRetryDelay` | string |  | e.g. `10s` | BootRetryDelay specifies a time interval between virtual machine boot failure and the subsequent attempt to boot again. |
| `spec.bootOptions.efiSecureBoot` | string |  | `Enabled`, `Disabled`; default `Disabled` | EFISecureBoot specifies whether the virtual machine's firmware will perform signature checks of any EFI images loaded during startup. |
| `spec.bootOptions.firmware` | string |  | `bios`, `efi` | Firmware represents the firmware for the virtual machine to use. Any update to this value after the virtual machine has already been created will be ignored. |
| `spec.bootOptions.networkBootProtocol` | string |  | `IP4`, `IP6`; default `IP4` | NetworkBootProtocol is the protocol to attempt during PXE network boot or NetBoot. The available protocols are: - IP4 -- PXE (or Apple NetBoot) over IPv4. |
| `spec.bootstrap` | object |  | e.g. `{cloudInit: {cloudConfig: {timezone: Europe/London, users: [{name: ops, ...}]}}}` | Bootstrap describes the desired state of the guest's bootstrap configuration. If omitted, a default bootstrap method may be selected based on the guest OS identifier. |
| `spec.bootstrap.cloudInit` | object |  | e.g. `{cloudConfig: {timezone: Europe/London, users: [{name: ops, ...}]}}` | CloudInit may be used to bootstrap Linux guests with Cloud-Init or Windows guests that support Cloudbase-Init. |
| `spec.bootstrap.cloudInit.cloudConfig` | object |  | e.g. `{timezone: Europe/London, users: [{name: ops, hashed_passwd: {key: ops-passwd, ...}}]}` | CloudConfig describes a subset of a Cloud-Init CloudConfig, used to bootstrap the VM. |
| `spec.bootstrap.cloudInit.cloudConfig.defaultUserEnabled` | boolean |  | e.g. `true` | DefaultUserEnabled may be set to true to ensure even if the Users field is not empty, the default user is still created on systems that have one defined. |
| `spec.bootstrap.cloudInit.cloudConfig.runcmd` | any |  | e.g. `[systemctl enable --now nginx]` | RunCmd allows running one or more commands on the guest. The entries in this list can adhere to two, different formats: Format 1 -- a string that contains the command and its arguments, ex. |
| `spec.bootstrap.cloudInit.cloudConfig.ssh_pwauth` | boolean |  | e.g. `true` | SSHPwdAuth sets whether or not to accept password authentication. In order for this config to be applied, SSH may need to be restarted. |
| `spec.bootstrap.cloudInit.cloudConfig.timezone` | string |  | e.g. `Europe/London` | Timezone describes the timezone represented in /usr/share/zoneinfo. |
| `spec.bootstrap.cloudInit.cloudConfig.users` | array of object |  | e.g. `[{name: ops, hashed_passwd: {key: ops-passwd, name: web-pw}}]` | Users allows adding/configuring one or more users on the guest. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].create_groups` | boolean |  | e.g. `true` | CreateGroups is a flag that may be set to false to disable creation of specified user groups. Defaults to true when Name is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].expiredate` | string |  | e.g. `2027-01-01` | ExpireData is the date on which the user's account will be disabled. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].gecos` | string |  | e.g. `Operations user` | Gecos is an optional comment about the user, usually a comma-separated string of the user's real name and contact information. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].groups` | array of string |  | e.g. `[sudo]` | Groups is an optional list of groups to add to the user. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].hashed_passwd` | object |  | e.g. `{key: ops-passwd, name: web-pw}` | HashedPasswd is a hash of the user's password that will be applied even if the specified user already exists. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].hashed_passwd.key` | string | yes | e.g. `ops-passwd` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].hashed_passwd.name` | string | yes | e.g. `web-pw` | Name is the name of the secret. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].homedir` | string |  | e.g. `/home/ops` | Homedir is the optional home directory for the user. Defaults to "/home/<username>" when Name is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].inactive` | integer |  | e.g. `30` | Inactive optionally represents the number of days until the user is disabled. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].lock_passwd` | boolean |  | e.g. `false` | LockPasswd disables password login. Defaults to true when Name is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].name` | string | yes | e.g. `ops` | Name is the user's login name. When set to "default", all other fields from this User must be nil. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].no_create_home` | boolean |  | e.g. `true` | NoCreateHome prevents the creation of the home directory. Defaults to false when Name is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].no_log_init` | boolean |  | e.g. `true` | NoLogInit prevents the initialization of lastlog and faillog for the user. Defaults to false when Name is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].no_user_group` | boolean |  | e.g. `true` | NoUserGroup prevents the creation of the group named after the user. Defaults to false when Name is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].passwd` | object |  | e.g. `{key: <key in the Secret>, name: <Secret name>}` | Passwd is a hash of the user's password that will be applied only to a newly created user. To apply a new, hashed password to an existing user please use HashedPasswd instead. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].passwd.key` | string | yes | e.g. `<key in the Secret>` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].passwd.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].primary_group` | string |  | e.g. `ops` | PrimaryGroup is the primary group for the user. Defaults to the value of the Name field when it is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].selinux_user` | string |  | e.g. `staff_u` | SELinuxUser is the SELinux user for the user's login. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].shell` | string |  | e.g. `/bin/bash` | Shell is the path to the user's login shell. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].snapuser` | string |  | e.g. `ops@example.com` | SnapUser specifies an e-mail address to create the user as a Snappy user through "snap create-user". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].ssh_authorized_keys` | array of string |  | e.g. `[ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOkJfr8Q3cNq ops@example]` | SSHAuthorizedKeys is a list of SSH keys to add to the user's authorized keys file. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].ssh_import_id` | array of string |  | e.g. `[gh:octocat]` | SSHImportID is a list of SSH IDs to import for the user. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].ssh_redirect_user` | boolean |  | e.g. `true` | SSHRedirectUser may be set to true to disable SSH logins for this user. Any SSH login as this user will timeout with a message to login instead as the default user. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].sudo` | string |  | e.g. `ALL=(ALL) NOPASSWD:ALL` | Sudo is a sudo rule to apply to the user. When omitted, no sudo rules will be applied to the user. |
| `spec.bootstrap.cloudInit.cloudConfig.users[].system` | boolean |  | e.g. `true` | System is an optional flag that indicates the user should be created as a system user with no home directory. Defaults to false when Name is not "default". |
| `spec.bootstrap.cloudInit.cloudConfig.users[].uid` | integer |  | e.g. `1001` | UID is the user's ID. When omitted the guest will default to the next available number. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files` | array of object |  | e.g. `[{path: /etc/nginx/conf.d/lab.conf, content: server_tokens off;}]` | WriteFiles allows adding files to the guest file system. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files[].append` | boolean |  | e.g. `true` | Append specifies whether or not to append the content to an existing file if the file specified by Path already exists. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files[].content` | any |  | e.g. `server_tokens off;` | Content is the optional content to write to the provided Path. When omitted an empty file will be created or existing file will be modified. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files[].defer` | boolean |  | e.g. `true` | Defer indicates to defer writing the file until Cloud-Init's "final" stage, after users are created and packages are installed. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files[].encoding` | string |  | `b64`, `base64`, `gz`, `gzip`, `gz+b64`, `gz+base64`, `gzip+b64`, `gzip+base64`, `text/plain`; default `text/plain` | Encoding is an optional encoding type of the content. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files[].owner` | string |  | default `root:root` | Owner is an optional "owner:group" to chown the file. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files[].path` | string | yes | e.g. `/etc/nginx/conf.d/lab.conf` | Path is the path of the file to which the content is decoded and written. |
| `spec.bootstrap.cloudInit.cloudConfig.write_files[].permissions` | string |  | default `0644` | Permissions an optional set of file permissions to set. "0###". When omitted the guest will default this value to "0644". |
| `spec.bootstrap.cloudInit.instanceID` | string |  | e.g. `web-01-v2` | InstanceID is the cloud-init metadata instance ID. If omitted, this field defaults to the VM's BiosUUID. |
| `spec.bootstrap.cloudInit.rawCloudConfig` | object |  | e.g. `{key: user-data, name: jump-bootstrap}` | RawCloudConfig describes a key in a Secret resource that contains the CloudConfig data used to bootstrap the VM. |
| `spec.bootstrap.cloudInit.rawCloudConfig.key` | string | yes | e.g. `user-data` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.cloudInit.rawCloudConfig.name` | string | yes | e.g. `jump-bootstrap` | Name is the name of the secret. |
| `spec.bootstrap.cloudInit.sshAuthorizedKeys` | array of string |  | e.g. `[ssh-ed25519 AAAA... ops@admin]` | SSHAuthorizedKeys is a list of public keys that CloudInit will apply to the guest's default user. |
| `spec.bootstrap.cloudInit.useGlobalNameserversAsDefault` | boolean |  | e.g. `true` | UseGlobalNameserversAsDefault will use the global nameservers specified in the NetworkSpec as the per-interface nameservers when the per-interface nameservers is not provided. |
| `spec.bootstrap.cloudInit.useGlobalSearchDomainsAsDefault` | boolean |  | e.g. `true` | UseGlobalSearchDomainsAsDefault will use the global search domains specified in the NetworkSpec as the per-interface search domains when the per-interface search domains is not provided. |
| `spec.bootstrap.cloudInit.waitOnNetwork4` | boolean |  | e.g. `true` | WaitOnNetwork4 indicates whether the cloud-init datasource should wait for an IPv4 address to be available before writing the instance-data. |
| `spec.bootstrap.cloudInit.waitOnNetwork6` | boolean |  | e.g. `true` | WaitOnNetwork6 indicates whether the cloud-init datasource should wait for an IPv6 address to be available before writing the instance-data. |
| `spec.bootstrap.linuxPrep` | object |  | e.g. `{password: {name: <Secret name>, key: password}, ...}` | LinuxPrep may be used to bootstrap Linux guests. The guest's networking stack is configured by Guest OS Customization (GOSC). |
| `spec.bootstrap.linuxPrep.customizeAtNextPowerOn` | boolean |  | e.g. `true` | CustomizeAtNextPowerOn describes when customization is performed on the VM. When set to false, the VM will not be customized at the next power on. |
| `spec.bootstrap.linuxPrep.expirePasswordAfterNextLogin` | boolean |  | e.g. `true` | ExpirePasswordAfterNextLogin indicates whether or not the root account is required to change their password after the next login. |
| `spec.bootstrap.linuxPrep.hardwareClockIsUTC` | boolean |  | e.g. `true` | HardwareClockIsUTC specifies whether the hardware clock is in UTC or local time. |
| `spec.bootstrap.linuxPrep.password` | object |  | e.g. `{name: <Secret name>, key: password}` | Password is the new root password for the machine. When not explicitly specified, the Key field for the selector defaults to `password`. |
| `spec.bootstrap.linuxPrep.password.key` | string |  | default `password` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.linuxPrep.password.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.linuxPrep.scriptText` | object |  | e.g. `{from: {key: <key in the Secret>, name: <Secret name>}, value: '#!/bin/sh ...'}` | ScriptText is the script to run before and after customization. Please see https://knowledge.broadcom.com/external/article?legacyId=1026614 for script examples. |
| `spec.bootstrap.linuxPrep.scriptText.from` | object |  | e.g. `{key: <key in the Secret>, name: <Secret name>}` | From is specified to reference a value from a Secret resource. |
| `spec.bootstrap.linuxPrep.scriptText.from.key` | string | yes | e.g. `<key in the Secret>` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.linuxPrep.scriptText.from.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.linuxPrep.scriptText.value` | string |  | e.g. `'#!/bin/sh ...'` | Value is used to directly specify a value. |
| `spec.bootstrap.linuxPrep.timeZone` | string |  | e.g. `Europe/London` | TimeZone is a case-sensitive timezone, such as Europe/Sofia. Valid values are based on the tz (timezone) database used by Linux and other Unix systems. |
| `spec.bootstrap.sysprep` | object |  | e.g. `{rawSysprep: {key: <key in the Secret>, name: <Secret name>}, ...}` | Sysprep may be used to bootstrap Windows guests. The guest's networking stack is configured by Guest OS Customization (GOSC). |
| `spec.bootstrap.sysprep.customizeAtNextPowerOn` | boolean |  | e.g. `true` | CustomizeAtNextPowerOn describes when customization is performed on the VM. When set to false, the VM will not be customized at the next power on. |
| `spec.bootstrap.sysprep.rawSysprep` | object |  | e.g. `{key: <key in the Secret>, name: <Secret name>}` | RawSysprep describes a key in a Secret resource that contains an XML string of the Sysprep text used to bootstrap the VM. |
| `spec.bootstrap.sysprep.rawSysprep.key` | string | yes | e.g. `<key in the Secret>` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.sysprep.rawSysprep.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.sysprep.sysprep` | object |  | e.g. `{guiRunOnce: {commands: [powershell -File C:\setup.ps1]}, ...}` | Sysprep is an object representation of a Windows sysprep.xml answer file. This field encloses all the individual keys listed in a sysprep.xml file. |
| `spec.bootstrap.sysprep.sysprep.expirePasswordAfterNextLogin` | boolean |  | e.g. `true` | ExpirePasswordAfterNextLogin indicates whether or not the local Administrators group accounts are required to change their password after the next login. |
| `spec.bootstrap.sysprep.sysprep.guiRunOnce` | object |  | e.g. `{commands: [powershell -File C:\setup.ps1]}` | GUIRunOnce is a representation of the Sysprep GuiRunOnce key. |
| `spec.bootstrap.sysprep.sysprep.guiRunOnce.commands` | array of string |  | e.g. `[powershell -File C:\setup.ps1]` | Commands is a list of commands to run at first user logon, after guest customization. |
| `spec.bootstrap.sysprep.sysprep.guiUnattended` | object |  | e.g. `{autoLogonCount: 1, password: {name: <Secret name>, key: password}}` | GUIUnattended is a representation of the Sysprep GUIUnattended key. |
| `spec.bootstrap.sysprep.sysprep.guiUnattended.autoLogon` | boolean |  | e.g. `true` | AutoLogon determine whether the machine automatically logs on as Administrator. |
| `spec.bootstrap.sysprep.sysprep.guiUnattended.autoLogonCount` | integer |  | e.g. `1` | AutoLogonCount specifies the number of times the machine should automatically log on as Administrator. |
| `spec.bootstrap.sysprep.sysprep.guiUnattended.password` | object |  | e.g. `{name: <Secret name>, key: password}` | Password is the new administrator password for the machine. To specify that the password should be set to blank (that is, no password), set the password value to NULL. |
| `spec.bootstrap.sysprep.sysprep.guiUnattended.password.key` | string | yes | default `password` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.sysprep.sysprep.guiUnattended.password.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.sysprep.sysprep.guiUnattended.timeZone` | integer |  | default `85` | TimeZone is the time zone index for the virtual machine.ly/3Rzv8oL. Defaults to UTC. |
| `spec.bootstrap.sysprep.sysprep.identification` | object |  | e.g. `{domainAdmin: svc-join@example.local, domainAdminPassword: {name: <Secret name>, ...}}` | Identification is a representation of the Sysprep Identification key. |
| `spec.bootstrap.sysprep.sysprep.identification.domainAdmin` | string |  | e.g. `svc-join@example.local` | DomainAdmin is the domain user account used for authentication if the virtual machine is joining a domain. |
| `spec.bootstrap.sysprep.sysprep.identification.domainAdminPassword` | object |  | e.g. `{name: <Secret name>, key: domain_admin_password}` | DomainAdminPassword is the password for the domain user account used for authentication if the virtual machine is joining a domain. |
| `spec.bootstrap.sysprep.sysprep.identification.domainAdminPassword.key` | string | yes | default `domain_admin_password` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.sysprep.sysprep.identification.domainAdminPassword.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.sysprep.sysprep.identification.domainOU` | string |  | e.g. `OU=Servers,DC=example,DC=local` | DomainOU is the MachineObjectOU which specifies the full LDAP path name of the OU to which the computer belongs. |
| `spec.bootstrap.sysprep.sysprep.identification.joinWorkgroup` | string |  | e.g. `WORKGROUP` | JoinWorkgroup is the workgroup that the virtual machine should join. |
| `spec.bootstrap.sysprep.sysprep.licenseFilePrintData` | object |  | e.g. `{autoUsers: 5, autoMode: perSeat}` | LicenseFilePrintData is a representation of the Sysprep LicenseFilePrintData key. |
| `spec.bootstrap.sysprep.sysprep.licenseFilePrintData.autoMode` | string | yes | `perSeat`, `perServer` | AutoMode specifies the server licensing mode. |
| `spec.bootstrap.sysprep.sysprep.licenseFilePrintData.autoUsers` | integer |  | e.g. `5` | AutoUsers indicates the number of client licenses purchased for the VirtualCenter server being installed. |
| `spec.bootstrap.sysprep.sysprep.scriptText` | object |  | e.g. `{from: {key: <key in the Secret>, name: <Secret name>}, ...}` | ScriptText describes the script to run before and after customization. The script must be a Windows batch file. |
| `spec.bootstrap.sysprep.sysprep.scriptText.from` | object |  | e.g. `{key: <key in the Secret>, name: <Secret name>}` | From is specified to reference a value from a Secret resource. |
| `spec.bootstrap.sysprep.sysprep.scriptText.from.key` | string | yes | e.g. `<key in the Secret>` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.sysprep.sysprep.scriptText.from.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.sysprep.sysprep.scriptText.value` | string |  | e.g. `powershell -File C:\setup.ps1` | Value is used to directly specify a value. |
| `spec.bootstrap.sysprep.sysprep.userData` | object | yes | e.g. `{fullName: Lab Admin, orgName: Example Ltd}` | UserData is a representation of the Sysprep UserData key. |
| `spec.bootstrap.sysprep.sysprep.userData.fullName` | string | yes | e.g. `Lab Admin` | FullName is the user's full name. |
| `spec.bootstrap.sysprep.sysprep.userData.orgName` | string | yes | e.g. `Example Ltd` | OrgName is the name of the user's organization. |
| `spec.bootstrap.sysprep.sysprep.userData.productID` | object |  | e.g. `{name: <Secret name>, key: product_id}` | ProductID is a valid serial number. When not explicitly specified, the Key field for the selector defaults to `domain_admin_password`. |
| `spec.bootstrap.sysprep.sysprep.userData.productID.key` | string | yes | default `product_id` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.sysprep.sysprep.userData.productID.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.vAppConfig` | object |  | e.g. `{properties: [{key: guestinfo.hostname, value: {from: {key: <key in the Secret>, ...}}}]}` | VAppConfig may be used to bootstrap guests that rely on vApp properties (how VMware surfaces OVF properties on guests) to transport data into the guest. |
| `spec.bootstrap.vAppConfig.properties` | array of object |  | e.g. `[{key: guestinfo.hostname, value: {from: {key: <key in the Secret>, ...}}}]` | Properties is a list of vApp/OVF property key/value pairs. |
| `spec.bootstrap.vAppConfig.properties[].key` | string | yes | e.g. `guestinfo.hostname` | Key is the key part of the key/value pair. |
| `spec.bootstrap.vAppConfig.properties[].value` | object |  | e.g. `{from: {key: <key in the Secret>, name: <Secret name>}, value: web-01}` | Value is the optional value part of the key/value pair. |
| `spec.bootstrap.vAppConfig.properties[].value.from` | object |  | e.g. `{key: <key in the Secret>, name: <Secret name>}` | From is specified to reference a value from a Secret resource. |
| `spec.bootstrap.vAppConfig.properties[].value.from.key` | string | yes | e.g. `<key in the Secret>` | Key is the key in the secret that specifies the requested data. |
| `spec.bootstrap.vAppConfig.properties[].value.from.name` | string | yes | e.g. `<Secret name>` | Name is the name of the secret. |
| `spec.bootstrap.vAppConfig.properties[].value.value` | string |  | e.g. `web-01` | Value is used to directly specify a value. |
| `spec.bootstrap.vAppConfig.rawProperties` | string |  | e.g. `<ConfigMap with the OVF properties>` | RawProperties is the name of a Secret resource in the same Namespace as this VM where each key/value pair from the Secret is used as a vApp key/value pair. |
| `spec.class` | object |  | e.g. `{kind: VirtualMachineClass, name: best-effort-small}` | Class describes the VirtualMachineClassInstance resource that is referenced by this virtual machine. |
| `spec.class.apiVersion` | string | yes | e.g. `vmoperator.vmware.com/v1alpha5` | APIVersion defines the versioned schema of this representation of an object. |
| `spec.class.kind` | string | yes | e.g. `VirtualMachineClass` | Kind is a string value representing the REST resource this object represents. Servers may infer this from the endpoint the client submits requests to. |
| `spec.class.name` | string | yes | e.g. `best-effort-small` | Name refers to a unique resource in the current namespace. |
| `spec.className` | string |  | e.g. `best-effort-small` | ClassName describes the name of the VirtualMachineClass resource used to deploy this VM. |
| `spec.crypto` | object |  | e.g. `{encryptionClassName: <encryption class>, useDefaultKeyProvider: true}` | Crypto describes the desired encryption state of the VirtualMachine. |
| `spec.crypto.encryptionClassName` | string |  | e.g. `<encryption class>` | EncryptionClassName describes the name of the EncryptionClass resource used to encrypt this VM. |
| `spec.crypto.useDefaultKeyProvider` | boolean |  | default `true` | UseDefaultKeyProvider describes the desired behavior for when an explicit EncryptionClass is not provided. |
| `spec.crypto.vTPMMode` | string |  | `Clone`, `New`; default `New` | VTPMMode describes the desired behavior when deploying a VirtualMachine using a VirtualMachine-backed image which created from an encrypted VirtualMachine with a vTPM. |
| `spec.currentSnapshotName` | string |  | e.g. `before-upgrade` | CurrentSnapshotName represents the desired snapshot that the VM should point to. This field can be specified to revert the VM to a given snapshot. |
| `spec.groupName` | string |  | e.g. `web` | GroupName indicates the name of the VirtualMachineGroup to which this VM belongs. VMs that belong to a group do not drive their own placement, rather that is handled by the group. |
| `spec.guestID` | string |  | e.g. `vmkernel9Guest` | GuestID describes the desired guest operating system identifier for a VM. The logic that determines the guest ID is as follows: If this field is set, then its value is used. |
| `spec.hardware` | object |  | e.g. `{cdrom: [{name: cdrom0, image: {kind: VirtualMachineImage, ...}}]}` | Hardware describes the VM's desired hardware. |
| `spec.hardware.cdrom` | array of object |  | e.g. `[{name: cdrom0, image: {kind: VirtualMachineImage, name: vmi-e400a813bbd5d52a5}}]` | Cdrom describes the desired state of the VM's CD-ROM devices. Each CD-ROM device requires a reference to an ISO-type VirtualMachineImage or ClusterVirtualMachineImage resource as backing. |
| `spec.hardware.cdrom[].allowGuestControl` | boolean |  | default `true` | AllowGuestControl describes whether or not a web console connection may be used to connect/disconnect the CD-ROM device. |
| `spec.hardware.cdrom[].connected` | boolean |  | default `true` | Connected describes the desired connection state of the CD-ROM device. When true, the CD-ROM device is added and connected to the VM. |
| `spec.hardware.cdrom[].controllerBusNumber` | integer |  | e.g. `0` | ControllerBusNumber describes the bus number of the controller to which this CD-ROM should be attached. |
| `spec.hardware.cdrom[].controllerType` | string |  | e.g. `SATA` | ControllerType describes the type of the controller to which this CD-ROM should be attached. |
| `spec.hardware.cdrom[].image` | object | yes | e.g. `{kind: VirtualMachineImage, name: vmi-e400a813bbd5d52a5}` | Image describes the reference to an ISO type VirtualMachineImage or ClusterVirtualMachineImage resource used as the backing for the CD-ROM. |
| `spec.hardware.cdrom[].image.kind` | string | yes | e.g. `VirtualMachineImage` | Kind describes the type of image, either a namespace-scoped VirtualMachineImage or cluster-scoped ClusterVirtualMachineImage. |
| `spec.hardware.cdrom[].image.name` | string | yes | e.g. `vmi-e400a813bbd5d52a5` | Name refers to the name of a VirtualMachineImage resource in the same namespace as this VM or a cluster-scoped ClusterVirtualMachineImage. |
| `spec.hardware.cdrom[].name` | string | yes | e.g. `cdrom0` | Name consists of at least two lowercase letters or digits of this CD-ROM. It must be unique among all CD-ROM devices attached to the VM. |
| `spec.hardware.cdrom[].unitNumber` | integer |  | e.g. `1` | UnitNumber describes the desired unit number for attaching the CD-ROM to a storage controller. When omitted, the next available unit number of the selected controller is used. |
| `spec.hardware.ideControllers` | array of object |  | e.g. `[{busNumber: 0}]` | IDEControllers describes the desired list of IDE controllers for the VM. Defaults to two IDE controllers, with bus 0 and bus 1. |
| `spec.hardware.ideControllers[].busNumber` | integer | yes | e.g. `0` | BusNumber describes the desired bus number of the controller. |
| `spec.hardware.nvmeControllers` | array of object |  | e.g. `[{busNumber: 0, sharingMode: None}]` | NVMEControllers describes the desired list of NVME controllers for the VM. |
| `spec.hardware.nvmeControllers[].busNumber` | integer | yes | e.g. `0` | BusNumber describes the desired bus number of the controller. |
| `spec.hardware.nvmeControllers[].sharingMode` | string |  | `None`, `Physical`; default `None` | SharingMode describes the sharing mode for the controller. Defaults to None. |
| `spec.hardware.sataControllers` | array of object |  | e.g. `[{busNumber: 0}]` | SATAControllers describes the desired list of SATA controllers for the VM. |
| `spec.hardware.sataControllers[].busNumber` | integer | yes | e.g. `0` | BusNumber describes the desired bus number of the controller. |
| `spec.hardware.scsiControllers` | array of object |  | e.g. `[{busNumber: 0, type: ParaVirtual}]` | SCSIControllers describes the desired list of SCSI controllers for the VM. |
| `spec.hardware.scsiControllers[].busNumber` | integer | yes | e.g. `0` | BusNumber describes the desired bus number of the controller. |
| `spec.hardware.scsiControllers[].sharingMode` | string |  | `None`, `Physical`, `Virtual`; default `None` | SharingMode describes the sharing mode for the controller. Defaults to None. |
| `spec.hardware.scsiControllers[].type` | string |  | `ParaVirtual`, `BusLogic`, `LsiLogic`, `LsiLogicSAS`; default `ParaVirtual` | Type describes the desired type of SCSI controller. Defaults to ParaVirtual. |
| `spec.image` | object |  | e.g. `{kind: VirtualMachineImage, name: vmi-0123456789abcdef0}` | Image describes the reference to the VirtualMachineImage or ClusterVirtualMachineImage resource used to deploy this VM.imageName, the value of spec.image.name MUST be a Kubernetes object ... |
| `spec.image.kind` | string | yes | e.g. `VirtualMachineImage` | Kind describes the type of image, either a namespace-scoped VirtualMachineImage or cluster-scoped ClusterVirtualMachineImage. |
| `spec.image.name` | string | yes | e.g. `vmi-0123456789abcdef0` | Name refers to the name of a VirtualMachineImage resource in the same namespace as this VM or a cluster-scoped ClusterVirtualMachineImage. |
| `spec.imageName` | string |  | e.g. `ubuntu-24.04-server-cloudimg-amd64` | ImageName describes the name of the image resource used to deploy this VM. This field may be used to specify the name of a VirtualMachineImage or ClusterVirtualMachineImage resource. |
| `spec.instanceUUID` | string |  | e.g. `5010c9b4-1f2e-4d3c-8b7a-6e5f4d3c2b1a` | InstanceUUID describes the desired Instance UUID for a VM. If omitted, this field defaults to a random UUID. This value is only used for the VM Instance UUID, it is not used within cloudInit. |
| `spec.minHardwareVersion` | integer |  | e.g. `21` | MinHardwareVersion describes the desired, minimum hardware version. The logic that determines the hardware version is as follows: 1. |
| `spec.network` | object |  | e.g. `{hostName: dc01, interfaces: [{name: eth0, addresses: [172.30.0.34/27]}]}` | Network describes the desired network configuration for the VM. |
| `spec.network.disabled` | boolean |  | e.g. `true` | Disabled is a flag that indicates whether or not to disable networking for this VM. |
| `spec.network.domainName` | string |  | e.g. `lab.local` | DomainName describes the value the guest uses as its domain name. |
| `spec.network.hostName` | string |  | e.g. `dc01` | HostName describes the value the guest uses as its host name. If omitted, the name of the VM will be used. |
| `spec.network.interfaces` | array of object |  | e.g. `[{name: eth0, addresses: [172.30.0.34/27]}]` | Interfaces is the list of network interfaces used by this VM. If the Interfaces field is empty and the Disabled field is false, then a default interface with the name eth0 will be created. |
| `spec.network.interfaces[].addresses` | array of string |  | e.g. `[172.30.0.34/27]` | Addresses is an optional list of IP4 or IP6 addresses to assign to this interface. 192.168.0.10/24 or 2001:db8:101::a/64. |
| `spec.network.interfaces[].dhcp4` | boolean |  | e.g. `true` | DHCP4 indicates whether or not this interface uses DHCP for IP4 networking. |
| `spec.network.interfaces[].dhcp6` | boolean |  | e.g. `true` | DHCP6 indicates whether or not this interface uses DHCP for IP6 networking. |
| `spec.network.interfaces[].gateway4` | string |  | e.g. `172.30.0.33` | Gateway4 is the default, IP4 gateway for this interface. If unset, the gateway from the network provider will be used. |
| `spec.network.interfaces[].gateway6` | string |  | e.g. `fd00::1` | Gateway6 is the primary IP6 gateway for this interface. If unset, the gateway from the network provider will be used. |
| `spec.network.interfaces[].guestDeviceName` | string |  | e.g. `eth0` | GuestDeviceName is used to rename the device inside the guest when the bootstrap provider is Cloud-Init. dvd, cdrom, sda, etc. |
| `spec.network.interfaces[].macAddr` | string |  | e.g. `00:50:56:00:00:10` | MACAddr is the optional MAC address of this interface. If no MAC address is provided, one will be generated by either the network provider or vCenter.nsx.vmware.com. |
| `spec.network.interfaces[].mtu` | integer |  | e.g. `1500` | MTU is the Maximum Transmission Unit size in bytes. |
| `spec.network.interfaces[].name` | string | yes | e.g. `eth0` | Name describes the unique name of this network interface, used to distinguish it from other network interfaces attached to this VM. |
| `spec.network.interfaces[].nameservers` | array of string |  | e.g. `[172.30.0.34]` | Nameservers is a list of IP4 and/or IP6 addresses used as DNS nameservers. |
| `spec.network.interfaces[].network` | object |  | e.g. `{kind: Subnet, name: sn-mgmt}` | Network is the name of the network resource to which this interface is connected. If no network is provided, then this interface will be connected to the Namespace's default network. |
| `spec.network.interfaces[].network.apiVersion` | string |  | e.g. `crd.nsx.vmware.com/v1alpha1` | APIVersion defines the versioned schema of this representation of an object. Servers should convert recognized schemas to the latest internal value, and may reject unrecognized values. |
| `spec.network.interfaces[].network.kind` | string |  | e.g. `Subnet` | Kind is a string value representing the REST resource this object represents. Servers may infer this from the endpoint the client submits requests to. |
| `spec.network.interfaces[].network.name` | string | yes | e.g. `sn-mgmt` | Name refers to a unique resource in the current namespace. |
| `spec.network.interfaces[].routes` | array of object |  | e.g. `[{to: 172.16.0.0/16, via: 10.200.0.1}]` | Routes is a list of optional, static routes. |
| `spec.network.interfaces[].routes[].metric` | integer |  | e.g. `100` | Metric is the weight/priority of the route. |
| `spec.network.interfaces[].routes[].to` | string | yes | e.g. `172.16.0.0/16` | To is either "default", or an IP4 or IP6 address. |
| `spec.network.interfaces[].routes[].via` | string | yes | e.g. `10.200.0.1` | Via is an IP4 or IP6 address. |
| `spec.network.interfaces[].searchDomains` | array of string |  | e.g. `[lab.local]` | SearchDomains is a list of search domains used when resolving IP addresses with DNS. |
| `spec.network.nameservers` | array of string |  | e.g. `[10.200.0.2]` | Nameservers is a list of IP4 and/or IP6 addresses used as DNS nameservers. These are applied globally. The Cloud-Init bootstrap provider supports per-interface nameservers. |
| `spec.network.searchDomains` | array of string |  | e.g. `[lab.local]` | SearchDomains is a list of search domains used when resolving IP addresses with DNS. These are applied globally. The Cloud-Init bootstrap provider supports per-interface search domains. |
| `spec.nextRestartTime` | string |  | e.g. `now` | NextRestartTime may be used to restart the VM, in accordance with RestartMode, by setting the value of this field to "now" (case-insensitive). |
| `spec.policies` | array of object |  | e.g. `[{kind: ComputePolicy, name: <compute policy>}]` | Policies describes a list of policies that should be explicitly applied to this VM. Please consult a policy to determine if it may be applied directly. |
| `spec.policies[].apiVersion` | string | yes | e.g. `vsphere.policy.vmware.com/v1alpha1` | APIVersion defines the versioned schema of this representation of an object. |
| `spec.policies[].kind` | string | yes | e.g. `ComputePolicy` | Kind is a string value representing the REST resource this object represents. Servers may infer this from the endpoint the client submits requests to. |
| `spec.policies[].name` | string | yes | e.g. `<compute policy>` | Name refers to a unique resource in the current namespace. |
| `spec.powerOffMode` | string |  | `Hard`, `Soft`, `TrySoft`; default `TrySoft` | PowerOffMode describes the desired behavior when powering off a VM. There are three, supported power off modes: Hard, Soft, and TrySoft. |
| `spec.powerState` | string |  | `PoweredOff`, `PoweredOn`, `Suspended` | PowerState describes the desired power state of a VirtualMachine." However, once the field is set to a non-empty value, it may no longer be set to an empty value. |
| `spec.promoteDisksMode` | string |  | `Online`, `Offline`, `Disabled`; default `Online` | PromoteDisksMode describes the mode used to promote a VM's delta disks to full disks. The available modes are: - Disabled -- Do not promote disks. |
| `spec.readinessProbe` | object |  | e.g. `{guestInfo: [{key: guestinfo.ready, value: "true"}], tcpSocket: {host: 10.200.0.10, ...}}` | ReadinessProbe describes a probe used to determine the VM's ready state. |
| `spec.readinessProbe.guestHeartbeat` | object |  | e.g. `{thresholdStatus: green}` | GuestHeartbeat specifies an action involving the guest heartbeat status. |
| `spec.readinessProbe.guestHeartbeat.thresholdStatus` | string |  | `yellow`, `green`; default `green` | ThresholdStatus is the value that the guest heartbeat status must be at or above to be considered successful. |
| `spec.readinessProbe.guestInfo` | array of object |  | e.g. `[{key: guestinfo.ready, value: "true"}]` | GuestInfo specifies an action involving key/value pairs from GuestInfo. |
| `spec.readinessProbe.guestInfo[].key` | string | yes | e.g. `guestinfo.ready` | Key is the name of the GuestInfo key. The key is automatically prefixed with "guestinfo." before being evaluated. |
| `spec.readinessProbe.guestInfo[].value` | string |  | e.g. `"true"` | Value is a regular expression that is matched against the value of the specified key. An empty value is the equivalent of "match any" or ".*". |
| `spec.readinessProbe.periodSeconds` | integer |  | e.g. `10` | PeriodSeconds specifics how often (in seconds) to perform the probe. Defaults to 10 seconds. Minimum value is 1. |
| `spec.readinessProbe.tcpSocket` | object |  | e.g. `{host: 10.200.0.10, port: 22}` | TCPSocket specifies an action involving a TCP port. Deprecated: The TCPSocket action requires network connectivity that is not supported in all environments. |
| `spec.readinessProbe.tcpSocket.host` | string |  | e.g. `10.200.0.10` | Host is an optional host name to connect to. Host defaults to the VM IP. |
| `spec.readinessProbe.tcpSocket.port` | int or string | yes | e.g. `22` | Port specifies a number or name of the port to access on the VM. If the format of port is a number, it must be in the range 1 to 65535. |
| `spec.readinessProbe.timeoutSeconds` | integer |  | e.g. `10` | TimeoutSeconds specifies a number of seconds after which the probe times out. Defaults to 10 seconds. Minimum value is 1. |
| `spec.reserved` | object |  | e.g. `{resourcePolicyName: <resource policy>}` | Reserved describes a set of VM configuration options reserved for system use. |
| `spec.reserved.resourcePolicyName` | string |  | e.g. `<resource policy>` |  |
| `spec.restartMode` | string |  | `Hard`, `Soft`, `TrySoft`; default `TrySoft` | RestartMode describes the desired behavior for restarting a VM when spec.nextRestartTime is set to "now" (case-insensitive). |
| `spec.storageClass` | string |  | e.g. `vsan-default-storage-policy` | StorageClass describes the name of a Kubernetes StorageClass resource used to configure this VM's storage-related attributes. |
| `spec.suspendMode` | string |  | `Hard`, `Soft`, `TrySoft`; default `TrySoft` | SuspendMode describes the desired behavior when suspending a VM. There are three, supported suspend modes: Hard, Soft, and TrySoft. |
| `spec.volumes` | array of object |  | e.g. `[{name: data, persistentVolumeClaim: {claimName: web-01-data, ...}}]` | Volumes describes a list of volumes that can be mounted to the VM. |
| `spec.volumes[].applicationType` | string |  | `OracleRAC`, `MicrosoftWSFC` | ApplicationType describes the type of application for which this volume is intended to be used. |
| `spec.volumes[].controllerBusNumber` | integer |  | e.g. `0` | ControllerBusNumber describes the bus number of the controller to which this volume should be attached. |
| `spec.volumes[].controllerType` | string |  | `IDE`, `NVME`, `SCSI`, `SATA` | ControllerType describes the type of the controller to which this volume should be attached. |
| `spec.volumes[].diskMode` | string |  | `IndependentNonPersistent`, `IndependentPersistent`, `NonPersistent`, `Persistent` | DiskMode describes the desired mode to use when attaching the volume. |
| `spec.volumes[].name` | string | yes | e.g. `data` | Name represents the volume's name. Must be a DNS_LABEL and unique within the VM. |
| `spec.volumes[].persistentVolumeClaim` | object |  | e.g. `{claimName: web-01-data, instanceVolumeClaim: {size: 50Gi, ...}}` | PersistentVolumeClaim represents a reference to a PersistentVolumeClaim in the same namespace. |
| `spec.volumes[].persistentVolumeClaim.claimName` | string | yes | e.g. `web-01-data` | claimName is the name of a PersistentVolumeClaim in the same namespace as the pod using this volume. |
| `spec.volumes[].persistentVolumeClaim.instanceVolumeClaim` | object |  | e.g. `{size: 50Gi, storageClass: vsan-default-storage-policy}` | InstanceVolumeClaim is set if the PVC is backed by instance storage. |
| `spec.volumes[].persistentVolumeClaim.instanceVolumeClaim.size` | int or string | yes | e.g. `50Gi` | Size is the size of the requested instance storage volume. |
| `spec.volumes[].persistentVolumeClaim.instanceVolumeClaim.storageClass` | string | yes | e.g. `vsan-default-storage-policy` | StorageClass is the name of the Kubernetes StorageClass that provides the backing storage for this instance storage volume. |
| `spec.volumes[].persistentVolumeClaim.readOnly` | boolean |  | e.g. `true` | readOnly Will force the ReadOnly setting in VolumeMounts. Default false. |
| `spec.volumes[].removable` | boolean |  | default `true` | Removable describes whether or not this volume may be removed from spec.volumes. |
| `spec.volumes[].sharingMode` | string |  | `MultiWriter`, `None` | SharingMode describes the volume's desired sharing mode. When applicationType=OracleRAC, this field defaults to MultiWriter. |
| `spec.volumes[].unitNumber` | integer |  | e.g. `1` | UnitNumber describes the desired unit number for attaching the volume to a storage controller. When omitted, the next available unit number of the selected controller is used. |
{{< /collapse >}}
<!-- /FIELDS:vm -->

Minimal:

```yaml
  vm1:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: vmoperator.vmware.com/v1alpha5
        kind: VirtualMachine
        metadata:
          name: web-01
          labels: {app: web}
        spec:
          className: best-effort-small
          imageName: ubuntu-24.04-server-cloudimg-amd64
          storageClass: vsan-default-storage-policy
      wait:
        conditions:
          - type: VirtualMachineGuestNetworkConfigSynced
            status: "True"
```

**Recipes**

- *A Linux user with an SSH key and a password*, inline cloud-init. The
  password is **not** a string here: `passwd` and `hashed_passwd` reference
  a key in a Secret, and a plain string fails with `cannot restore struct
  from: string`. The hash can come from [Util.PasswordEntry](#utilpasswordentry):

  ```yaml
          bootstrap:
            cloudInit:
              cloudConfig:
                users:
                  - name: ops
                    sudo: ALL=(ALL) NOPASSWD:ALL
                    lock_passwd: false
                    hashed_passwd:
                      name: web-pw          # a Secret in the namespace
                      key: ops-passwd       # holding ${resource.pw.sha512crypt}
                    ssh_authorized_keys:
                      - ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOkJfr8Q3cNq ops@example
                runcmd:
                  - [systemctl, enable, --now, ssh]
  ```

  We logged in through a load balancer as `ops` with that key; `sudo` needed
  no password and the shadow entry held the `$6$` hash.

- *Windows, or a long first-boot script:* keep the whole cloud-config in a
  Secret and point `rawCloudConfig` at it. Our jump hosts run cloudbase-init
  this way:

  ```yaml
          bootstrap:
            cloudInit:
              rawCloudConfig:
                name: jump-bootstrap     # the Secret
                key: user-data           # the key inside it
  ```

- *A static address on a VPC subnet.* With cloud-init the DNS servers go on
  the interface:

  ```yaml
          network:
            hostName: dc01
            interfaces:
              - name: eth0
                network: {apiVersion: crd.nsx.vmware.com/v1alpha1, kind: Subnet, name: sn-mgmt}
                addresses: ["172.30.0.34/27"]
                gateway4: 172.30.0.33
                nameservers: [172.30.0.34]
          bootstrap:
            cloudInit:
              rawCloudConfig: {name: dc-bootstrap, key: user-data}
  ```

- *An address on a subnet without choosing it:* name the subnet and leave
  `addresses` out. VM Operator takes one from the subnet and configures the
  guest; ours got `172.30.0.2`.

  ```yaml
          network:
            interfaces:
              - name: eth0
                network: {apiVersion: crd.nsx.vmware.com/v1alpha1, kind: Subnet, name: sn-app}
  ```

- *An extra data disk:* a Persistent Volume Claim in the same blueprint, then
  the VM below. It arrived in the guest as `sdb`, 5 GiB, beside the image's
  10 GiB `sda`:

  ```yaml
          volumes:
            - name: data
              persistentVolumeClaim:
                claimName: web-01-data
  ```

- *An ISO in the CD-ROM*, for an installer (our nested hosts boot the ESXi
  installer this way). `guestID` becomes mandatory:

  ```yaml
          guestID: vmkernel9Guest
          hardware:
            cdrom:
              - name: cdrom0
                image: {kind: VirtualMachineImage, name: vmi-e400a813bbd5d52a5}
                connected: true
                allowGuestControl: true
  ```

- *A bigger boot disk than the image's:* `advanced.bootDiskCapacity: 80Gi`.
  The guest still has to grow its partition.

- *Keep VMs apart.* Affinity rules only work for members of a
  [Virtual Machine Group](#virtual-machine-group); on a VM without
  `groupName` the Supervisor refuses them (`spec.groupName: Required value:
  when setting affinity`). Our two web VMs with this rule landed on
  different hosts:

  ```yaml
          groupName: web
          affinity:
            vmAntiAffinity:
              preferredDuringSchedulingPreferredDuringExecution:
                - labelSelector:
                    matchLabels: {app: web}
                  topologyKey: kubernetes.io/hostname
  ```

**Status worth reading:** `status.network.primaryIP4` (after the wait above),
`status.powerState`, `status.nodeName` (the ESXi host), `status.zone`,
`status.instanceUUID`, `status.biosUUID`, `status.hardwareVersion`, and
`status.volumes[]` with `attached` per disk.

**Gotchas**

- DNS settings depend on the bootstrap provider: `spec.network.nameservers`
  works only with LinuxPrep and Sysprep, the per-interface `nameservers` only
  with CloudInit and Sysprep, and a VM with no bootstrap can have neither.
  The Supervisor says which: `nameservers is available only with the
  following bootstrap providers: ...`.
- `promoteDisksMode` defaults to `Online`: after a fast deploy from a linked
  clone, VM Operator copies the disks into full disks while the VM runs. For
  a large image that is real I/O; `Disabled` keeps the linked clone and
  deploys faster. Our Windows jump host was ready in 15.1 minutes with
  `Disabled` against 17.6 with the default. VMs with snapshots cannot
  promote online.
- The first deployment of a new image into a VPC can fail with an NSX
  `503638` error while the image is still being cached; a retry succeeds.
- Changing `className` resizes the VM; changing `manifest` in a new blueprint
  version recreates it.

## Virtual Machine Group

`CCI.Supervisor.Resource` with `apiVersion: vmoperator.vmware.com/v1alpha5`,
`kind: VirtualMachineGroup`. A set of VMs placed and powered as one: a boot
order with delays between steps, and one power state for all of them.

| `spec` field | Notes |
|---|---|
| `bootOrder[]` | Steps, in order. Each has `members[]` (`kind`: `VirtualMachine` default or `VirtualMachineGroup`; `name`) and `powerOnDelay` before the step. |
| `powerState` | `PoweredOn` (default), `PoweredOff`, `Suspended`, applied to every member. |
| `powerOffMode`, `suspendMode` | `TrySoft` (default), `Soft`, `Hard`. |
| `groupName` | A parent group, to nest groups. |
| `nextForcePowerStateSyncTime` | `now` pushes the group's power state to every member again. |

<!-- FIELDS:vm-group -->
{{< collapse summary="Every field the platform accepts (10)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.bootOrder` | array of object |  | e.g. `[{members: [{name: web-01, kind: VirtualMachine}], powerOnDelay: 30s}]` | BootOrder describes the boot sequence for this group members. Each boot order contains a set of members that will be powered on simultaneously, with an optional delay before powering on. |
| `spec.bootOrder[].members` | array of object |  | e.g. `[{name: web-01, kind: VirtualMachine}]` | Members describes the names of VirtualMachine or VirtualMachineGroup objects that are members of this boot order group. |
| `spec.bootOrder[].members[].kind` | string |  | `VirtualMachine`, `VirtualMachineGroup`; default `VirtualMachine` | Kind is the kind of member of this group, which can be either VirtualMachine or VirtualMachineGroup. If omitted, it defaults to VirtualMachine. |
| `spec.bootOrder[].members[].name` | string | yes | e.g. `web-01` | Name is the name of member of this group. |
| `spec.bootOrder[].powerOnDelay` | string |  | e.g. `30s` | PowerOnDelay is the amount of time to wait before powering on all the members of this boot order group. |
| `spec.groupName` | string |  | e.g. `<parent group>` | GroupName describes the name of the group that this group belongs to. |
| `spec.nextForcePowerStateSyncTime` | string |  | e.g. `now` | NextForcePowerStateSyncTime may be used to force sync the power state of the group to all of its members, by setting the value of this field to "now" (case-insensitive). |
| `spec.powerOffMode` | string |  | `Hard`, `Soft`, `TrySoft` | PowerOffMode describes the desired behavior when powering off a VM Group. Refer to the VirtualMachine.PowerOffMode field for more details. |
| `spec.powerState` | string |  | `PoweredOff`, `PoweredOn`, `Suspended` | PowerState describes the desired power state of a VirtualMachineGroup. |
| `spec.suspendMode` | string |  | `Hard`, `Soft`, `TrySoft` | SuspendMode describes the desired behavior when suspending a VM Group. Refer to the VirtualMachine.SuspendMode field for more details. |
{{< /collapse >}}
<!-- /FIELDS:vm-group -->

Recipe, one VM before the next, thirty seconds apart:

```yaml
  appGroup:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: vmoperator.vmware.com/v1alpha5
        kind: VirtualMachineGroup
        metadata: {name: app}
        spec:
          bootOrder:
            - members: [{name: web-01}]
            - members: [{name: web-02}]
              powerOnDelay: 30s
```

Each member names the group in `spec.groupName: app` and depends on the group
resource (`dependsOn: [appGroup]`), because the group is referenced only by
name.

**Status worth reading:** `status.members[]` (each member's power state and
placement), `status.conditions`.

**Gotchas**

- A member of a later step stays off until every member of the earlier steps
  is on. When our first test's `web-01` failed to create, `web-02` sat
  powered off for good.
- A VM in a group doesn't place itself; the group places its members.

## Virtual Machine Service

`CCI.Supervisor.Resource` with `apiVersion: vmoperator.vmware.com/v1alpha5`,
`kind: VirtualMachineService`. A Kubernetes-style service in front of VMs,
selected by label. With `type: LoadBalancer`, the VPC's load balancer gives
it an external address. That's how a VM on a private subnet is reached from
outside.

| `spec` field | Notes |
|---|---|
| `type` | **Required.** `LoadBalancer` or `ClusterIP`. The API lists `ExternalName` too; the VM Operator documentation says it isn't supported. |
| `selector` | Labels of the VMs behind it. |
| `ports[]` | `name`, `port`, `targetPort`, `protocol` (`TCP`, `UDP`, `SCTP`). |
| `loadBalancerSourceRanges[]` | Source CIDRs allowed to reach a `LoadBalancer` service. |
| `loadBalancerIP`, `clusterIp`, `externalName` | A requested address, a fixed cluster IP, a DNS name. |

<!-- FIELDS:vm-service -->
{{< collapse summary="Every field the platform accepts (11)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.clusterIp` | string |  | e.g. `10.96.0.20` | ClusterIP is the IP address of the service and is usually assigned randomly by the master. |
| `spec.externalName` | string |  | e.g. `web.example.com` | ExternalName is the external reference that kubedns or equivalent will return as a CNAME record for this service. No proxying will be involved. |
| `spec.loadBalancerIP` | string |  | e.g. `192.168.144.20` | LoadBalancer will get created with the IP specified in this field. |
| `spec.loadBalancerSourceRanges` | array of string |  | e.g. `[10.0.0.0/8]` | LoadBalancerSourceRanges is an array of IP addresses in the format of CIDRs, for example: 103.21.244.0/22 and 10.0.0.0/24. |
| `spec.ports` | array of object |  | e.g. `[{name: rdp, port: 3389}]` | Ports specifies a list of VirtualMachineServicePort to expose with this VirtualMachineService. Each of these ports will be an accessible network entry point to access this service by. |
| `spec.ports[].name` | string | yes | e.g. `rdp` | Name describes the name to be used to identify this VirtualMachineServicePort. |
| `spec.ports[].port` | integer | yes | e.g. `3389` | Port describes the external port that will be exposed by the service. |
| `spec.ports[].protocol` | string | yes | e.g. `TCP` | Protocol describes the Layer 4 transport protocol for this port. Supports "TCP", "UDP", and "SCTP". |
| `spec.ports[].targetPort` | integer | yes | e.g. `3389` | TargetPort describes the internal port open on a VirtualMachine that should be mapped to the external Port. |
| `spec.selector` | object |  | e.g. `{app: web}` | Selector specifies a map of key-value pairs, also known as a Label Selector, that is used to match this VirtualMachineService with the set of VirtualMachines that should back this VirtualMachineService. |
| `spec.type` | string | yes | e.g. `LoadBalancer` | Type specifies a desired VirtualMachineServiceType for this VirtualMachineService. Supported types are ClusterIP, LoadBalancer, ExternalName. |
{{< /collapse >}}
<!-- /FIELDS:vm-service -->

Recipe, RDP to a jump host, the only way into our labs:

```yaml
  jumpAccess:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: vmoperator.vmware.com/v1alpha5
        kind: VirtualMachineService
        metadata: {name: jump-access}
        spec:
          type: LoadBalancer
          selector: {app: jump}
          ports:
            - {name: rdp, port: 3389, targetPort: 3389, protocol: TCP}
          loadBalancerSourceRanges: [10.0.0.0/8]
```

**Status worth reading:** `status.loadBalancer.ingress[0].ip`, the external
address.

**Gotchas**

- `LoadBalancer` needs the VPC's load balancer. VCF Automation waits for the
  address by itself, so in a VPC without one the request stays in progress
  until it times out. A VPC made by a blueprint never has one; see [VPC](#vpc).
- A service with several VMs behind it spreads connections across them: our
  SSH sessions alternated between the two web VMs.
- The palette writes `v1alpha3`; we use `v1alpha5`, the Supervisor's stored
  version. Both are served.

## Subnet

`CCI.Supervisor.Resource` with `apiVersion: crd.nsx.vmware.com/v1alpha1`,
`kind: Subnet`. A subnet of the namespace's VPC: a layer-2 segment with its
own address range, for VMs that need a network of their own.

| `spec` field | Notes |
|---|---|
| `accessMode` | `Private` (default): routed inside the VPC only. `PrivateTGW`: reachable from other VPCs through the transit gateway. `Public`: from the external network. |
| `ipv4SubnetSize` | Addresses in the subnet, default 64. |
| `ipAddresses[]` | Specific CIDRs instead of a size. |
| `subnetDHCPConfig.mode` | `DHCPDeactivated` (default), `DHCPServer`, `DHCPRelay`; `dhcpServerAdditionalConfig.reservedIPRanges` keeps ranges out of the pool. |
| `advancedConfig` | `staticIPAllocation.enabled`, `connectivityState` (`Connected` default, `Disconnected`), `gatewayAddresses`, `dhcpServerAddresses`. |
| `vpcName` | The VPC, when it isn't the namespace's own. |
| `vlanConnectionName` | A subnet backed by a distributed VLAN connection; not in the designer's form. |

<!-- FIELDS:subnet -->
{{< collapse summary="Every field the platform accepts (15)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.accessMode` | string |  | `Private`, `Public`, `PrivateTGW`, `L2Only` | Access mode of Subnet, accessible only from within VPC or from outside VPC. |
| `spec.advancedConfig` | object |  | e.g. `{dhcpServerAddresses: [10.200.0.2/28], gatewayAddresses: [10.200.0.1/28]}` | VPC Subnet advanced configuration. |
| `spec.advancedConfig.connectivityState` | string |  | `Connected`, `Disconnected`; default `Connected` | Connectivity status of the Subnet from other Subnets of the VPC. The default value is "Connected". |
| `spec.advancedConfig.dhcpServerAddresses` | array of string |  | e.g. `[10.200.0.2/28]` | DHCPServerAddresses specifies custom DHCP server IP addresses for the Subnet. |
| `spec.advancedConfig.gatewayAddresses` | array of string |  | e.g. `[10.200.0.1/28]` | GatewayAddresses specifies custom gateway IP addresses for the Subnet. |
| `spec.advancedConfig.staticIPAllocation` | object |  | e.g. `{enabled: true}` | Static IP allocation for VPC Subnet Ports. |
| `spec.advancedConfig.staticIPAllocation.enabled` | boolean |  | e.g. `true` | Activate or deactivate static IP allocation for VPC Subnet Ports. If the DHCP mode is DHCPDeactivated or not set, its default value is true. |
| `spec.ipAddresses` | array of string |  | e.g. `[10.200.0.0/28]` | Subnet CIDRS. |
| `spec.ipv4SubnetSize` | integer |  | e.g. `32` | Size of Subnet based upon estimated workload count. |
| `spec.subnetDHCPConfig` | object |  | e.g. `{dhcpServerAdditionalConfig: {reservedIPRanges: [10.200.0.10-10.200.0.15]}, ...}` | DHCP configuration for Subnet. |
| `spec.subnetDHCPConfig.dhcpServerAdditionalConfig` | object |  | e.g. `{reservedIPRanges: [10.200.0.10-10.200.0.15]}` | Additional DHCP server config for a VPC Subnet. |
| `spec.subnetDHCPConfig.dhcpServerAdditionalConfig.reservedIPRanges` | array of string |  | e.g. `[10.200.0.10-10.200.0.15]` | Reserved IP ranges. Supported formats include: ["192.168.1.1", "192.168.1.3-192.168.1.100"] |
| `spec.subnetDHCPConfig.mode` | string |  | `DHCPServer`, `DHCPRelay`, `DHCPDeactivated` | DHCP Mode. DHCPDeactivated will be used if it is not defined. It cannot switch from DHCPDeactivated to DHCPServer or DHCPRelay. |
| `spec.vlanConnectionName` | string |  | e.g. `<distributed VLAN connection>` | Distributed VLAN Connection name. |
| `spec.vpcName` | string |  | e.g. `${resource.vpc.name}` | VPC name of the Subnet. |
{{< /collapse >}}
<!-- /FIELDS:subnet -->

Minimal, our lab's management subnet:

```yaml
  snMgmt:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: crd.nsx.vmware.com/v1alpha1
        kind: Subnet
        metadata: {name: sn-mgmt}
        spec: {accessMode: Private, ipv4SubnetSize: 32}
```

A VM joins it by name, in an interface:
`network: {apiVersion: crd.nsx.vmware.com/v1alpha1, kind: Subnet, name: sn-mgmt}`.

**Status worth reading:** `status.networkAddresses`, `status.gatewayAddresses`,
`status.conditions` (`Realized`).

**Gotchas**

- DHCP is off by default. VMs still get addresses: VM Operator takes one
  from the subnet and hands it to the guest through the bootstrap provider.
- Subnets are NSX objects of the VPC. After a deployment is deleted they can
  outlive it for a few minutes; wait until the VPC lists none before reusing
  the addresses.

## Persistent Volume Claim

`CCI.Supervisor.Resource` with `apiVersion: v1`,
`kind: PersistentVolumeClaim`. A disk from a storage class, for a VM's
`volumes` or a pod.

| `spec` field | Notes |
|---|---|
| `storageClassName` | A storage class the namespace has. |
| `resources.requests.storage` | The size: `100Gi`. |
| `accessModes[]` | `ReadWriteOnce` for a VM disk; `ReadWriteMany` where the storage supports it. |
| `volumeMode` | `Filesystem` or `Block`. |
| `dataSource`, `dataSourceRef` | Restore from a snapshot or clone another claim. |

<!-- FIELDS:pvc -->
{{< collapse summary="Every field the platform accepts (23)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.accessModes` | array of string |  | e.g. `[ReadWriteOnce]` | accessModes contains the desired access modes the volume should have. |
| `spec.dataSource` | object |  | e.g. `{apiGroup: snapshot.storage.k8s.io, kind: <kind>}` | TypedLocalObjectReference contains enough information to let you locate the typed referenced object inside the same namespace. |
| `spec.dataSource.apiGroup` | string |  | e.g. `snapshot.storage.k8s.io` | APIGroup is the group for the resource being referenced. If APIGroup is not specified, the specified Kind must be in the core API group. |
| `spec.dataSource.kind` | string | yes | e.g. `<kind>` | Kind is the type of resource being referenced |
| `spec.dataSource.name` | string | yes | e.g. `<name>` | Name is the name of resource being referenced |
| `spec.dataSourceRef` | object |  | e.g. `{apiGroup: snapshot.storage.k8s.io, namespace: ns-source}` | TypedObjectReference contains enough information to let you locate the typed referenced object |
| `spec.dataSourceRef.apiGroup` | string |  | e.g. `snapshot.storage.k8s.io` | APIGroup is the group for the resource being referenced. If APIGroup is not specified, the specified Kind must be in the core API group. |
| `spec.dataSourceRef.kind` | string | yes | e.g. `<kind>` | Kind is the type of resource being referenced |
| `spec.dataSourceRef.name` | string | yes | e.g. `<name>` | Name is the name of resource being referenced |
| `spec.dataSourceRef.namespace` | string |  | e.g. `ns-source` | Namespace is the namespace of resource being referenced Note that when a namespace is specified, a gateway.networking.k8s.io/ReferenceGrant object is required in the referent namespace to ... |
| `spec.resources` | object |  | e.g. `{limits: {storage: 20Gi}, requests: {storage: 20Gi}}` | VolumeResourceRequirements describes the storage resource requirements for a volume. |
| `spec.resources.limits` | object |  | e.g. `{storage: 20Gi}` | Limits describes the maximum amount of compute resources allowed. |
| `spec.resources.requests` | object |  | e.g. `{storage: 20Gi}` | Requests describes the minimum amount of compute resources required. |
| `spec.selector` | object |  | e.g. `{matchExpressions: [{key: app, operator: In}], matchLabels: {tier: fast}}` | A label selector is a label query over a set of resources. The result of matchLabels and matchExpressions are ANDed. |
| `spec.selector.matchExpressions` | array of object |  | e.g. `[{key: app, operator: In}]` | matchExpressions is a list of label selector requirements. The requirements are ANDed. |
| `spec.selector.matchExpressions[].key` | string | yes | e.g. `app` | key is the label key that the selector applies to. |
| `spec.selector.matchExpressions[].operator` | string | yes | e.g. `In` | operator represents a key's relationship to a set of values. Valid operators are In, NotIn, Exists and DoesNotExist. |
| `spec.selector.matchExpressions[].values` | array of string |  | e.g. `[fast]` | values is an array of string values. If the operator is In or NotIn, the values array must be non-empty. If the operator is Exists or DoesNotExist, the values array must be empty. |
| `spec.selector.matchLabels` | object |  | e.g. `{tier: fast}` | matchLabels is a map of {key,value} pairs. |
| `spec.storageClassName` | string |  | e.g. `vsan-default-storage-policy` | storageClassName is the name of the StorageClass required by the claim. |
| `spec.volumeAttributesClassName` | string |  | e.g. `<volume attributes class>` | volumeAttributesClassName may be used to set the VolumeAttributesClass used by this claim. |
| `spec.volumeMode` | string |  | `Block`, `Filesystem` | volumeMode defines what type of volume is required by the claim. Value of Filesystem is implied when not included in claim spec. |
| `spec.volumeName` | string |  | e.g. `<existing PersistentVolume>` | volumeName is the binding reference to the PersistentVolume backing this claim. |
{{< /collapse >}}
<!-- /FIELDS:pvc -->

```yaml
  dataDisk:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: v1
        kind: PersistentVolumeClaim
        metadata: {name: web-01-data}
        spec:
          accessModes: [ReadWriteOnce]
          storageClassName: vsan-default-storage-policy
          resources:
            requests:
              storage: 5Gi
```

**Status worth reading:** `status.phase` (`Bound`), `status.capacity.storage`.

**Gotchas**

- The designer's form calls the field `accessMode`; the Supervisor refuses
  that spelling (`unknown field "spec.accessMode"`).
- A `-latebinding` storage class (WaitForFirstConsumer) puts no constraint on
  where the VM lands; our nested hosts' vSAN capacity disks use one.

## Secret

`CCI.Supervisor.Resource` with `apiVersion: v1`, `kind: Secret`. Key/value
data in the namespace. In a blueprint it mostly carries a VM's cloud-init or
Sysprep data, or a password a VM's `cloudConfig` references.

| Field | Notes |
|---|---|
| `stringData` | Plain values; the Supervisor encodes them. The easy one in a blueprint. |
| `data` | Base64-encoded values. |
| `type` | `Opaque` for your own data; `kubernetes.io/tls` and the other standard types. |
| `immutable` | `true` stops changes after creation. |

<!-- FIELDS:secret -->
{{< collapse summary="Every field the platform accepts (4)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `data` | object |  | e.g. `{password: <base64>}` | Data contains the secret data. Each key must consist of alphanumeric characters, '-', '_' or '.'. |
| `immutable` | boolean |  | e.g. `true` | Immutable, if set to true, ensures that data stored in the Secret cannot be updated (only object metadata can be modified). |
| `stringData` | object |  | e.g. `{password: ${input.password}}` | stringData allows specifying non-binary secret data in string form. It is provided as a write-only input field for convenience. |
| `type` | string |  | e.g. `Opaque` | Used to facilitate programmatic handling of secret data. |
{{< /collapse >}}
<!-- /FIELDS:secret -->

```yaml
  jumpConfig:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: v1
        kind: Secret
        metadata: {name: jump-bootstrap}
        type: Opaque
        stringData:
          user-data: |
            #cloud-config
            users:
              - name: student
                passwd: ${input.jumpPassword}
```

**Gotcha:** an input marked `encrypted: true` stays hidden in the request,
but whatever a Secret holds can be read by anyone allowed to read Secrets in
the namespace.

## Kubernetes Cluster

`CCI.Supervisor.Resource` with `apiVersion: cluster.x-k8s.io/v1beta1`,
`kind: Cluster`. A VKS cluster, described by a ClusterClass topology. The
designer's schema stops at `topology.variables`. What the variables can be
comes from the ClusterClass: `builtin-generic-v3.6.0` on our platform.

| `spec` field | Notes |
|---|---|
| `clusterNetwork` | **Required.** `pods.cidrBlocks`, `services.cidrBlocks`, `serviceDomain`. Without `services` VKS refuses the cluster: `spec.ClusterNetwork.Services must be defined`. |
| `topology.class` | **Required.** The ClusterClass. |
| `topology.classNamespace` | Where the ClusterClass lives; not in the designer's form. See the gotchas. |
| `topology.version` | **Required.** A Kubernetes release the Supervisor offers, for example `v1.35.5+vmware.1-vkr.1`. |
| `topology.controlPlane` | `replicas` (1 or 3), `metadata`, `machineHealthCheck`, node drain and deletion timeouts. |
| `topology.workers.machineDeployments[]` | `class: node-pool` (the only worker class), `name`, `replicas`, and `variables.overrides[]` per pool. |
| `topology.variables[]` | `name` and `value` pairs, below. |

<!-- FIELDS:cluster -->
{{< collapse summary="Every field the platform accepts (85)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `spec.availabilityGates` | array of object |  | e.g. `[{conditionType: <condition type>, polarity: Positive}]` | availabilityGates specifies additional conditions to include when evaluating Cluster Available condition. |
| `spec.availabilityGates[].conditionType` | string | yes | e.g. `<condition type>` | conditionType refers to a condition with matching type in the Cluster's condition list. If the conditions doesn't exist, it will be treated as unknown. |
| `spec.availabilityGates[].polarity` | string |  | `Positive`, `Negative` | polarity of the conditionType specified in this availabilityGate. Valid values are Positive, Negative and omitted. When omitted, the default behaviour will be Positive. |
| `spec.clusterNetwork` | object |  | e.g. `{pods: {cidrBlocks: [192.168.156.0/20]}, serviceDomain: cluster.local}` | clusterNetwork represents the cluster network configuration. |
| `spec.clusterNetwork.apiServerPort` | integer |  | e.g. `6443` | apiServerPort specifies the port the API Server should bind to. Defaults to 6443. |
| `spec.clusterNetwork.pods` | object |  | e.g. `{cidrBlocks: [192.168.156.0/20]}` | pods is the network ranges from which Pod networks are allocated. |
| `spec.clusterNetwork.pods.cidrBlocks` | array of string | yes | e.g. `[192.168.156.0/20]` | cidrBlocks is a list of CIDR blocks. |
| `spec.clusterNetwork.serviceDomain` | string |  | e.g. `cluster.local` | serviceDomain is the domain name for services. |
| `spec.clusterNetwork.services` | object |  | e.g. `{cidrBlocks: [10.96.0.0/12]}` | services is the network ranges from which service VIPs are allocated. |
| `spec.clusterNetwork.services.cidrBlocks` | array of string | yes | e.g. `[10.96.0.0/12]` | cidrBlocks is a list of CIDR blocks. |
| `spec.controlPlaneEndpoint` | object |  | e.g. `{host: 192.168.144.40, port: 6443}` | controlPlaneEndpoint represents the endpoint used to communicate with the control plane. |
| `spec.controlPlaneEndpoint.host` | string |  | e.g. `192.168.144.40` | host is the hostname on which the API server is serving. |
| `spec.controlPlaneEndpoint.port` | integer |  | e.g. `6443` | port is the port on which the API server is serving. |
| `spec.controlPlaneRef` | object |  | e.g. `{kind: KubeadmControlPlane, name: lab-vks-cp}` | controlPlaneRef is an optional reference to a provider-specific resource that holds the details for provisioning the Control Plane for a Cluster. |
| `spec.controlPlaneRef.apiVersion` | string |  | e.g. `controlplane.cluster.x-k8s.io/v1beta1` | API version of the referent. |
| `spec.controlPlaneRef.fieldPath` | string |  | e.g. `(set by the platform)` | If referring to a piece of an object instead of an entire object, this string should contain a valid JSON/Go field access statement, such as desiredState.manifest.containers[2]. |
| `spec.controlPlaneRef.kind` | string |  | e.g. `KubeadmControlPlane` | Kind of the referent. |
| `spec.controlPlaneRef.name` | string |  | e.g. `lab-vks-cp` | Name of the referent. |
| `spec.controlPlaneRef.namespace` | string |  | e.g. `ns-lab` | Namespace of the referent. |
| `spec.controlPlaneRef.resourceVersion` | string |  | e.g. `(set by the platform)` | Specific resourceVersion to which this reference is made, if any. |
| `spec.controlPlaneRef.uid` | string |  | e.g. `(set by the platform)` | UID of the referent. |
| `spec.infrastructureRef` | object |  | e.g. `{kind: VSphereCluster, name: lab-vks}` | infrastructureRef is a reference to a provider-specific resource that holds the details for provisioning infrastructure for a cluster in said provider. |
| `spec.infrastructureRef.apiVersion` | string |  | e.g. `vmware.infrastructure.cluster.x-k8s.io/v1beta1` | API version of the referent. |
| `spec.infrastructureRef.fieldPath` | string |  | e.g. `(set by the platform)` | If referring to a piece of an object instead of an entire object, this string should contain a valid JSON/Go field access statement, such as desiredState.manifest.containers[2]. |
| `spec.infrastructureRef.kind` | string |  | e.g. `VSphereCluster` | Kind of the referent. |
| `spec.infrastructureRef.name` | string |  | e.g. `lab-vks` | Name of the referent. |
| `spec.infrastructureRef.namespace` | string |  | e.g. `ns-lab` | Namespace of the referent. |
| `spec.infrastructureRef.resourceVersion` | string |  | e.g. `(set by the platform)` | Specific resourceVersion to which this reference is made, if any. |
| `spec.infrastructureRef.uid` | string |  | e.g. `(set by the platform)` | UID of the referent. |
| `spec.paused` | boolean |  | e.g. `true` | paused can be used to prevent controllers from processing the Cluster and all its associated objects. |
| `spec.topology` | object |  | e.g. `{class: builtin-generic-v3.6.0, classNamespace: vmware-system-vks-public}` | topology encapsulates the topology for the cluster. |
| `spec.topology.class` | string | yes | e.g. `builtin-generic-v3.6.0` | class is the name of the ClusterClass object to create the topology. |
| `spec.topology.classNamespace` | string |  | e.g. `vmware-system-vks-public` | classNamespace is the namespace of the ClusterClass that should be used for the topology. If classNamespace is empty or not set, it is defaulted to the namespace of the Cluster object. |
| `spec.topology.controlPlane` | object |  | e.g. `{replicas: 1, machineHealthCheck: {maxUnhealthy: 40%, nodeStartupTimeout: 10m}}` | controlPlane describes the cluster control plane. |
| `spec.topology.controlPlane.machineHealthCheck` | object |  | e.g. `{maxUnhealthy: 40%, nodeStartupTimeout: 10m}` | machineHealthCheck allows to enable, disable and override the MachineHealthCheck configuration in the ClusterClass for this control plane. |
| `spec.topology.controlPlane.machineHealthCheck.enable` | boolean |  | e.g. `true` | enable controls if a MachineHealthCheck should be created for the target machines. If false: No MachineHealthCheck will be created. |
| `spec.topology.controlPlane.machineHealthCheck.maxUnhealthy` | int or string |  | e.g. `40%` | maxUnhealthy specifies the maximum number of unhealthy machines allowed. Any further remediation is only allowed if at most "maxUnhealthy" machines selected by "selector" are not healthy. |
| `spec.topology.controlPlane.machineHealthCheck.nodeStartupTimeout` | string |  | e.g. `10m` | nodeStartupTimeout allows to set the maximum time for MachineHealthCheck to consider a Machine unhealthy if a corresponding Node isn't associated through a `Spec.ProviderID` field. |
| `spec.topology.controlPlane.machineHealthCheck.remediationTemplate` | object |  | e.g. `{apiVersion: <group>/<version>, kind: <remediation template kind>, name: <name>}` | remediationTemplate is a reference to a remediation template provided by an infrastructure provider. |
| `spec.topology.controlPlane.machineHealthCheck.unhealthyConditions` | array of object |  | e.g. `[{type: Ready, status: Unknown, timeout: 300s}]` | unhealthyConditions contains a list of the conditions that determine whether a node is considered unhealthy. The conditions are combined in a logical OR, i.e. |
| `spec.topology.controlPlane.machineHealthCheck.unhealthyRange` | string |  | e.g. `'[1-3]'` | unhealthyRange specifies the range of unhealthy machines allowed. |
| `spec.topology.controlPlane.metadata` | object |  | e.g. `{annotations: {owner: team-a}, labels: {app: web}}` | metadata is the metadata applied to the ControlPlane and the Machines of the ControlPlane if the ControlPlaneTemplate referenced by the ClusterClass is machine based. |
| `spec.topology.controlPlane.metadata.annotations` | object |  | e.g. `{owner: team-a}` | annotations is an unstructured key value map stored with a resource that may be set by external tools to store and retrieve arbitrary metadata. |
| `spec.topology.controlPlane.metadata.labels` | object |  | e.g. `{app: web}` | labels is a map of string keys and values that can be used to organize and categorize (scope and select) objects. May match selectors of replication controllers and services. |
| `spec.topology.controlPlane.nodeDeletionTimeout` | string |  | e.g. `10m` | nodeDeletionTimeout defines how long the controller will attempt to delete the Node that the Machine hosts after the Machine is marked for deletion. |
| `spec.topology.controlPlane.nodeDrainTimeout` | string |  | e.g. `10m` | nodeDrainTimeout is the total amount of time that the controller will spend on draining a node. The default value is 0, meaning that the node can be drained without any time limitations. |
| `spec.topology.controlPlane.nodeVolumeDetachTimeout` | string |  | e.g. `10m` | nodeVolumeDetachTimeout is the total amount of time that the controller will spend on waiting for all volumes to be detached. |
| `spec.topology.controlPlane.readinessGates` | array of object |  | e.g. `[{conditionType: <condition type>, polarity: Positive}]` | readinessGates specifies additional conditions to include when evaluating Machine Ready condition. This field can be used e.g. |
| `spec.topology.controlPlane.readinessGates[].conditionType` | string | yes | e.g. `<condition type>` | conditionType refers to a condition with matching type in the Machine's condition list. If the conditions doesn't exist, it will be treated as unknown. |
| `spec.topology.controlPlane.readinessGates[].polarity` | string |  | `Positive`, `Negative` | polarity of the conditionType specified in this readinessGate. Valid values are Positive, Negative and omitted. When omitted, the default behaviour will be Positive. |
| `spec.topology.controlPlane.replicas` | integer |  | e.g. `1` | replicas is the number of control plane nodes. |
| `spec.topology.controlPlane.variables` | object |  | e.g. `{overrides: [{name: vmClass, value: best-effort-medium}]}` | variables can be used to customize the ControlPlane through patches. |
| `spec.topology.controlPlane.variables.overrides` | array of object |  | e.g. `[{name: vmClass, value: best-effort-medium}]` | overrides can be used to override Cluster level variables. |
| `spec.topology.rolloutAfter` | string |  | e.g. `2026-10-01T22:00:00Z` | rolloutAfter performs a rollout of the entire cluster one component at a time, control plane first and then machine deployments. |
| `spec.topology.variables` | array of object |  | e.g. `[{name: vmClass, value: best-effort-small}]` | variables can be used to customize the Cluster through patches. They must comply to the corresponding VariableClasses defined in the ClusterClass. |
| `spec.topology.variables[].definitionFrom` | string |  | e.g. `<patch name>` | definitionFrom specifies where the definition of this Variable is from. Deprecated: This field is deprecated, must not be set anymore and is going to be removed in the next apiVersion. |
| `spec.topology.variables[].name` | string | yes | e.g. `vmClass` | name of the variable. |
| `spec.topology.variables[].value` | any | yes | e.g. `best-effort-small` | value of the variable. Note: the value will be validated against the schema of the corresponding ClusterClassVariable from the ClusterClass. |
| `spec.topology.version` | string | yes | e.g. `v1.35.5+vmware.1-vkr.1` | version is the Kubernetes version of the cluster. |
| `spec.topology.workers` | object |  | e.g. `{machineDeployments: [{name: np-1, class: node-pool}], machinePools: [{name: mp-1, ...}]}` | workers encapsulates the different constructs that form the worker nodes for the cluster. |
| `spec.topology.workers.machineDeployments` | array of object |  | e.g. `[{name: np-1, class: node-pool}]` | machineDeployments is a list of machine deployments in the cluster. |
| `spec.topology.workers.machineDeployments[].class` | string | yes | e.g. `node-pool` | class is the name of the MachineDeploymentClass used to create the set of worker nodes. |
| `spec.topology.workers.machineDeployments[].failureDomain` | string |  | e.g. `domain-c9` | failureDomain is the failure domain the machines will be created in. Must match a key in the FailureDomains map stored on the cluster object. |
| `spec.topology.workers.machineDeployments[].machineHealthCheck` | object |  | e.g. `{enable: true}` | machineHealthCheck allows to enable, disable and override the MachineHealthCheck configuration in the ClusterClass for this MachineDeployment. |
| `spec.topology.workers.machineDeployments[].metadata` | object |  | e.g. `{labels: {pool: np-1}}` | metadata is the metadata applied to the MachineDeployment and the machines of the MachineDeployment. At runtime this metadata is merged with the corresponding metadata from the ClusterClass. |
| `spec.topology.workers.machineDeployments[].minReadySeconds` | integer |  | e.g. `10` | minReadySeconds is the minimum number of seconds for which a newly created machine should be ready. Defaults to 0 (machine will be considered available as soon as it is ready) |
| `spec.topology.workers.machineDeployments[].name` | string | yes | e.g. `np-1` | name is the unique identifier for this MachineDeploymentTopology. The value is used with other unique identifiers to create a MachineDeployment's Name (e.g. |
| `spec.topology.workers.machineDeployments[].nodeDeletionTimeout` | string |  | e.g. `10m` | nodeDeletionTimeout defines how long the controller will attempt to delete the Node that the Machine hosts after the Machine is marked for deletion. |
| `spec.topology.workers.machineDeployments[].nodeDrainTimeout` | string |  | e.g. `10m` | nodeDrainTimeout is the total amount of time that the controller will spend on draining a node. The default value is 0, meaning that the node can be drained without any time limitations. |
| `spec.topology.workers.machineDeployments[].nodeVolumeDetachTimeout` | string |  | e.g. `10m` | nodeVolumeDetachTimeout is the total amount of time that the controller will spend on waiting for all volumes to be detached. |
| `spec.topology.workers.machineDeployments[].readinessGates` | array of object |  | e.g. `[{conditionType: <condition type>}]` | readinessGates specifies additional conditions to include when evaluating Machine Ready condition. This field can be used e.g. |
| `spec.topology.workers.machineDeployments[].replicas` | integer |  | e.g. `1` | replicas is the number of worker nodes belonging to this set. |
| `spec.topology.workers.machineDeployments[].strategy` | object |  | e.g. `{type: RollingUpdate, rollingUpdate: {maxSurge: 1}}` | strategy is the deployment strategy to use to replace existing machines with new ones. |
| `spec.topology.workers.machineDeployments[].variables` | object |  | e.g. `{overrides: [{name: vmClass, value: best-effort-large}]}` | variables can be used to customize the MachineDeployment through patches. |
| `spec.topology.workers.machinePools` | array of object |  | e.g. `[{name: mp-1, class: <machine pool class>}]` | machinePools is a list of machine pools in the cluster. |
| `spec.topology.workers.machinePools[].class` | string | yes | e.g. `<machine pool class>` | class is the name of the MachinePoolClass used to create the pool of worker nodes. |
| `spec.topology.workers.machinePools[].failureDomains` | array of string |  | e.g. `[domain-c9]` | failureDomains is the list of failure domains the machine pool will be created in. Must match a key in the FailureDomains map stored on the cluster object. |
| `spec.topology.workers.machinePools[].metadata` | object |  | e.g. `{labels: {pool: mp-1}}` | metadata is the metadata applied to the MachinePool. At runtime this metadata is merged with the corresponding metadata from the ClusterClass. |
| `spec.topology.workers.machinePools[].minReadySeconds` | integer |  | e.g. `10` | minReadySeconds is the minimum number of seconds for which a newly created machine pool should be ready. Defaults to 0 (machine will be considered available as soon as it is ready) |
| `spec.topology.workers.machinePools[].name` | string | yes | e.g. `mp-1` | name is the unique identifier for this MachinePoolTopology. The value is used with other unique identifiers to create a MachinePool's Name (e.g. |
| `spec.topology.workers.machinePools[].nodeDeletionTimeout` | string |  | e.g. `10m` | nodeDeletionTimeout defines how long the controller will attempt to delete the Node that the MachinePool hosts after the MachinePool is marked for deletion. |
| `spec.topology.workers.machinePools[].nodeDrainTimeout` | string |  | e.g. `10m` | nodeDrainTimeout is the total amount of time that the controller will spend on draining a node. The default value is 0, meaning that the node can be drained without any time limitations. |
| `spec.topology.workers.machinePools[].nodeVolumeDetachTimeout` | string |  | e.g. `10m` | nodeVolumeDetachTimeout is the total amount of time that the controller will spend on waiting for all volumes to be detached. |
| `spec.topology.workers.machinePools[].replicas` | integer |  | e.g. `2` | replicas is the number of nodes belonging to this pool. |
| `spec.topology.workers.machinePools[].variables` | object |  | e.g. `{overrides: [{name: vmClass, value: best-effort-large}]}` | variables can be used to customize the MachinePool through patches. |
{{< /collapse >}}
<!-- /FIELDS:cluster -->

The ClusterClass's variables (`builtin-generic-v3.6.0`); `vmClass` and
`storageClass` are required:

| Variable | What it sets |
|---|---|
| `vmClass` | The VM class for the nodes. |
| `storageClass` | The storage class for node disks. |
| `volumes` | Extra node disks: `name`, `capacity`, `mountPath`, `storageClass`. |
| `node` | `labels`, `taints` and `firewall` for the nodes. |
| `osConfiguration` | `ntp.servers`, `trust.additionalTrustedCAs`, `systemProxy` (`http`, `https`, `noProxy`), `user` (an administrator and its SSH key), `sshd`, `fips`, `grub`, `directoryJoin`, `ubuntuPro`, `tuned`, `securityContext`. |
| `kubernetes` | `endpointFQDNs`, `certificateRotation` (on by default), and API server, kubelet, controller-manager and etcd settings. |
| `networks` | The nodes' interfaces: one primary and optional secondary networks. |
| `resourceConfiguration` | `systemReserved` CPU and memory for the kubelet. |
| `vsphereOptions` | `persistentVolumes`: which storage classes the cluster's PVCs may use. |
| `bootstrapAddons` | The CNI, through `cniRef`. |

<!-- FIELDS:clusterclass-variables -->
{{< collapse summary="Every field the platform accepts (147)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `bootstrapAddons` | object |  | e.g. `{cniRef: {name: <CNI package config>, namespace: <its namespace>}}` | BootstrapAddons defines Addons to be installed on Cluster during bootstrapping. Only supported with Kubernetes 1.35 and above. |
| `bootstrapAddons.cniRef` | object | yes | e.g. `{name: <CNI package config>, namespace: <its namespace>}` | CNI Addon to instantiate for Cluster. Used to select CNI rather than ClusterBootstrap spec.CNI field. Compatible Addon/AddonRelease must exist. |
| `bootstrapAddons.cniRef.name` | string | yes | e.g. `<CNI package config>` | Name of the Addon being referenced. |
| `bootstrapAddons.cniRef.namespace` | string |  | e.g. `<its namespace>` | Namespace of the addon being referenced. If not specified, will use the default public namespace defined by the addon manager. |
| `kubeAPIServerFQDNs` | array of string |  | e.g. `[api.lab.example.com]` | Deprecated: This variable is deprecated. Use kubernetes.endpointFQDNs instead. This variable will be removed in a future release. |
| `kubernetes` | object |  | e.g. `{apiServerConfiguration: {logs: {flushFrequency: 5s, verbosity: 2}, ...}}` | Kubernetes configures cluster-wide settings for the Kubernetes cluster, typically applied to the control plane. Supported scopes: cluster, controlPlane, workers |
| `kubernetes.apiServerConfiguration` | object |  | e.g. `{logs: {flushFrequency: 5s, verbosity: 2}, maxMutatingRequestsInFlight: 200}` | APIServerConfiguration contains configuration options for the Kubernetes API server. |
| `kubernetes.apiServerConfiguration.logs` | object |  | e.g. `{flushFrequency: 5s, verbosity: 2}` | Logging configures the logging options for the API server, including log levels, formats, and output destinations. Refer to the Kubernetes component-base logs options for more information. |
| `kubernetes.apiServerConfiguration.logs.flushFrequency` | string |  | e.g. `5s` | FlushFrequency is the maximum time between log flushes. If specified as a string, it's parsed as a duration (e.g., "1s"). |
| `kubernetes.apiServerConfiguration.logs.format` | string |  | `text`, `json` | Format specifies the structure of log messages. Supported values are "text" (default) and "json". Corresponds to --logging-format flag. |
| `kubernetes.apiServerConfiguration.logs.verbosity` | integer |  | e.g. `2` | Verbosity is the threshold that determines which log messages are logged. Default is zero which logs only the most important messages. |
| `kubernetes.apiServerConfiguration.maxMutatingRequestsInFlight` | integer |  | e.g. `200` | MaxMutatingRequestsInFlight is the maximum number of parallel mutating requests. Every further request has to wait. |
| `kubernetes.apiServerConfiguration.maxRequestsInFlight` | integer |  | e.g. `400` | MaxRequestsInFlight is the maximum number of parallel non-long-running requests. Every further request has to wait. |
| `kubernetes.apiServerConfiguration.profiling` | boolean |  | e.g. `true` | Profiling enables profiling via web interface host:port/debug/pprof/ Default: false |
| `kubernetes.apiServerConfiguration.requestTimeout` | string |  | e.g. `60s` | RequestTimeout is the duration after which all non-long-running requests will be timed out. Corresponds to the --request-timeout flag. |
| `kubernetes.certificateRotation` | object |  | e.g. `{enabled: true, renewalDaysBeforeExpiry: 90}` | CertificateRotation configures options for the automatic rotation of control plane certificates which have a default validity of 12 months. |
| `kubernetes.certificateRotation.enabled` | boolean |  | default `true` | Enabled controls enablement of auto certificate rotation |
| `kubernetes.certificateRotation.renewalDaysBeforeExpiry` | integer |  | default `90` | RenewalDaysBeforeExpiry states the number of days before certificate expiry to initiate the renewal of certificates. |
| `kubernetes.endpointFQDNs` | array of string |  | e.g. `[api.lab.example.com]` | EndpointFQDNs Configure FQDN aliases for the control plane endpoint for example to allow users to connect to the cluster using https://k8s.prod.example.com/ |
| `kubernetes.etcdConfiguration` | object |  | e.g. `{maximumDBSizeGiB: 8}` | EtcdConfiguration contains configuration options for the etcd database used by Kubernetes. These settings control etcd behavior including database size limits and performance tuning. |
| `kubernetes.etcdConfiguration.maximumDBSizeGiB` | integer | yes | e.g. `8` | MaximumDBSizeGiB specifies the maximum size of the etcd database in GiB. This value is used to set --quota-backend-bytes for etcd. |
| `kubernetes.kubeControllerManagerConfiguration` | object |  | e.g. `{terminatedPodGCThreshold: 1000}` | KubeControllerManagerConfiguration contains configuration options for the kube-controller-manager. Supported scopes: cluster, controlPlane |
| `kubernetes.kubeControllerManagerConfiguration.terminatedPodGCThreshold` | integer |  | e.g. `1000` | TerminatedPodGCThreshold is the number of terminated pods that can exist before the terminated pod garbage collector starts deleting terminated pods. |
| `kubernetes.kubeletConfiguration` | object |  | e.g. `{allowedUnsafeSysctls: [net.core.somaxconn], eventBurst: 100}` | KubeletConfiguration contains configuration options for the kubelet running on worker nodes. |
| `kubernetes.kubeletConfiguration.allowedUnsafeSysctls` | array of string |  | e.g. `[net.core.somaxconn]` | AllowedUnsafeSysctls is a comma separated allowlist of unsafe sysctls or sysctl patterns (ending in `*`). All safe sysctls are enabled by default. |
| `kubernetes.kubeletConfiguration.containerLogMaxFiles` | integer |  | e.g. `5` | ContainerLogMaxFiles is the maximum number of container log files that can be present for a container. Default: 5 |
| `kubernetes.kubeletConfiguration.containerLogMaxSizeMiB` | integer |  | e.g. `10` | ContainerLogMaxSize defines the maximum size of the container log file before it is rotated in MiB. |
| `kubernetes.kubeletConfiguration.eventBurst` | integer |  | e.g. `100` | EventBurst is the maximum size of a burst of event creations, temporarily allows event creations to burst to this number, while still not exceeding eventRecordQPS. |
| `kubernetes.kubeletConfiguration.eventRecordQPS` | integer |  | e.g. `50` | EventRecordQPS is the maximum event creations per second. If 0, there is no limit enforced. Corresponds to --event-qps kubelet flag. |
| `kubernetes.kubeletConfiguration.healthzBindAddress` | string |  | e.g. `127.0.0.1` | HealthzBindAddress is the IP address for the healthz server to serve on. Default: "127.0.0.1" |
| `kubernetes.kubeletConfiguration.imageGCHighThresholdPercent` | integer |  | e.g. `85` | ImageGCHighThresholdPercent is the percent of disk usage after which image garbage collection is always run. The percent is calculated as this field value out of 100. |
| `kubernetes.kubeletConfiguration.imageGCLowThresholdPercent` | integer |  | e.g. `80` | ImageGCLowThresholdPercent is the percent of disk usage before which image garbage collection is never run. Lowest disk usage to garbage collect to. |
| `kubernetes.kubeletConfiguration.imageMaximumGCAge` | string |  | e.g. `168h` | ImageMaximumGCAge is the maximum age an image can be unused before it is garbage collected. |
| `kubernetes.kubeletConfiguration.imageMinimumGCAge` | string |  | e.g. `2m` | ImageMinimumGCAge is the minimum age for an unused image before it is garbage collected. Default: "2m" |
| `kubernetes.kubeletConfiguration.imagePullCredentialsVerificationPolicy` | string |  | `NeverVerify`, `NeverVerifyPreloadedImages`, `NeverVerifyAllowlistedImages`, `AlwaysVerify` | ImagePullCredentialsVerificationPolicy determines how credentials should be verified when pod requests an image that is already present on the node. |
| `kubernetes.kubeletConfiguration.logging` | object |  | e.g. `{flushFrequency: 5s, verbosity: 2}` | Logging specifies the logging configuration options for the kubelet. This controls log levels, formats, and output destinations for kubelet logs. |
| `kubernetes.kubeletConfiguration.logging.flushFrequency` | string |  | e.g. `5s` | FlushFrequency is the maximum time between log flushes. If specified as a string, it's parsed as a duration (e.g., "1s"). |
| `kubernetes.kubeletConfiguration.logging.format` | string |  | `text`, `json` | Format specifies the structure of log messages. Supported values are "text" (default) and "json". Corresponds to --logging-format flag. |
| `kubernetes.kubeletConfiguration.logging.verbosity` | integer |  | e.g. `2` | Verbosity is the threshold that determines which log messages are logged. Default is zero which logs only the most important messages. |
| `kubernetes.kubeletConfiguration.maxParallelImagePulls` | integer |  | e.g. `5` | MaxParallelImagePulls sets the maximum number of image pulls in parallel. This field is only used when SerializeImagePulls is false. |
| `kubernetes.kubeletConfiguration.maxPods` | integer |  | e.g. `110` | MaxPods is the number of pods that can run on this Kubelet. Default: 110 NOTE: By default, the maximum allowed value is 250. |
| `kubernetes.kubeletConfiguration.podPidsLimit` | integer |  | e.g. `4096` | PodPidsLimit is the maximum number of PIDs in any pod. Use Kubelet default (-1) when omitted. Default: nil |
| `kubernetes.kubeletConfiguration.preloadedImagesVerificationAllowlist` | array of string |  | e.g. `[registry.example.local/*]` | PreloadedImagesVerificationAllowlist specifies a list of images that are exempted from credential reverification for the "NeverVerifyAllowlistedImages" `imagePullCredentialsVerificationPolicy`. |
| `kubernetes.kubeletConfiguration.registryBurst` | integer |  | e.g. `10` | RegistryBurst is the maximum size of bursty pulls, temporarily allows pulls to burst to this number, while still not exceeding registryPullQPS. |
| `kubernetes.kubeletConfiguration.registryPullQPS` | integer |  | e.g. `5` | RegistryPullQPS is the limit of registry pulls per second. Set to 0 for no limit. Default: 5 |
| `kubernetes.kubeletConfiguration.serializeImagePulls` | boolean |  | e.g. `true` | SerializeImagePulls when enabled, tells the Kubelet to pull images one at a time. Default: true |
| `kubernetes.kubeletConfiguration.streamingConnectionIdleTimeout` | string |  | e.g. `4h` | StreamingConnectionIdleTimeout is the maximum time a streaming connection can be idle before the connection is automatically closed. |
| `kubernetes.security` | object |  | e.g. `{podSecurityStandard: {auditVersion: latest, enforceVersion: latest}, ...}` | Security configures Kubernetes specific security settings. |
| `kubernetes.security.podSecurityStandard` | object |  | e.g. `{auditVersion: latest, enforceVersion: latest}` | PodSecurityStandard configures the PodSecurityStandard settings for the cluster. |
| `kubernetes.security.podSecurityStandard.audit` | string |  | ``, `privileged`, `baseline`, `restricted` | Audit sets the level for the audit PodSecurityConfiguration mode. Policy violations trigger an audit annotation, but are otherwise allowed One of "", privileged, baseline, restricted. |
| `kubernetes.security.podSecurityStandard.auditVersion` | string |  | e.g. `latest` | AuditVersion can be used to pin the policy to the version that shipped with a given Kubernetes minor version (e.g. v1.31) when in audit mode. |
| `kubernetes.security.podSecurityStandard.deactivated` | boolean |  | default `false` | Deactivated disables the patches for Pod Security Standard via AdmissionConfiguration. |
| `kubernetes.security.podSecurityStandard.enforce` | string |  | ``, `privileged`, `baseline`, `restricted` | Enforce sets the level for the enforce PodSecurityConfiguration mode. Policy violations cause the pod to be rejected. |
| `kubernetes.security.podSecurityStandard.enforceVersion` | string |  | e.g. `latest` | EnforceVersion can be used to pin the policy to the version that shipped with a given Kubernetes minor version (e.g. |
| `kubernetes.security.podSecurityStandard.exemptions` | object |  | e.g. `{namespaces: [monitoring]}` | Exemptions can be statically configured based on (requesting) user, RuntimeClass, or namespace. A request meeting exemption criteria is ignored by the admission plugin. |
| `kubernetes.security.podSecurityStandard.warn` | string |  | ``, `privileged`, `baseline`, `restricted` | Warn sets the level for the warn PodSecurityConfiguration mode. Policy violations trigger a user-facing warning, but are otherwise allowed. |
| `kubernetes.security.podSecurityStandard.warnVersion` | string |  | e.g. `latest` | WarnVersion can be used to pin the policy to the version that shipped with a given Kubernetes minor version (e.g. v1.31) when in warn mode. |
| `kubernetes.security.resourceQuotaConfiguration` | object |  | e.g. `{enabled: false}` | ResourceQuotaConfiguration configures the ResourceQuota admission control settings for the cluster. |
| `kubernetes.security.resourceQuotaConfiguration.enabled` | boolean |  | default `false` | Enabled enables the patches for ResourceQuotaConfiguration via AdmissionConfiguration. |
| `networks` | object |  | e.g. `{interfaces: {primary: {network: {apiVersion: crd.nsx.vmware.com/v1alpha1, ...}}}}` | Networks defines the network configuration for the cluster |
| `networks.interfaces` | object |  | e.g. `{primary: {network: {apiVersion: crd.nsx.vmware.com/v1alpha1, kind: SubnetSet, ...}}}` | Interfaces describes one primary (eth0) and zero or more secondary interfaces attached to Node virtual machine. |
| `networks.interfaces.primary` | object |  | e.g. `{network: {apiVersion: crd.nsx.vmware.com/v1alpha1, kind: SubnetSet, ...}}` | Primary is the primary network interface which is used to connect the Kubernetes primary network for Load balancer, Service discovery, Pod traffic and management traffic etc. |
| `networks.interfaces.primary.mtu` | integer |  | e.g. `1500` | MTU is the Maximum Transmission Unit size in bytes. |
| `networks.interfaces.primary.network` | object | yes | e.g. `{apiVersion: crd.nsx.vmware.com/v1alpha1, kind: SubnetSet, name: <subnet set>}` | Network is the name of the network resource to which this interface is connected. |
| `networks.interfaces.primary.routes` | array of object |  | e.g. `[{to: 172.16.0.0/16, via: 10.244.0.1}]` | Routes is a list of optional, static routes. |
| `networks.interfaces.secondary` | array of object |  | e.g. `[{name: eth1, network: {apiVersion: crd.nsx.vmware.com/v1alpha1, kind: Subnet, ...}}]` | Secondary network is supported with network provider NSX-VPC and vsphere-network. |
| `networks.interfaces.secondary[].mtu` | integer |  | e.g. `1500` | MTU is the Maximum Transmission Unit size in bytes. |
| `networks.interfaces.secondary[].name` | string | yes | e.g. `eth1` | Name describes the unique name of this network interface, used to distinguish it from other network interfaces attached to node Virtual Machine. |
| `networks.interfaces.secondary[].network` | object | yes | e.g. `{apiVersion: crd.nsx.vmware.com/v1alpha1, kind: Subnet, name: storage-net}` | Network is the name of the network resource to which this interface is connected. |
| `networks.interfaces.secondary[].routes` | array of object |  | e.g. `[{to: 10.50.0.0/16, via: 10.250.0.1}]` | Routes is a list of optional, static routes. |
| `node` | object |  | e.g. `{firewall: {inboundRules: [{fromPort: 30000, protocol: TCP}]}, labels: {workload: web}}` | Node configures Kubernetes node specific settings. Supported scopes: cluster, controlPlane, workers |
| `node.firewall` | object |  | e.g. `{inboundRules: [{fromPort: 30000, protocol: TCP}]}` | Firewall specifies the firewall configuration that should be created on the node to allow specific kinds of traffic. |
| `node.firewall.inboundRules` | array of object | yes | e.g. `[{fromPort: 30000, protocol: TCP}]` | InboundRules is a list of firewall rules that will be configured on each node to allow or deny specific kinds of traffic. |
| `node.firewall.inboundRules[].fromPort` | integer |  | e.g. `30000` | FromPort is the low end (inclusive) of the port range that this rule applies to. |
| `node.firewall.inboundRules[].protocol` | int or string | yes | e.g. `TCP` | Protocol is the type of traffic that this rule applies to. Allowed protocols include "tcp", "udp", "icmp", or an any valid IANA protocol number. |
| `node.firewall.inboundRules[].source` | string |  | e.g. `10.0.0.0/8` | Source is the CIDR range of the originating traffic that this rule applies to. If unset, the rule will apply to any source network. |
| `node.firewall.inboundRules[].toPort` | integer |  | e.g. `32767` | ToPort is the high end (inclusive) of the port range that this rule applies to. |
| `node.labels` | object |  | e.g. `{workload: web}` | Labels is a list of user defined name-value pairs |
| `node.taints` | array of object |  | e.g. `[{key: dedicated, value: gpu}]` | Taints specifies the taints the Node API object should be registered with. If this field is unset, i.e. nil, it will be defaulted with a control-plane taint for control-plane nodes. |
| `node.taints[].effect` | string | yes | `NoSchedule`, `PreferNoSchedule`, `NoExecute` | Effect of the taint on pods that do not tolerate the taint. Valid effects are NoSchedule, PreferNoSchedule and NoExecute. |
| `node.taints[].key` | string | yes | e.g. `dedicated` | Key is the taint key to be applied to a node. |
| `node.taints[].value` | string | yes | e.g. `gpu` | Value is the taint value corresponding to the taint key. |
| `osConfiguration` | object |  | e.g. `{ntp: {servers: [172.30.0.34]}, ...}` | OSConfiguration configures the system settings of nodes that are independent of Kubernetes. Supported scopes: cluster, controlPlane, workers |
| `osConfiguration.directoryJoin` | object |  | e.g. `{credentialSecretRef: <Secret with the join account>, domain: example.local}` | DirectoryJoin configures the node to join a Windows Active Directory. Only supported on Windows at present. |
| `osConfiguration.directoryJoin.credentialSecretRef` | string | yes | e.g. `<Secret with the join account>` | CredentialSecretRef is the name of the secret containing Active Directory join credentials. |
| `osConfiguration.directoryJoin.domain` | string | yes | e.g. `example.local` | Domain is the FQDN of the Active Directory Kerberos domain to join. |
| `osConfiguration.directoryJoin.gmsaControlSecurityGroupDN` | string |  | e.g. `CN=gmsa-k8s,OU=Groups,DC=example,DC=local` | GMSAControlSecurityGroupDN is an optional Windows Active Directory security group that has permissions to access the password of the Group Managed Service Accounts. |
| `osConfiguration.directoryJoin.organizationalUnitDN` | string |  | e.g. `OU=K8s,DC=example,DC=local` | OrganizationalUnitDN is an optional organizational unit where the node will be added to in Active Directory. The value will be validated according to https://tools.ietf.org/html/rfc4514 |
| `osConfiguration.fips` | object |  | e.g. `{enabled: false}` | FIPS configures FIPS related settings for the Kubernetes cluster to run in FIPS mode. Supported scopes: cluster |
| `osConfiguration.fips.enabled` | boolean |  | default `false` | Enable specifies whether FIPS settings are enabled and enforced on the node |
| `osConfiguration.grub` | object |  | e.g. `{password: {secretRef: {name: <Secret>, key: password}, user: root}}` | GRUB configures GRUB Boot Loader. |
| `osConfiguration.grub.password` | object |  | e.g. `{secretRef: {name: <Secret>, key: password}, user: root}` | Password configures the password protection for GRUB Boot Loader (Only applicable on Linux). |
| `osConfiguration.grub.password.enabled` | boolean |  | default `false` | Enabled defines if the GRUB Boot Loader must be protected with a password |
| `osConfiguration.grub.password.secretRef` | object |  | e.g. `{name: <Secret>, key: password}` | SecretRef is the name of the secret containing the password to protect GRUB Key is the data.key field within the secret containing the password value. |
| `osConfiguration.grub.password.user` | string |  | e.g. `root` | User specifies the username to use for GRUB password protection. |
| `osConfiguration.ntp` | object |  | e.g. `{servers: [172.30.0.34]}` | NTP sets the time servers that will be used by nodes in the cluster. By default, NTP servers are inherited from vCenter. |
| `osConfiguration.ntp.servers` | array of string | yes | e.g. `[172.30.0.34]` | NTP sets the time servers that will be used by nodes in this cluster. By default, NTP servers are inherited from vCenter. |
| `osConfiguration.securityContext` | object |  | e.g. `{appArmor: {profiles: [{name: <AppArmor profile>}]}}` | SecurityContext holds security configurations that will be applied to node. |
| `osConfiguration.securityContext.appArmor` | object |  | e.g. `{profiles: [{name: <AppArmor profile>}]}` | AppArmor configures the appArmor profiles of the node. Supported scopes: cluster, controlPlane, workers Only supported on Ubuntu and Photon nodes. |
| `osConfiguration.securityContext.appArmor.profiles` | array of object | yes | e.g. `[{name: <AppArmor profile>}]` | Profiles is a list of appArmor profiles to be added to the node. |
| `osConfiguration.sshd` | object |  | e.g. `{banner: Authorised use only}` | SSHD configures the sshd config of the node. |
| `osConfiguration.sshd.banner` | string |  | e.g. `Authorised use only` | Banner specifies the login message used for sending a legal warning message before authentication |
| `osConfiguration.systemProxy` | object |  | e.g. `{http: http://proxy.example.local:3128, https: http://proxy.example.local:3128}` | SystemProxy configures parameters that reference a proxy server for outbound cluster connections. |
| `osConfiguration.systemProxy.http` | string | yes | e.g. `http://proxy.example.local:3128` | HTTP is the proxy server to be used for all http connections. This should be a hostname or dotted numerical IP address. |
| `osConfiguration.systemProxy.https` | string | yes | e.g. `http://proxy.example.local:3128` | HTTPS configures the proxy server to be used for all https connections. This should be a hostname or dotted numerical IP address. |
| `osConfiguration.systemProxy.noProxy` | array of string | yes | e.g. `[.example.local, 10.0.0.0/8]` | NoProxy configures the list of hostnames and CIDR ranges that should be reached without the configured proxy servers. |
| `osConfiguration.trust` | object |  | e.g. `{additionalTrustedCAs: [{caCert: {secretRef: {name: corp-ca}}}]}` | Trust configures system-wide certificate trust for nodes |
| `osConfiguration.trust.additionalTrustedCAs` | array of object | yes | e.g. `[{caCert: {secretRef: {name: corp-ca}}}]` | AdditionalTrustedCAs is a list of additional CAs to be added to the system trust store of nodes. |
| `osConfiguration.trust.additionalTrustedCAs[].caCert` | object | yes | e.g. `{secretRef: {name: corp-ca, key: ca.crt}}` | SecretContent configures a reference to or content of secret data. |
| `osConfiguration.tuned` | object |  | e.g. `{active: [<tuned profile>], profiles: {<profile name>: <TunedProfile reference>}}` | TuneD injects TuneD profiles and activate specified profile on Linux nodes. Only supported on Linux. |
| `osConfiguration.tuned.active` | array of string | yes | e.g. `[<tuned profile>]` | Active is a list of tuned profile name will be activated on node. |
| `osConfiguration.tuned.profiles` | object |  | e.g. `{<profile name>: <TunedProfile reference>}` | Profiles is a map of tuned profiles will be injected on node. Key is the desired tuned profile name, value is the TunedProfile CR reference which contains the profile content. |
| `osConfiguration.ubuntuPro` | object |  | e.g. `{services: [usg], settings: [{key: <setting>, value: <value>}]}` | UbuntuPro configures the Ubuntu Pro subscription of the node. Only supported on Ubuntu. |
| `osConfiguration.ubuntuPro.services` | array of string |  | e.g. `[usg]` | Services specifies the Ubuntu Pro services to be enabled. |
| `osConfiguration.ubuntuPro.settings` | array of object |  | e.g. `[{key: <setting>, value: <value>}]` | Settings specifies the Ubuntu Pro client (ubuntu-advantage-tools) settings to be configured. |
| `osConfiguration.ubuntuPro.settings[].key` | string | yes | e.g. `<setting>` |  |
| `osConfiguration.ubuntuPro.settings[].value` | string | yes | e.g. `<value>` |  |
| `osConfiguration.ubuntuPro.tokenSecretRef` | string | yes | e.g. `<Secret with the Pro token>` | TokenSecretRef is the name of the secret containing a valid Ubuntu Pro Subscription token. The secret must have a key token with the content of a valid token. |
| `osConfiguration.user` | object |  | e.g. `{passwordSecret: {key: password, name: <Secret>}, ...}` | User is an administrative user that will be created on all nodes. If not set, this is defaulted to "vmware-system-user". |
| `osConfiguration.user.password` | object |  | e.g. `{renewalDaysBeforeExpiry: 30}` | Password configures the password policy such as password max age and renewal settings. |
| `osConfiguration.user.password.renewalDaysBeforeExpiry` | integer |  | e.g. `30` | RenewalDaysBeforeExpiry configures the days to renew the password before it gets expired. |
| `osConfiguration.user.passwordSecret` | object |  | e.g. `{key: password, name: <Secret>}` | Key is the data.key field within the secret containing the password value. If not specified, the secret will be automatically generated as <cluster name>-ssh-password. |
| `osConfiguration.user.passwordSecret.key` | string | yes | e.g. `password` | Key is the data.key field within the secret containing the password value. For Linux, this must be the hashed value that should be inserted into /etc/shadow. |
| `osConfiguration.user.passwordSecret.name` | string | yes | e.g. `<Secret>` | Name is the name of the secret containing the password for the administrative account. |
| `osConfiguration.user.requirePasswordOnSudo` | boolean |  | e.g. `true` | RequirePasswordOnSudo configures whether password re-authentication is required on sudo. |
| `osConfiguration.user.sshAuthorizedKey` | string |  | e.g. `ssh-ed25519 AAAA... ops@admin` | The string of the SSH public key that is to be used for the administrative account. The public key must be of any FIPS-140 approved algorithm. |
| `osConfiguration.user.user` | string | yes | e.g. `vmware-system-user` | Name is the name of the user to be created. By default, this is vmware-system-user. |
| `resourceConfiguration` | object |  | e.g. `{systemReserved: {cpu: 500m, memory: 1Gi}}` | ResourceConfiguration configures kubelet resource options. Currently, only CPU and memory reservations are supported. |
| `resourceConfiguration.systemReserved` | object |  | e.g. `{cpu: 500m, memory: 1Gi}` | SystemReserved defines the system reserved CPU and memory reservations. |
| `resourceConfiguration.systemReserved.automatic` | boolean |  | default `true` | Automatic controls the automatic calculation of system reserved resources. |
| `resourceConfiguration.systemReserved.cpu` | int or string |  | e.g. `500m` | CPU describes the number of CPU cores reserved for system processes. |
| `resourceConfiguration.systemReserved.memory` | int or string |  | e.g. `1Gi` | Memory describes the memory resources reserved for system processes. |
| `storageClass` | string | yes | e.g. `vsan-default-storage-policy` | StorageClass sets the StorageClass that will be used to create node root volumes. |
| `vmClass` | string | yes | e.g. `best-effort-small` | VMClass sets the VMClass that will be used to create nodes. Supported scopes: cluster, controlPlane, workers |
| `volumes` | array of object |  | e.g. `[{name: containerd, capacity: 50Gi}]` | Volumes configures additional disks to be attached to node virtual machines. Supported scopes: cluster, controlPlane, workers |
| `volumes[].capacity` | string | yes | e.g. `50Gi` | Capacity defines the storage capacity of the volume. |
| `volumes[].mountPath` | string | yes | e.g. `/var/lib/containerd` | MountPath defines the mount path for the volume. |
| `volumes[].name` | string | yes | e.g. `containerd` | Name defines the name of the volume. |
| `volumes[].storageClass` | string |  | e.g. `vsan-default-storage-policy` | StorageClass defines the Storage class to use for the volume. |
| `vsphereOptions` | object |  | e.g. `{persistentVolumes: {availableStorageClasses: [vsan-default-storage-policy], ...}}` | VSphereOptions configures vSphere specific options related to nodes Supported scopes: cluster, controlPlane, workers |
| `vsphereOptions.persistentVolumes` | object |  | e.g. `{availableStorageClasses: [vsan-default-storage-policy], ...}` | PersistentVolumes configures what is available for PVCs to be used in the cluster. |
| `vsphereOptions.persistentVolumes.availableStorageClasses` | array of string |  | e.g. `[vsan-default-storage-policy]` | AvailableStorageClasses lists the storage classes that can be used in the cluster. |
| `vsphereOptions.persistentVolumes.availableVolumeSnapshotClasses` | array of string |  | e.g. `[volumesnapshotclass-delete]` | AvailableVolumeSnapshotClasses lists the volume snapshot classes that can be used in the cluster. |
| `vsphereOptions.persistentVolumes.customizableStorageClassAnnotations` | array of string |  | e.g. `[<annotation>]` | CustomizableStorageClassAnnotations is a list of annotation keys set on the storage classes within the cluster which can be customized by the user. |
| `vsphereOptions.persistentVolumes.customizableStorageClassLabels` | array of string |  | e.g. `[<label>]` | CustomizableStorageClassLabels is a list of label keys set on the storage classes within the cluster which can be customized by the user. |
| `vsphereOptions.persistentVolumes.defaultStorageClass` | string |  | e.g. `vsan-default-storage-policy` | DefaultStorageClass sets the default storage class inside the cluster. |
| `vsphereOptions.persistentVolumes.defaultVolumeSnapshotClass` | string |  | e.g. `volumesnapshotclass-delete` | DefaultVolumeSnapshotClass sets the default volume snapshot class inside the cluster. |
{{< /collapse >}}
<!-- /FIELDS:clusterclass-variables -->

Recipe, one control plane node and one worker, as we deployed it (ready in
four minutes):

```yaml
  k8s:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest:
        apiVersion: cluster.x-k8s.io/v1beta1
        kind: Cluster
        metadata: {name: dev-01}
        spec:
          clusterNetwork:
            pods: {cidrBlocks: [192.168.156.0/20]}
            services: {cidrBlocks: [10.96.0.0/12]}
            serviceDomain: cluster.local
          topology:
            class: builtin-generic-v3.6.0
            classNamespace: vmware-system-vks-public
            version: v1.35.5+vmware.1-vkr.1
            controlPlane:
              replicas: 1
            workers:
              machineDeployments:
                - class: node-pool
                  name: np-1
                  replicas: 1
            variables:
              - name: vmClass
                value: best-effort-small
              - name: storageClass
                value: vsan-default-storage-policy
              - name: osConfiguration
                value:
                  ntp:
                    servers: [172.30.0.34]
      wait:
        conditions:
          - type: Ready
            status: "True"
```

The same cluster in `v1beta2`, the version the Supervisor recommends; the
class becomes a reference with its namespace:

```yaml
        apiVersion: cluster.x-k8s.io/v1beta2
        kind: Cluster
        metadata: {name: dev-01}
        spec:
          clusterNetwork:
            pods: {cidrBlocks: [192.168.156.0/20]}
            services: {cidrBlocks: [10.96.0.0/12]}
            serviceDomain: cluster.local
          topology:
            classRef:
              name: builtin-generic-v3.6.0
              namespace: vmware-system-vks-public
            version: v1.35.5+vmware.1-vkr.1
            controlPlane: {replicas: 1}
            workers:
              machineDeployments:
                - {class: node-pool, name: np-1, replicas: 1}
            variables:
              - {name: vmClass, value: best-effort-small}
              - {name: storageClass, value: vsan-default-storage-policy}
```

**Status worth reading:** `status.phase`, `status.conditions`; the kubeconfig
is in the namespace as the Secret `<cluster>-kubeconfig` (ours:
`dev-01-kubeconfig`).

**Gotchas**

- Every namespace gets copies of a few ClusterClasses, on f06
  `builtin-generic-v3.1.0` to `v3.3.0`; Broadcom's ClusterClass matrix marks
  `v3.3.0` deprecated for VKS 3.6 and 3.7, and Broadcom's own 9.1 sample still
  uses it. The newer classes live only in `vmware-system-vks-public`: name
  that namespace (`classNamespace`, or `classRef.namespace` in `v1beta2`) to
  use them.
- The palette's `v1beta1` works, with a deprecation warning.
- Nodes run Photon OS unless the cluster carries the annotation
  `run.tanzu.vmware.com/resolve-os-image: os-name=ubuntu`.
- `topology.version` must be a release the Supervisor lists as ready and
  compatible; on f06 those were `v1.32.x` to `v1.35.5`.
- VKS needs the VPC's load balancer for the cluster's API endpoint, so the
  namespace must use a VPC that has one.

## Util.PasswordEntry

`type: Util.PasswordEntry`. Not in the palette, but one of the five types: it
generates a password, or takes one you give it, and hashes it at request
time.

| Property | Notes |
|---|---|
| `length` | Generate a password of this length. Default 14. |
| `password` | A password to use instead, when `length` is not set. |
| `generatedPassword` | Computed: the generated password. |
| `sha512crypt` | Computed: the password's SHA-512 crypt hash (`$6$...`). |

<!-- FIELDS:password -->
{{< collapse summary="Every field the platform accepts (3)" >}}
| Field | Type | Req. | Values | Description |
|---|---|---|---|---|
| `count` | integer |  | default `1` | The number of resource instances to be created. |
| `length` | integer |  | default `14` | Length of the password to be auto generated |
| `password` | string |  | e.g. `${input.adminPassword}` | Password value received as an input when length is not specified |
{{< /collapse >}}
<!-- /FIELDS:password -->

```yaml
  pw:
    type: Util.PasswordEntry
    properties:
      length: 20
```

VCF Automation stores both computed values as encrypted secrets
(`((secret:v1:...))`), so the deployment doesn't show them. Where the hash is
used decides how to write it:

- In a raw cloud-config held in a Secret, it is a string:
  `hashed_passwd: ${resource.pw.sha512crypt}`.
- In a VM's inline `cloudConfig` it must be a Secret reference, so put it in
  a Secret first:

  ```yaml
  webPw:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.ns.id}
      manifest:
        apiVersion: v1
        kind: Secret
        metadata: {name: web-pw}
        type: Opaque
        stringData:
          ops-passwd: ${resource.pw.sha512crypt}
  ```

## Complete, tested blueprints

The five blueprints we deployed to test this guide, as they ran:

| File | What it builds | Result |
|---|---|---|
| `test1-vpc.yaml` | A VPC, its attachment, an external IP allocation, a group, a gateway firewall policy referencing the group, a namespace in the new VPC, a generated password, two counted Secrets holding its hash | Created in 2 min 15 s; every VPC object `Realized` |
| `test1b-nat.yaml` | A DNAT rule on that VPC | Created; NSX realized it without the port |
| `test3-workload.yaml` | In an existing VPC with a load balancer: a namespace, a subnet, a PVC, a VM group with a boot order, two Ubuntu VMs (cloud-init user with key and hashed password, data disk, subnet, anti-affinity), a LoadBalancer service | Created in 2 min; SSH through the load balancer as the cloud-init user |
| `test4-vks.yaml` | A VKS cluster, one control plane node and one worker, `builtin-generic-v3.6.0` | Ready in 4 min |
| `test5-ipwait.yaml` | One VM whose output is its IP | Output `172.30.0.2` |

## Downloads

- [`vcfa-91-blueprint-reference.zip`](/files/vcfa-91-blueprint-reference.zip):
  the five test blueprints; the five base types as VCF Automation's API
  returns them; the fifteen palette schemas from the designer and the palette
  map; and the field tables of this guide as Markdown.

## Why this matters outside the lab

Self-service on VCF Automation All Apps is only as good as its blueprints.
And a blueprint is only as good as its author's knowledge of the fields,
which are mostly documented somewhere else, or nowhere.

The cost of not knowing shows up late. The designer saves the blueprint,
the validator passes it, and the request fails ten minutes in. Or worse, it
succeeds, with a NAT rule that forwards every port or a firewall rule that
allows any service.

Knowing what the platform actually enforces turns that into a five-second
dry run. It also turns a catalog item from a demo into something a team can
depend on.

## Rules learned

- The palette is five resource types. Learn `CCI.Supervisor.Resource` and
  `CCI.VPC.Configuration` and you can write every item by hand, including
  kinds the palette doesn't show.
- VCF Automation's validation checks a resource's own properties, never the
  manifest or the VPC spec inside. Dry-run manifests against the Supervisor;
  test VPC objects by deploying them.
- Where the designer's form and the platform disagree, the platform wins:
  `accessModes`, `labelSelector`, VM affinity terms ending
  `PreferredDuringExecution`.
- Outputs are computed once. Wait for what they read: a VM's address needs
  the condition `VirtualMachineGuestNetworkConfigSynced`.
- A blueprint VPC has no load balancer and can't get one, so LoadBalancer
  services and VKS need a VPC made in the UI.
- Name firewall services (`":HTTPS"`) instead of port sets, give every rule a
  `from`, and treat a NAT rule as mapping the whole address.
- Inline cloud-init passwords are Secret references; `count.index` needs
  `allocatePerInstance: true`.

## Broadcom documentation

- [Managing Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation.html): blueprints, the designer, inputs, versions, property groups and custom forms.
- [Sample Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html): Broadcom's samples: VMs, `count` with `allocatePerInstance`, a VM with a VKS cluster, a VPC with a namespace, a VM group with affinity.
- [Specifying formatVersion in Blueprints](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/specifying-formatversion-in-your-blueprints.html): what `formatVersion: 2` adds, including outputs and `__deploymentOverview`.
- [Creating bindings and dependencies between resources](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/bindings-and-dependencies.html): `dependsOn` and property bindings, and how each orders the build.
- [Input Property Groups](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups/input-property-groups.html) and [Constant Property Groups](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups/constant-property-groups-in-vcf-automation-for-all-apps.html): `${input.<group>.<property>}` and `${propgroup.<group>.<property>}`.
- [Managing Secrets in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/administering-all-apps-organizations-in-vcfa-automation/managing-secrets-in-vcfa.html): `${secret.<name>}`, organization and project secrets.
- [VCF Automation blueprint designs that prepare for day 2 changes](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/preparing-for-day-2.html): re-applying a blueprint versus day-2 actions, and bindings in day 2.
- [Create a Namespace Class in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-projects-in-vcfa/create-a-namespace-class.html): what a namespace class sets, and so what a blueprint namespace must add.
- [Create a Virtual Private Cloud in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/adding-and-managing-virtual-private-clouds/add-a-vpc.html): a VPC's connectivity profile, private CIDRs and load balancing, and that VKS needs load balancing.
- [Create a NAT Rule for a VPC in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/adding-and-managing-virtual-private-clouds/add-a-vpc/create-a-nat-rule-for-a-vpc-in-vcf-automation(1).html): the NAT actions, external addresses and priorities behind `VPCNATRule`.
- [Secure North-South boundaries for Transit Gateways and VPCs (vDefend 9.1)](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/vdefend/vdefend-firewall/9-1/vcf-automation-integration-with-vdefend-firewall/security-management-workflow.html): VPC gateway firewall policies, rules realized on the edges, and the activation flag in the security profile.
- [Deploying and Managing Virtual Machines in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane.html): VM classes, images, storage classes and zones, with a pointer to the VM Operator API.
- [Using the Versioned ClusterClass](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/managing-vsphere-kuberenetes-service-clusters-and-workloads/provisioning-tkg-service-clusters/using-the-cluster-v1beta1-api/using-the-versioned-clusterclass.html): the ClusterClass matrix per VKS release and `vmware-system-vks-public`.
- [v1beta1/v1beta2 Example: Default Cluster](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/managing-vsphere-kuberenetes-service-clusters-and-workloads/provisioning-tkg-service-clusters/using-the-cluster-v1beta1-api/using-the-versioned-clusterclass/v1beta1-example-default-cluster.html): the minimum cluster and the CIDR rules.
- [ClusterClass Variable Reference](https://developer.broadcom.com/xapis/vmware-vsphere-kubernetes-service/3.7.0/variable-docs.html): every variable of the builtin-generic classes, and where each can be overridden.
- [VM Status Information Missing in VCF Automation 9.0.x Deployments (KB 435137)](https://knowledge.broadcom.com/external/article/435137/vm-status-information-missing-in-vcf-aut.html): where the designer's default VM `wait` comes from.

The VM Operator API itself is documented upstream, outside Broadcom, and
Broadcom's VM Service pages link there: [v1alpha5 reference](https://vm-operator.readthedocs.io/en/latest/ref/api/v1alpha5/).

---
*Lab environment; opinions my own. Every snippet was validated, dry-run or
deployed on a live VCF 9.1 environment; the field tables come from the
platform's own schemas.*
