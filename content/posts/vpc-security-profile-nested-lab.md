---
title: "The security profile that would have dropped every nested lab"
date: 2027-01-13
draft: false
tags: [vcf, nsx, vpc, vdefend, distributed-firewall, vcf-automation, nested-esxi]
products: ["NSX", "VCF Automation"]
series: ["The VPC Pod Papers"]
seriesPart: 12
tldr:
  - "VCF Automation gives each new VPC the region's default security profile, and ours was isolation with essential services, not the None profile."
  - "With vDefend enforcing, only the VPC's VM ports may talk to each other, and a nested lab's hosts are not VM ports."
  - "Our hosts never enforced it, so no lab noticed; decide the profile with your security team before the first lab."
tested: "VCF 9.1"
cover:
  image: "/images/post32-hero-secprofile.svg"
  alt: "The region's default VPC security profile allows DNS, DHCP, NTP and ICMP and traffic between VM ports, and drops the rest; a nested lab's hosts, vCenter and VCF Operations sit behind trunk ports, and its binaries server and RDP load balancer sit outside the VPC"
  hidden: false
summary: "No lab of ours ever failed on this. VCF Automation gives every new VPC a default security profile, and under vDefend's firewall ours would drop most of a nested lab's traffic. Check yours, and the one-field fix."
---

No lab of ours ever failed because of this, which is exactly why it's worth
writing down.

Every VPC that VCF Automation created for our nested labs came with a
distributed firewall policy. That policy would drop most of what a lab does:
the jump host talking to the nested hosts, the hosts talking to each other,
the downloads from the binaries server, and very likely RDP too.

The policy came from the region's default security profile. On our platform
that was isolation with essential services, not the None that Broadcom ships
as the default, so check which one yours has.

On our platform the policy did nothing, because our hosts do not enforce the
distributed firewall. Ignorance, for once, was bliss. On a platform with
vDefend and the same default, it would have been the first thing a class met.

The question was simple: what happens to a nested lab where the distributed
firewall does enforce? I answered it by reading the profile, the policy NSX
makes from it and the group that policy uses, not by watching a lab fail.
Everything below about drops is what those rules say would happen;
enforcement itself I could not test.

## Every VPC gets a profile

VCF Automation attaches each VPC to one of five NSX security profiles of its
region, one per strategy: `none`, `vpc-isolation`,
`vpc-isolation-with-essential-services`, `vpc-external-connectivity` and
`vpc-secure-connection`.

An organization administrator can read all of it through the VPC API,
`vpc.nsx.vmware.com/v1alpha1`: `securityprofiles`, `securitystrategies`, and
one `securityprofileattachments` object per VPC. The same administrator can
change a VPC's attachment.

On f06 the organization's own default VPC was on None. The other seven,
`shared-svc` and every student VPC we had created, named the profile flagged
`isDefault: true`. That's `system-security-profile-3--f06`, which the API
describes like this:

> Deny all communication to VPCs except for essential services like ICMP, DNS,
> NTP and DHCP. All workloads within the VPC to be allowed to communicate

Curiously, NSX's own default project flags the None profile as its default.
The NSX project behind our organization flags this one. Two defaults on one
platform, and naturally ours was the other one.

## What the profile turns into

NSX turns the profile into one security policy per VPC, in the Environment
category. The hosts apply it wherever the distributed firewall enforces. A
read-only probe listed the policies with their rules:

```text
== project policy vpc-isolation-with-essential-services-vpc-student04 | category Environment | seq 45000000 | scope ['ANY'] | stateful True
   Allow-Essential-Services         JUMP_TO_APPLICATION  dir IN_OUT src ['ANY'] -> dst ['ANY'] | svc ['/infra/services/DHCP-Client', ... '/infra/services/ICMP-ALL', '/infra/services/DNS', ... '/infra/services/NTP_Time_Server']
   Allow-within-VPC                 JUMP_TO_APPLICATION  dir IN_OUT src ['/orgs/default/projects/.../vpcs/vpc-student04/groups/default'] -> dst ['/orgs/default/projects/.../vpcs/vpc-student04/groups/default'] | svc ['ANY']
   Deny-All                         DROP                 dir IN_OUT src ['ANY'] -> dst ['ANY'] | svc ['ANY'] | scope ['/orgs/default/projects/.../vpcs/vpc-student04/groups/default']
```

`JUMP_TO_APPLICATION` is not an allow. It hands the packet on to the
Application category, where the firewall's own rules decide. So DNS, DHCP,
NTP and ICMP pass from anywhere. Other traffic passes only when both ends are
in the VPC's default group, and everything else touching the group is
dropped. For ordinary VMs, that is a sensible default.

## Who is in the group

Everything hangs on what the group counts as "in the VPC": the addresses NSX
allocated to ports. For `vpc-student03`, with a lab running in it:

```text
members (IPs): ["172.30.0.2", "172.30.0.7", "172.30.0.8", "172.30.0.3", "172.30.0.4", "172.30.0.11", "172.30.0.10", "172.30.0.17", "172.30.0.16", "172.30.0.34", "172.30.0.35", "172.30.0.13", "172.30.0.12", "172.30.0.9", "172.30.0.5", "172.30.0.15", "172.30.0.6", "172.30.0.14"]
```

Those are the sixteen trunk-port addresses of the four nested hosts, plus
`dc01` at .34 and the jump host at .35: the lab's VM ports.

What the lab actually runs on is elsewhere. The hosts' management, vMotion
and vSAN addresses ride as VLANs inside those trunk ports
([the trunk-subnet design](/posts/nested-esxi-nsx-vpc/)). The lab vCenter and
VCF Operations are VMs inside the nested cluster. NSX never allocated those
addresses, so the group has never heard of them.

![The lab VPC's group holds the 16 trunk-port addresses, dc01 and the jump host; the hosts' vmk addresses, the lab vCenter and VCF Operations are behind the trunk ports and not in it; the binaries server and the RDP load balancer are outside the VPC](/images/vpc-security-profile-nested-lab-diagram.svg)

Read the rules against that list:

- The jump host and `dc01` talking to the hosts, the vCenter or VCF
  Operations: one end is outside the group, so Deny-All.
- Host to host: neither end is in it.
- Downloads from the binaries server, which sits in `shared-svc` behind the
  transit gateway ([shared services](/posts/shared-services-for-isolated-tenants/)):
  dropped on the way out, and again on arrival by `shared-svc`'s own copy of
  the policy.
- And very likely RDP, which arrives through the VPC's load balancer, whose
  address is not in the group either.

Ping and DNS would still pass the first rule. So under a default rule that
allows, a lab would answer ping and resolve every name while failing to copy
a file. Chatty, cheerful and no use at all: the kind of fault that sends
people to the wrong layer.

## Why our labs never met it

NSX's own firewall setting is on:

```text
DFW settings: {'idfw_enabled': False, ..., 'enable_firewall': True, 'disable_auto_drafts': False, ...}
```

The hosts disagree. `nsxcli -c 'get firewall status'` on an f06 host:

```text
--- nsx dfw status: Firewall Status
----------------------------------------------------------------------

       firewall: disabled
  headless mode: false
 failure policy: open
```

Our NSX runs on its evaluation licence, without vDefend: the policies exist
and nothing enforces them. Every lab we built ran with the policy attached
and inert, and no test of ours could have said otherwise.

## One field

The way out is the profile with the `none` strategy. NSX makes no policy per
VPC from it, so a lab VPC meets the distributed firewall's default rule like
any other workload. Moving a VPC is a JSON merge-patch of one field on its
attachment.

`create_vpcs.py` finds the profile by strategy rather than by name. The name
carries the region (`default--f06` here), and the same profile is `default`
in NSX and `system-security-profile-1` in the UI:

```python
prof = [i["metadata"]["name"] for i in (d.get("items", []) if isinstance(d, dict) else [])
        if i["spec"].get("regionName") == region and (i["spec"].get("eastWestFirewall") or {}).get("securityStrategies") == [want]]
...
code, r = call("PATCH", "/securityprofileattachments/" + v, {"spec": {"securityProfileName": prof[0]}}, "application/merge-patch+json")
...
# NSX names a strategy's policy <strategy>-<vpc>: wait until only the wanted one (none for 'none') is there
expect = set() if want == "none" else {"%s-%s" % (want, v)}
```

I tried it on one free VPC first, with a script that patches the attachment
and polls the VPC's firewall policies every ten seconds:

```text
before: 200 {'regionName': 'f06', 'vpcName': 'vpc-student05', 'securityProfileName': 'system-security-profile-3--f06'}
PATCH: 200
 10 s attachment default--f06 | VPC firewall policies: none | status {}
```

Gone at the first poll. Then came the check that matters for labs: a
namespace-only draft deployment into the VPC, checked and deleted:

```text
vpc-student05      ok - a namespace was created in it
--
1 VPC(s) checked, 0 failed
```

Switching back brought the policy back just as fast:

```text
before: 200 {'regionName': 'f06', 'vpcName': 'vpc-student05', 'securityProfileName': 'default--f06'}
PATCH: 200
 10 s attachment system-security-profile-3--f06 | VPC firewall policies: ['vpc-isolation-with-essential-services-vpc-student05'] | status {}
```

Then I made the None profile the region's default, in the organization
portal. The path is **Manage & Govern** > **Firewall** > **Security Profiles**,
then the region, then the **⋮** menu on the row whose **Security Strategy**
is `none`. That covers every VPC created afterwards. (Broadcom's
[NSX-side page](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/vdefend/vdefend-firewall/9-1/secure-vpc-projects/implementing-distributed-firewall-security-strategies/configure-dfw-security-strategies.html)
says None can't be made the default there, in NSX Manager; the organization
portal took it.)

Existing VPCs can keep their old profile, so I moved those as well. The
**VPC Applied To** column counts the VPCs on each profile. On f06 the None
row ended at 8: the six student VPCs, `shared-svc` and the organization's
default VPC. Afterwards the tool had nothing left to do, and said so, which is
the best news a tool can give:

```text
shared-svc      security profile default--f06 (none): already
vpc-student01   security profile default--f06 (none): already
...
vpc-student06   security profile default--f06 (none): already
```

## A decision, not a default

In the site file ([one file per platform](/posts/lab-catalog-property-groups/))
this is one key, `install.vpcSecurityStrategy`. `create_vpcs.py` puts each
new VPC on that profile, and `--security-only` moves existing ones such as
`shared-svc`. Ours says `none`.

The template for a new site ships the line commented out, on purpose, so
nothing weakens a VPC unless somebody decided it should. Until somebody does,
the site check says so on every run, with all the persistence of a smoke
alarm with a low battery:

```text
Security    VPC security profile: the region's default (decide install.vpcSecurityStrategy if the distributed firewall enforces)
```

The other route keeps the default profile and adds allow rules above each
VPC's policy. They would allow all traffic within the lab's own ranges, HTTP
and NFS from the labs to the binaries server, and RDP to the jump hosts. We
have not tested it. Either way the labs stay apart: a lab's subnets are private to its
VPC, and no other VPC routes to them.

## Why this matters outside the lab

A default that is safe for virtual machines is wrong for nested
infrastructure, and the platform cannot tell the two apart. VCF Automation
sees a VPC. It does not know that most of what runs inside is ESXi hosts, a
vCenter and appliances behind trunk ports. The same gap opens for anything
that brings its own addresses into a VPC: nested hypervisors, appliances with
secondary interfaces, routers in VMs.

The lesson is about order. Decide the VPC security profile with the security
team before the first lab, with the policy and the group in front of them,
not after a class has found the drop. And if the platform where the design
was proven does not enforce the distributed firewall, say so in the handover.

## Rules learned

- VCF Automation attaches every new VPC to its region's default security
  profile. On our VCF 9.1 platform that was isolation with essential services;
  Broadcom ships None as the default. Check which one yours has, and
  `securityprofileattachments`, before trusting a VPC's behaviour.
- That profile passes DNS, DHCP, NTP and ICMP from anywhere and other traffic
  only between members of the VPC's group, and drops the rest.
- The group is the addresses NSX allocated to ports. Nested hosts' vmk
  addresses, and VMs inside a nested cluster, are never in it.
- A policy that exists is not a policy that enforces. Ask the hosts
  (`nsxcli -c 'get firewall status'`), not only NSX's settings.
- Move a VPC with a merge-patch of `spec.securityProfileName` on its
  attachment, and find the profile by strategy: its name differs per region,
  and between the API, NSX and the UI.
- Make None the region's default before the VPCs exist, move the older ones,
  and record the choice in the site file rather than defaulting it in a tool.

## Broadcom documentation

- [VPC Security Profiles](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/vdefend/vdefend-firewall/9-1/secure-vpc-projects/implementing-distributed-firewall-security-strategies/vpc-security-key-concepts.html): the five profiles each project gets, one profile per VPC, and the default.
- [Supported VPC Security Strategies](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/vdefend/vdefend-firewall/9-1/secure-vpc-projects/implementing-distributed-firewall-security-strategies/supported-vpc-security-strategies-and-transit-gateway-topologies.html): what each strategy allows, isolation with essential services included.
- [Rule Application and Precedence Model](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/vdefend/vdefend-firewall/9-1/secure-vpc-projects/implementing-distributed-firewall-security-strategies/rule-application-and-precedence-model.html): the Environment category, and the Jump to Application action.
- [Define Default Security Posture for VPCs](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/vdefend/vdefend-firewall/9-1/vcf-automation-integration-with-vdefend-firewall/defining-the-security-posture-for-virtual-private-clouds/define-default-security-posture-for-vpcs.html): setting a region's default profile in VCF Automation.
- [Apply a Security Profile to VPCs](https://techdocs.broadcom.com/us/en/vmware-security-load-balancing/vdefend/vdefend-firewall/9-1/vcf-automation-integration-with-vdefend-firewall/defining-the-security-posture-for-virtual-private-clouds/apply-a-security-profile-to-existing-vpcs.html): moving existing VPCs to another profile in VCF Automation.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
