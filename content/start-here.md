---
title: "Start here"
description: "Reading paths through The Nested Lab: where to begin for VCF Automation All Apps, nested labs in NSX VPCs, catalog automation, observability on VCF and dark sites."
summary: "Reading paths through The Nested Lab, by what you are trying to do."
ShowReadingTime: false
ShowToc: false
ShowBreadCrumbs: false
ShowPostNavLinks: false
ShowShareButtons: false
hidemeta: true
---

Everything here was written from a nested VCF 9 lab while the work was being done: real commands, real output, the failure first and then the fix. Most posts belong to a series, but you rarely need a whole series to get going. Pick the path closest to what you are doing. Each one is in reading order, and new posts join their path on the day they are published.

{{< path id="all-apps" title="New to VCF Automation All Apps" intro="You run VCF 9 and want to know what the supervisor-native side of VCF Automation is, and how a catalog item is put together." posts="vm-apps-vs-all-apps whats-a-vpc-with-pacman vks-kubectl-vs-vcfa-all-apps demo-apps-via-vcfa cci-blueprint-gotchas vcfa-blueprint-resource-reference vcfa-custom-request-forms one-item-students-and-trainers" >}}

{{< path id="nested-labs" title="Nested VCF labs in NSX VPCs" intro="You want isolated nested ESXi and VCF labs on a VCF platform, one per person or per class, and the networking that makes them work." posts="nested-esxi-nsx-vpc the-lb-that-must-exist-first three-datacenters-one-ip-plan shared-services-for-isolated-tenants nested-esxi-via-vcfa-all-apps dual-nic-nested-hosts vpc-subnets-have-no-dhcp nested-labs-as-code nested-lab-use-cases lab-network-no-router six-phases-one-catalog inside-the-lab-blueprint adapting-the-lab-catalog nested-nsx-offload-stalls nested-vsan-join-vmk0 vpc-subnets-outlive-the-lab vpc-security-profile-nested-lab" >}}

{{< path id="automation" title="Catalog items and automation pipelines" intro="You turn scripts and runbooks into catalog items, from a whole VCF instance to a Windows build, and want them to fail safely." posts="one-catalog-item-one-vcf-instance validateonly-everywhere porting-a-powershell-deploy-script driving-the-vcf-installer-api-from-vro lab-catalog-property-groups validate-blueprints-without-saving windows-2025-aria-part-1 windows-2025-aria-part-2 windows-2025-aria-part-3" >}}

{{< path id="observability" title="Observability on VCF" intro="You want logs and metrics from VKS clusters, Windows servers and things without an adapter in VCF Operations and Operations for Logs." posts="fluent-bit-two-ways telegraf-windows-2025 telegraf-vks-management-proxy vllm-metrics-vcf-ops-part-1 vllm-metrics-vcf-ops-part-2 vcf-ops-ad-groups-by-dn" >}}

{{< path id="dark-sites" title="Dark sites and air gaps" intro="Your platform has no internet: images, packages and operators have to arrive another way." posts="imgpkg-tar-vs-oci-archive vks-gpu-operator-dark-site lab-catalog-handover" >}}

## Other ways in

Browse [by VCF product](/products/) or [by series](/series/), see every post by month in the [archive](/archives/), or [search](/search/). Each product and series page has its own RSS feed, beside its title; [this one](/index.xml) carries every post.
