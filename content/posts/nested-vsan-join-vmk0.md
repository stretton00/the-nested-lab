---
title: "The tags said vmk2: nested hosts that joined vSAN on the management network"
date: 2026-12-23
draft: false
tags: [vcf, vsan, nested-esxi, powercli, troubleshooting, homelab]
products: ["vSphere and vSAN"]
series: ["The Lab Factory"]
seriesPart: 6
cover:
  image: "/images/post27-hero-vsan-join.svg"
  alt: "The esxcli tags say vmk2, the host's vSAN view still says vmk0, and vCenter joins the host from the view; setting the vSAN network with UpdateVsan before the join fixes it"
  hidden: false
summary: "The build tagged vmk2 for vSAN on every nested host and checked it again seconds before each join. Three of four hosts still joined vSAN on vmk0. vCenter does not read the tags when a host joins; it reads the host's vSAN view, and that view was nearly three hours old."
---

Our lab builds finish with a vCenter, four nested ESXi hosts and a vSAN ESA
datastore. The build was green. The check I ran afterwards was not:

```text
esx01.acme.lab Connected vmk0[Management] vmk1[VMotion] vmk2[VSAN] vSAN members 4
esx02.acme.lab Connected vmk0[VSAN+Management] vmk1[VMotion] vmk2[] vSAN members 4
esx03.acme.lab Connected vmk0[VSAN+Management] vmk1[VMotion] vmk2[] vSAN members 4
esx04.acme.lab Connected vmk0[VSAN+Management] vmk1[VMotion] vmk2[] vSAN members 4
```

vSAN worked: four members and a 399 GB datastore. But three hosts carried
vSAN traffic on the management interface, and esx01 on the vSAN VLAN, so every
conversation with esx01 went through the VPC router. The lab manual says
vSAN runs on vmk2, VLAN 1612. The build script tags vmk2 for vSAN on all four
hosts in its second step, long before any host meets vCenter.

## The obvious fix, and why it was wrong

This had happened once before, on an earlier lab, to two hosts. I did the
obvious thing on the running cluster: added the vSAN tag to vmk2 and removed it
from vmk0. vSAN partitioned at once. The other members' unicast agent lists
still held the old addresses. vCenter normally repairs those lists, but this
vCenter lives on that vSAN datastore, and it stopped answering. vmkping between
the vmk2 addresses worked for every pair, so the network was fine; the
membership was not. Putting the tags back recovered the lab, and I did not try
that again.

So the fix had to come before the join. My first theory was a race: the
appliance's own first-boot setup finishing after the build had tagged the
hosts. The next build therefore checked every host again just before it moved
into the cluster, through vCenter, and corrected the tags if needed.

## A check that found nothing

On the next test the check ran on esx02 seconds before the join; its hostd log
shows the four tag reads at 11:22:11-12. It found vmk2 tagged and vmk0 clean,
and logged nothing. After the build, esx02, esx03 and esx04 were on vmk0 again,
exactly as before.

So the tags were right at the moment of the join, and something in the join put
vSAN back on vmk0. Two logs show what. The host agent on esx02 (vpxa) records
every change vCenter sees, trimmed here:

```text
11:22:15.855Z vpxaInvtHost ... HostChanged|configManager.vsanSystem:config.networkInfo.port
11:22:28.201Z vpxaInvtHost ... HostChanged|configManager.vsanSystem:config.enabled
11:22:28.201Z vpxaInvtHost ... HostChanged|configManager.vsanSystem:config.networkInfo.port
```

And vCenter's vSAN service, in
`/var/log/vmware/vsan-health/vmware-vsan-health-service.log` on the lab's
VCSA, logs the address it will give the other members for esx02:

```text
11:22:14.338Z VsanMgmtAdapters::GetUnicastConfig  Add IPv4 unicast entry (172.30.0.41, vmk0)
11:22:26.082Z VsanMgmtAdapters::GetUnicastConfig  Add IPv4 unicast entry (172.30.0.101, vmk2)
11:22:32.987Z VsanMgmtAdapters::GetUnicastConfig  Add IPv4 unicast entry (172.30.0.41, vmk0)
```

172.30.0.41 is esx02's management address and 172.30.0.101 its vSAN address.
vCenter saw vmk0 before the join and vmk2 a few seconds later. vmk0 was back
after vSAN was switched on at 11:22:28, in the same update that set
`config.enabled`. esx03 and esx04 show the same flip, half a minute and a
minute later.

Put together: when a host joins, vCenter takes its vSAN network from the host's
vSAN view (`HostVsanSystem.config.networkInfo`), not from the vmknic tags. On
esx02 hostd still held vmk0 in that view while the tags said vmk2, and only
refreshed it at 11:22:15, after vCenter had already read it. The settings
applied at 11:22:28 carried the stale vmk0 with them.

## Where the vmk0 came from

The last question was why the view said vmk0 at all. A freshly deployed lab
host, read before the build touched it, answers it:

```text
vmknics: vmk0
vsan network list: vmk0
vmk0 tags: VSAN+Management+VMotion
vsanSystem view: vmk0
```

The Nested ESXi appliance boots with vSAN and vMotion on vmk0. The build's
esxcli tag changes move the tags, but hostd's view keeps the appliance's vmk0,
on esx02 for almost three hours, from the tagging to the join. esx01 never
showed the problem: its vSAN is switched on locally in the build's bootstrap
step, and that evidently refreshes the view.

## The fix: set it the way vCenter reads it

The check before the join now sets the vSAN network through the [vSAN API](https://techdocs.broadcom.com/us/en/vmware-cis/vsan/vsan-sdk/8-0/setting-up-a-vsan-cluster/configuring-vmkernel-netowkring-for-vsan.html)
instead of trusting the tags. `UpdateVsan` writes the host's configuration and
its view in one call:

```powershell
$vs = Get-View $vmh.ExtensionData.ConfigManager.VsanSystem
$ports = @($vs.Config.NetworkInfo.Port | ForEach-Object { $_.Device })
if (($ports -join '+') -ne 'vmk2') {
    $spec = New-Object VMware.Vim.VsanHostConfigInfo
    $spec.NetworkInfo = New-Object VMware.Vim.VsanHostConfigInfoNetworkInfo
    $port = New-Object VMware.Vim.VsanHostConfigInfoNetworkInfoPortConfig
    $port.Device = 'vmk2'
    $spec.NetworkInfo.Port = @($port)
    $task = Get-View ($vs.UpdateVsan_Task($spec))
    for ($i = 0; $i -lt 60 -and "$($task.Info.State)" -notin 'success', 'error'; $i++) { Start-Sleep 2; $task.UpdateViewData('Info') }
    if ("$($task.Info.State)" -ne 'success') { throw "setting the vSAN network: $($task.Info.State) $($task.Info.Error.LocalizedMessage)" }
}
```

It runs while the host sits in the datacenter, after `Add-VMHost` and before
`Move-VMHost` puts it into the vSAN cluster. The hosts join in those two steps
for a second reason: a direct `Connect-VIServer` to a host hangs while a
vCenter connection is open in the same session, so the check has to go through
vCenter.

## Proof

I tried it on the broken lab before it was deleted. esx04 went into
maintenance mode without data migration, out of the cluster, through the new
check, and back in:

```text
12:44:11 esx04 before: vSAN view=vmk0, state Connected, cluster Cluster-Student02
12:44:28 esx04 in maintenance mode (no data migration)
12:44:55 esx04 out of the cluster: vSAN view=vmk0, vSAN enabled=True
12:46:12   esx04.acme.lab: corrected before joining vSAN - vSAN network vmk0 -> vmk2
12:46:13 esx04 after the check: vSAN view=vmk2
12:46:25 esx04 back in Cluster-Student02, state Connected
12:47:13   vSAN network per host: esx01=vmk2 esx02=vmk0 esx03=vmk0 esx04=vmk2
```

esx04 rejoined on vmk2 with all four members still present. esx02 and esx03
stayed where they were, and that was deliberate: a live cluster is exactly
where not to move them.

The next full build, a Phase 6 lab requested from the released catalog item,
logged this at the joins:

```text
14:38:02    esx04.acme.lab: corrected before joining vSAN - vSAN network vmk0 -> vmk2
14:39:54    vSAN network per host: esx01=vmk2 esx02=vmk2 esx03=vmk2 esx04=vmk2
```

Only esx04 needed the correction this time; esx02 and esx03 already showed
vmk2 when the check ran. That matches the earlier randomness: hostd sometimes
refreshes its view during the join and sometimes does not. The check from the
top of this post, run after the build:

```text
esx01.acme.lab Connected vmk0[Management] vmk1[VMotion] vmk2[VSAN] vSAN members 4
esx02.acme.lab Connected vmk0[Management] vmk1[VMotion] vmk2[VSAN] vSAN members 4
esx03.acme.lab Connected vmk0[Management] vmk1[VMotion] vmk2[VSAN] vSAN members 4
esx04.acme.lab Connected vmk0[Management] vmk1[VMotion] vmk2[VSAN] vSAN members 4
```

## Why this matters outside the lab

Automation usually checks what it can see, and this check looked in the wrong
place. The tags said vmk2, so every script and every person reading them would
have called the host correct, while vCenter was about to act on a different
record entirely. Any tool that changes a running host with esxcli and then
hands the host to vCenter can hit the same gap.

It also matters because the failure is quiet. vSAN worked with its traffic on
the wrong network: the build finished green and vSAN reported four members.
The lab would have taught students a design that is not the one in their
manual, and in a production cluster the same drift would put storage traffic
on the management network, where it competes with everything else.

## Rules learned

- When a host joins a vSAN cluster, vCenter takes its vSAN network from the
  host's vSAN view (`HostVsanSystem.config.networkInfo`), not from the vmknic
  tags. Check the view, not just `esxcli network ip interface tag get`.
- esxcli tag changes do not refresh that view. Set vSAN networking with
  `UpdateVsan`, or through vCenter, before the host joins.
- The Nested ESXi appliance boots with vSAN and vMotion on vmk0. Anything that
  builds on it, a script or a student, has to move both.
- Never move a vSAN vmknic on a live cluster whose vCenter lives on that vSAN.
  The other members keep the old address in their unicast agent lists, and the
  one service that would fix them is the one that just lost its storage.
- When a fix "does nothing", check whether it tested the thing the platform
  actually reads.

## Broadcom documentation

- [Set Up a VMkernel Network for vSAN](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsan-deployment-administration-and-monitoring/vsan-planning-and-deployment/creating-a-virtual-san-cluster/enabling-virtual-san/set-up-networking-for-virtual-san.html): a VMkernel adapter with the vSAN service on each host
- [Using Unicast in vSAN Network](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vsan-deployment-administration-and-monitoring/vsan-network-design/understanding-vsan-networking/vsan-network-characteristics/using-unicast-in-vsan-network.html): vCenter as the source of the membership list every host receives
- [Configuring VMkernel Networking for vSAN](https://techdocs.broadcom.com/us/en/vmware-cis/vsan/vsan-sdk/8-0/setting-up-a-vsan-cluster/configuring-vmkernel-netowkring-for-vsan.html): setting the vSAN vmknic with `UpdateVsan_Task` (vSAN SDK 8.0 guide)
- [vSAN cluster partition due to invalid unicast agent list](https://knowledge.broadcom.com/external/article/317830/vsan-cluster-partition-due-to-invalid-un.html): partitions when vCenter does not update the unicast agent lists after a vSAN vmknic change
- [Non-Disruptively Change the VLAN/IP for vSAN VMk in a Production Environment](https://knowledge.broadcom.com/external/article/326852/nondisruptively-change-the-vlanip-for-vs.html): moving vSAN to a new vmknic on a running cluster, one host at a time

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
