---
title: "One VKS cluster, two ways: kubectl vs VCF Automation All Apps"
date: 2026-09-16T06:50:00+01:00
draft: false
tags: [vcf, vks, kubernetes, vcf-automation, all-apps, vcf-operations]
products: ["VKS", "VCF Automation"]
series: ["All Apps in Practice"]
seriesPart: 1
cover:
  image: "/images/post10-hero-vks-two-ways.svg"
  alt: "The same Cluster manifest applied by kubectl and requested through the catalog — and what the second path adds for free"
  hidden: false
summary: "I built the same VKS cluster twice on the same supervisor: once with kubectl apply, once as a VCF Automation All Apps request. The Cluster object is identical. Everything around it isn't — and the payoff table is what you get for free the second way: catalog, quota class, org RBAC, VCF Operations visibility."
---

The `Cluster` manifest is the same. That's the point of this post, and
also the punchline: **VKS is VKS** whichever door you walk through. What
differs is everything wrapped around the cluster — who can ask for it,
what limits it, who can see it, and how it shows up in operations tooling.

So: two clusters, one supervisor, one ClusterClass, two paths.

## Path A: kubectl, the way we've always done it

```
kubectl vsphere login --server <supervisor> --tanzu-kubernetes-cluster-namespace demo
kubectl apply -f cluster.yaml
```

```yaml
apiVersion: cluster.x-k8s.io/v1beta1
kind: Cluster
spec:
  clusterNetwork: { pods, services, serviceDomain }   # set all three — see below
  topology:
    class: builtin-generic-v3.6.0
    classNamespace: vmware-system-vks-public          # the gotcha
    version: v1.35.5+vmware.1
    controlPlane: {replicas: 1}
    workers: { one node pool, 2 replicas }
    variables: [ vmClass, storageClass ]
```

Fifteen minutes later: a cluster. Requires a vSphere namespace that
somebody (an admin) created, with a content library attached, a VM class
assigned and quota set — all in the vSphere Client, by hand.

## Path B: the same manifest, as a catalog request

In All Apps the cluster is a `CCI.Supervisor.Resource` inside a [blueprint](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html),
sitting next to a `CCI.Supervisor.Namespace`:

```yaml
resources:
  namespace:
    type: CCI.Supervisor.Namespace
    properties:
      generateName: ${input.name}-
      className: large                      # quota comes from the class
      regionName: f06
      vpcName: ${input.vpc}
      contentSources: [{name: f06-vks-lib01, type: ContentLibrary}]
  cluster:
    type: CCI.Supervisor.Resource
    properties:
      context: ${resource.namespace.id}
      manifest: <the SAME Cluster object as above>
```

Publish it, and a tenant user requests it from a tile:

![VCFA: VKS cluster list as the tenant sees it](/images/ui/u6a-vks-cluster-list.jpg)
![VCFA: cluster detail](/images/ui/u6-vks-cluster-detail.jpg)

Fifteen minutes later: a cluster. Byte-identical `Cluster` object.

## What path B adds for free

| | kubectl | All Apps request |
|---|---|---|
| Who can create | anyone with a kubeconfig to that namespace | org users with catalog entitlement (org RBAC) |
| Namespace | pre-created by an admin, by hand | created by the request, from a **class** |
| Quota | set per namespace in the vSphere Client | inherited from the namespace class (`small`/`medium`/`large`) |
| Content library | admin attaches manually | `contentSources` on the blueprint |
| Networking | whatever the namespace has | pinned to a tenant VPC by `vpcName` |
| Sizing choices | edit YAML | form inputs with enums (worker count, VM class) |
| Record | `kubectl get cluster` | a **deployment** with inputs, owner, history, day-2 actions |
| Visibility | supervisor only | VCFA inventory **and** VCF Operations |

That last row is the one operations teams care about:

![VCF Operations: the VKS cluster object with gauges and time series](/images/ui/u8-ops-vks-summary.jpg)
![VCF Operations: topology view — the cluster and the apps on it, by name](/images/ui/u9-ops-vks-topology.jpg)

The VCFA-deployed cluster appears in Ops' object model — supervisor →
namespace → cluster → nodes → the workloads running on it — and its demo
apps show up by name in the topology tab. The kubectl-built cluster is
*also* visible to Ops (it's the same supervisor, after all), but it has no
deployment, no owner, no request history and no quota lineage. It's a
thing that exists, not a thing that was *provided*.


## The four gotchas, in order of how much time they cost

Both paths share the same four traps on VKS 1.35 / VCF 9.1:

1. **Our VCFA-created namespace had no content library.** Zero
   `VirtualMachineImage`s → no cluster possible. `contentSources` in the
   blueprint, or attach by hand. The 9.1 docs say a namespace class
   [gets a content library automatically](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-projects-in-vcfa/create-a-namespace-class.html); our `large` class had none
   assigned.
2. **`ClusterClass` lives in `vmware-system-vks-public`.** It 404s from
   the workload namespace unless the spec sets
   `topology.classNamespace`.
3. **The default Quick Start namespace is 1000M CPU / 1000Mi.** Unusable
   for a cluster. Use a real class: `small` 10000M/10000Mi, `medium`
   20000M, `large` 40000M.
4. **VKS 1.35 enforces PodSecurity `restricted` by default.** Demo apps
   that run as root get a ReplicaSet and *no pods*; the events say
   `FailedCreate`. Label the app namespace
   `pod-security.kubernetes.io/enforce=privileged` (or fix the apps).

Plus one that only shows up later: set `clusterNetwork.serviceDomain`
explicitly. It's immutable after create, and a cluster without it produces
a service DNS name that some add-ons build wrongly (`....svc.` with no
domain). And pick a pod CIDR that doesn't shadow your VPC's external range
— the stock `192.168.0.0/16` hid the org's `192.168.144.0/21` from inside
the cluster.

## So which one?

Use **kubectl** when you're the platform team proving something on a
supervisor, or debugging. Use **All Apps** the moment a second person needs
a cluster: the request form is the interface, the namespace class is the
guardrail, the deployment is the audit trail, and Ops sees it as a
provided service rather than a stray object.

The cluster's the same either way. The *service* isn't.

## Why this matters outside the lab

The business case for the second path is governance without friction.
Development teams get Kubernetes clusters on request; the platform team
gets quotas, ownership, RBAC and a monitoring view of every cluster for
free. That's the difference between a managed Kubernetes *service* and a
collection of clusters nobody can account for — and it's typically the
gap that stops organisations offering Kubernetes broadly at all. Everything
the developers touch stays standard Kubernetes; the control lands around
it, not on it.

## Rules learned

- The `Cluster` object is identical across paths — All Apps wraps it, it
  doesn't change it.
- What All Apps adds: catalog RBAC, class-based quota, library attach,
  VPC pinning, deployment history, and a place in the Ops object model.
- Four traps on 1.35: no library on our namespace class, `classNamespace`,
  tiny default quota, PodSecurity `restricted`.
- Set `serviceDomain` and a non-shadowing pod CIDR at create; both are
  immutable.

## Broadcom documentation

- [Workflow for Provisioning VKS Clusters Using kubectl](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/managing-vsphere-kuberenetes-service-clusters-and-workloads/provisioning-tkg-service-clusters/workflow-for-provisioning-tkg-clusters-using-kubectl.html): path A, from Supervisor login to an applied cluster YAML
- [Using the Versioned ClusterClass](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/managing-vsphere-kuberenetes-service-clusters-and-workloads/provisioning-tkg-service-clusters/using-the-cluster-v1beta1-api/using-the-versioned-clusterclass.html): the built-in ClusterClass in `vmware-system-vks-public` and `spec.topology.classNamespace`
- [Sample Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/sample-blueprints-in-vcf-automation-for-all-apps.html): a `Cluster` as a `CCI.Supervisor.Resource` beside a `CCI.Supervisor.Namespace`
- [Create a Namespace Class in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-projects-in-vcfa/create-a-namespace-class.html): CPU and memory limits, VM classes, storage and content libraries per class, and the default small, medium and large
- [Configure PSA for VKr 1.25 and Later](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/managing-vsphere-kuberenetes-service-clusters-and-workloads/managing-security-for-tkg-service-clusters/configure-psa-for-tkr-1-25-and-later.html): `restricted` enforced by default from VKr 1.26, and the namespace label that relaxes it
- [Monitoring VKS Clusters Using VCF Operations](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/managing-vsphere-kuberenetes-service-clusters-and-workloads/operating-tkg-service-clusters/monitoring-vks-clusters-using-vcf-operations.html): VKS clusters in VCF Operations, monitored by default on VCF 9.1

*Next in All Apps in Practice: [the demo apps that live on this
cluster](/series/all-apps-in-practice/).*

---
*Lab environment; opinions my own.*
