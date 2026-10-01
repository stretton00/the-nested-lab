---
title: "The subnets that outlive the lab: why a quick re-request never boots"
date: 2027-01-06
draft: false
tags: [vcf, nsx, vpc, vm-service, ipam, training-labs, troubleshooting]
products: ["NSX", "VCF Automation"]
series: ["The VPC Pod Papers"]
seriesPart: 11
cover:
  image: "/images/post31-hero-subnets.svg"
  alt: "A deleted lab's subnet still holds the first block of the VPC, so each new subnet moves up one /27 and the domain controller's fixed address 172.30.0.34 no longer fits sn-mgmt"
  hidden: false
summary: "I deleted a test lab, got 'clean', and requested the next one into the same VPC eleven seconds later. It never booted: NSX still held the old lab's subnets. Why fixed addresses need a clean slate, and tooling that waits for NSX instead of a timer."
---

Our delete tool said the old lab was gone:

```text
23:26:06 deployment=DELETE_INPROGRESS namespaces=0 volumes=0
23:26:49 deployment=gone namespaces=0 volumes=0
clean
```

Eleven seconds later I requested the next Phase 6 lab into the same VPC.
Forty minutes after that, the four nested ESXi hosts were running, and the
two Windows VMs, the domain controller `dc01` and the jump host, had never
powered on:

```text
NAME              POWER-STATE   CLASS                IMAGE                   PRIMARY-IP4   AGE
dc01-student03                  best-effort-small    vmi-0e77cab86c7da5872                 39m
esx01-student03   PoweredOn     nested-esx-medium    vmi-06c9d169cecd2eb9d   172.30.0.40   39m
esx02-student03   PoweredOn     nested-esx-medium    vmi-06c9d169cecd2eb9d   172.30.0.41   39m
esx03-student03   PoweredOn     nested-esx-medium    vmi-06c9d169cecd2eb9d   172.30.0.42   39m
esx04-student03   PoweredOn     nested-esx-medium    vmi-06c9d169cecd2eb9d   172.30.0.43   39m
jump-student03                  best-effort-medium   vmi-0e77cab86c7da5872                 39m
```

VCF Automation still showed the deployment in progress, with no reason. The
reason was on each VM, about 300 characters into its network condition:

```text
VirtualMachineNetworkReady=False NotReady: network interface "eth0" error: network interface is not ready: SubnetPortNotReady - error occurred while processing the SubnetPort CR. Error: /orgs/default/projects/.../vpcs/vpc-student03/subnets/sn-mgmt_pzsh3/ports/dc01-student03-sn-mgmt-eth0_pzsh3 realized with errors: [IP Address 172.30.0.34 does not belong to any of the existing ranges in the pool with id IpPool/...]
```

The jump host had the same error for 172.30.0.35.

## The plan every lab shares

Every lab in a student's VPC uses the same addresses, the pattern from
[three datacenters, one IP plan](/posts/three-datacenters-one-ip-plan/). The
blueprint creates four subnets in a fixed order, and in a fresh VPC NSX
hands out /27 blocks from `172.30.0.0/16` in that order:

| Subnet | Block | What lives there |
|---|---|---|
| sn-trunk | 172.30.0.0/27 | the nested hosts' vNICs |
| sn-mgmt | 172.30.0.32/27 | dc01 .34, jump host .35, host vmk0 .40-.43 (VLAN 1610) |
| sn-vmotion | 172.30.0.64/27 | vmk1 .70-.73 (VLAN 1611) |
| sn-vsan | 172.30.0.96/27 | vmk2 .100-.103 (VLAN 1612) |

`dc01` and the jump host ask VM Operator for their fixed addresses
(`addresses` and `gateway4` in the VM spec), and NSX creates each port with
that address bound to it. That is why the domain controller is .34 in every
lab, and why one set of class notes fits them all.

## What NSX actually did

The new lab's subnets as NSX had them (the fourth column is the creation
time in milliseconds):

```text
sn-mgmt_pzsh3 sn-mgmt_pzsh3 ['172.30.0.64/27'] 1790720923025 False
sn-trunk_pzsh3 sn-trunk_pzsh3 ['172.30.0.32/27'] 1790720920699 False
sn-vmotion_pzsh3 sn-vmotion_pzsh3 ['172.30.0.96/27'] 1790720928832 False
sn-vsan_pzsh3 sn-vsan_pzsh3 ['172.30.0.128/27'] 1790720933557 False
```

Every subnet had moved up one block, so the first block was still taken, by
the lab I had just deleted. VCF Automation had removed the deployment, the
Supervisor had no namespace and no volumes left, and NSX still held at least
one of its subnets. The new sn-mgmt came out as .64/27, where .34 and .35 do
not exist, so NSX refused both Windows VMs' ports and they waited for ever.
The hosts powered on because their trunk ports take whatever address NSX
hands out; their own addresses are set inside the guest. They were running
on a plan that no longer matched their subnets, so the lab was dead either
way.

![Fresh VPC: sn-mgmt at .32/27 holds dc01's .34. Re-request while a deleted lab's subnet holds .0/27: every subnet moves up a block and .34 no longer fits](/images/vpc-subnets-outlive-the-lab-diagram.svg)

Two live labs in one VPC break each other the same way, because the second
lab's subnets take the next free blocks. The first time I met this, a failed
attempt's namespace was still in the VPC and the retry's subnets came out
three blocks up. The rule has been one lab per VPC at a time ever since. The
new lesson was that a deleted lab still counts for a while.

## Wait for the layer that holds the resource

The delete tool used to watch VCF Automation and the Supervisor. Now it also
asks NSX for the VPC's subnets, and waits up to ten minutes for there to be
none:

```python
def _vpc_subnets(vpc):
    ...
        return [x["id"] for x in nsx("/orgs/default/projects/%s/vpcs/%s/subnets?page_size=100" % (pid, vpc)).get("results", [])]
...
if st in ("gone", "DELETE_SUCCESSFUL") and ns[:2] == ["0", "0"]:
    left = vpc_subnets(vpcname) if vpcname else None
    t1 = time.time()
    while left and time.time() - t1 < 600:
        print(time.strftime("%H:%M:%S"), "waiting for NSX to release %s's subnets: %s" % (vpcname, ", ".join(left)), flush=True)
        time.sleep(20)
        left = vpc_subnets(vpcname)
```

Its first job was deleting the stuck lab:

```text
00:13:48 deployment=DELETE_INPROGRESS namespaces=0 volumes=0
00:14:33 deployment=gone namespaces=0 volumes=0
clean - vpc-student03 has no subnets left, a new lab can use it
```

The retry, requested after that line, was ready three and a half hours later,
and went on to star in [the VCF Operations post](/posts/vcf-ops-ad-groups-by-dn/).
A later delete caught the lag in the act, one second after the namespace and
volumes had gone:

```text
16:08:54 deployment=gone namespaces=0 volumes=0
16:08:55 waiting for NSX to release vpc-student04's subnets: sn-mgmt_gnk7l
clean - vpc-student04 has no subnets left, a new lab can use it
```

The main endings, one line each, and what each means:

| `lab_delete.py` ends with | Then |
|---|---|
| `clean - vpc-student01 has no subnets left, a new lab can use it` | Request the next lab |
| `clean - wait 5 minutes before a new lab in vpc-student01 (NSX was not asked)` | Wait five minutes, then request |
| `not clean after <n> minutes: ...` | The delete is still running: run the tool again |
| `NSX still holds vpc-student01's subnets after 10 minutes (...): ...` | Do not request until NSX shows none |
| `the delete FAILED - see the deployment in VCF Automation` | Read the reason there and delete again |

The five minutes are a margin, not a measurement, and apply only when NSX
cannot be asked. That happened once, a timeout (`NSX not asked about
vpc-student03's subnets (TimeoutError)`), so the tool now asks three times
before it falls back.

## Say it where people look

The error that explained all this was not in VCF Automation, and not in VM
Operator's log. It was in each VM's `VirtualMachineNetworkReady` condition,
a long way into the message. So the lab watcher, `phase_watch.py`, now reads
the failing conditions of every VM that is not on yet, cuts the message down
to the part that matters, and adds a line saying what to do:

```python
HINTS = [(re.compile(r"IP Address [\d.]+ does not belong to any of the existing ranges"),
          "the VPC still held an earlier lab's subnets when this lab was requested: delete this lab with lab_delete.py, "
          "wait for 'clean - ... has no subnets left', then request it again")]
```

It prints `VM condition:` with the VM, the condition and the matched text,
then the hint on a line of its own after `>>>`.

## Before a class: a throwaway namespace per VPC

Would namespaces waiting in the VPCs save time? No: creating the namespace
took about 5 seconds of a 2 min 25 s lab request. What pre-creating would
really buy is failing early, and a throwaway namespace buys that too.
`vpc_check.py` makes a namespace-only draft deployment in each free VPC
through VCF Automation, with no VMs and no subnets, checks it and deletes
it. A VPC that holds a lab is skipped, because a namespace beside a live lab
is exactly what the labs must avoid:

```text
vpc-student01      ok - a namespace was created in it
vpc-student02      ok - a namespace was created in it
vpc-student04      ok - a namespace was created in it
vpc-student05      ok - a namespace was created in it
vpc-student06      ok - a namespace was created in it
--
vpc-student03      skipped - a lab's namespace is in it now
6 VPC(s) checked, 0 failed
```

## Why this matters outside the lab

Fixed addresses are what make identical environments possible: one runbook,
true screenshots, firewall rules written once. But the platform promises
deterministic addressing only to a clean slate. A tear-down that finishes in
the background turns a harmless delay into an environment that never boots,
and the failure surfaces somewhere else, forty minutes later, in a message
nobody reads.

The same race exists wherever an environment is torn down and recreated with
the same identity: blue/green deployments, short-lived test environments,
pipelines that reuse names, addresses or certificates. The fix is the same
everywhere. Wait for the signal from the layer that actually holds the
resource, not for a timer, and not for the layer above it. Where you cannot
wait, make the failure say what to do.

## Rules learned

- A VPC realizes subnets in the plan's order only when it is empty. Any
  subnet left in it, from a live lab or a deleted one, moves every new
  subnet up a block.
- NSX releases a deleted lab's subnets after the deployment, the namespace
  and the volumes have gone. "Deployment deleted" is not "VPC free".
- Wait on NSX: no subnets left in the VPC. A timer is the fallback for when
  NSX cannot be asked, not the plan.
- The symptom is in the VM's `VirtualMachineNetworkReady` condition: "IP
  Address ... does not belong to any of the existing ranges". Watchers should
  read VM conditions and say what to do.
- Hosts on a trunk subnet still boot; VMs with fixed addresses do not. A
  half-started lab in a reused VPC is a shifted lab until proven otherwise.
- One lab per VPC at a time, and "at a time" includes the minutes after a
  delete.
- Smoke-test each free VPC with a throwaway namespace before a class, never
  beside a live lab.

## Broadcom documentation

- [Add a Subnet to a VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-subnet-for-the-vpc.html): subnet CIDRs auto-allocated from the VPC's IP blocks, by size.
- [Create a VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/create-a-vpc.html): the private CIDRs a VPC's subnets come from.
- [Provision a VM Using Self-Service](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/vm-service/provision-a-vm-using-the-iaas-services-console-in-vcf-automation.html): a subnet's static IP allocation, and entering an address to override it.
- [Remove a vSphere Namespace from Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsphere-supervisor-installation-and-configuration/configuring-and-managing-vsphere-namespaces/services-and-workloads-remove-a-vsphere-namespace.html): removing a namespace, which can take a while to complete.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
