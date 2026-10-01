---
title: "Our VPC subnets have no DHCP — and that's fine"
date: 2026-09-16T07:20:00+01:00
lastmod: 2026-10-01
draft: false
tags: [vcf, nsx, vpc, cloud-init, ovf, esxi, bootstrap]
products: ["NSX", "vSphere and vSAN"]
series: ["The VPC Pod Papers"]
seriesPart: 8
tldr:
  - "The nested-ESXi appliance sat at \"waiting for DHCP\", ready to wait politely until the heat death of the universe."
  - "Our VPC subnets have DHCP deactivated by default: NSX allocates each address at the port, and the guest must be told."
  - "Use the VM Service's bootstrap providers: `cloudInit` for Linux, `sysprep` for Windows and `vAppConfig` for appliances like nested ESXi."
tested: "VCF 9.1"
cover:
  image: "/images/post7-hero-nodhcp.svg"
  alt: "Three bootstrap paths into a VPC subnet: cloud-init, sysprep, vAppConfig"
  hidden: false
summary: "The nested ESXi appliance sat at 'waiting for DHCP' for ever. VPC subnets don't hand out addresses: the VM Service does, through cloud-init, sysprep or OVF guestinfo, depending on the guest."
---

The second trap from [part 1](/posts/nested-esxi-nsx-vpc/) deserves its own
short post, because it catches everything, not just ESXi: **our VPC subnets
have DHCP deactivated**. NSX VPC subnets can run a DHCP server or relay
([Add a Subnet to a VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-subnet-for-the-vpc.html)).
But the subnets the Supervisor made for us, and every `Subnet` we created
with the defaults, came up `DHCP_DEACTIVATED` with static IP allocation.

Drop a stock appliance onto one and it will boot, sit at "waiting for DHCP",
and wait politely until the heat death of the universe.

This isn't a gap. It's the model. NSX allocates the address at the *port*
and pins it there with address bindings, and the *guest* has to be told what
it was given. The VM Service does that telling through **bootstrap
providers**. Once you know the three of them, static addressing stops being
a chore and starts being a feature.

## Three providers, three guest types

| Guest | Provider | Carries |
|---|---|---|
| Linux | `cloudInit` | user-data (users, `write_files`, `runcmd`) + network config |
| Windows | `sysprep` | unattend XML / sysprep spec, identity, network |
| Appliances (OVF) | `vAppConfig` | OVF properties (`guestinfo.*`) the appliance reads on boot |

All three are **typed fields on the `VirtualMachine` object**, not bolt-on
customisation specs. The platform already knows the network side: the VM
Service knows which subnet each interface landed on, and what NSX allocated.
So for cloud-init and sysprep, the addressing is injected for you.
Appliances are the exception, because each one has its own idea of which
properties it wants.

## Appliances: vAppConfig

The nested-ESXi appliance reads `guestinfo.*` OVF properties. In the VM
Service spec, that's:

```yaml
bootstrap:
  vAppConfig:
    properties:
      - {key: guestinfo.hostname,  value: {value: "esx01.pod-a.res.lab"}}
      - {key: guestinfo.ipaddress, value: {value: "172.30.0.40"}}
      - {key: guestinfo.netmask,   value: {value: "255.255.255.224"}}
      - {key: guestinfo.gateway,   value: {value: "172.30.0.33"}}
      - {key: guestinfo.vlan,      value: {value: "1610"}}
      - {key: guestinfo.dns,       value: {value: "10.20.52.1"}}
      - {key: guestinfo.ssh,       value: {value: "True"}}
```

The one that trips people up: **the address you give must be the one NSX
allocated to the port**. In a standard subnet, SpoofGuard enforces that, and
it doesn't negotiate. On a trunk subnet, the VLAN subnets have their own
allocations, and you're choosing addresses within them.

Either way, pick from the realized range. And remember that [recreating a VM
reallocates its addresses](/posts/nested-esxi-nsx-vpc/). So the fixed
`.40`/`.41` in a [deterministic pod](/posts/three-datacenters-one-ip-plan/)
is a design choice, not luck.

## Linux: cloud-init

A Secret holding user-data, referenced from the VM:

```yaml
bootstrap:
  cloudInit:
    cloudConfig:
      users: [ ... a local user with a key ... ]
      write_files:
        - path: /var/www/html/index.html
          content: "shared-svc repo01\n"
      runcmd:
        - [systemctl, enable, --now, nginx]
```

Networking arrives through the platform's own network-config, so you don't
write it. Every line of YAML I don't write is a line I can't get wrong.

The `svc-repo01` VM from [the shared-services
post](/posts/shared-services-for-isolated-tenants/) was exactly this:
`write_files` plus `runcmd`, with its web page verified from three pods.

## Windows: sysprep

```yaml
bootstrap:
  sysprep:
    sysprep:
      guiUnattended: {autoLogon: true, autoLogonCount: 1, timeZone: 85}
      identification: {joinWorkgroup: WORKGROUP}
      userData: {fullName: Lab, orgName: Lab, computerName: {name: win01}}
```

Or use `rawSysprep` with an unattend XML in a Secret, if you already have
one. The ISO from [the blueprint post](/posts/nested-esxi-via-vcfa-all-apps/)
can ride along as a declarative `hardware.cdrom`. That's handy for tools and
agents on first boot.

## The ESXi footnote: one gateway, many vmks

Once the appliance is up and you add vMotion and vSAN vmks on their own
subnets, you hit a detail that makes the Host Client *look* wrong:

![Host Client: vmk0/1/2, one service each](/images/ui/u12-hostclient-vmk-adapters.jpg)

ESXi's default TCP/IP stack has **one** default gateway (vmk0's `.33`), and
the UI repeats it on every vmk row with total confidence. Same-subnet vMotion
never uses a gateway, so nothing breaks. But each NSX subnet *does* have its
own gateway, and cross-subnet traffic from vmk1 and vmk2 would take the wrong
exit. Set per-vmk override gateways:

```
esxcli network ip interface ipv4 set -i vmk1 -t static -I 172.30.0.70  -N 255.255.255.224 -g 172.30.0.65
esxcli network ip interface ipv4 set -i vmk2 -t static -I 172.30.0.100 -N 255.255.255.224 -g 172.30.0.97
```

Now the display is truthful and the routing is correct. (The full-realism
alternative is a dedicated `vmotion` netstack for vmk1. I kept the default
stack so the service tags stay visible in the Host Client.)

## Why this matters outside the lab

For the business, "no DHCP" translates into something security and
operations teams both want: **predictable addressing**. Every environment has
a known address plan, firewall rules can be written once, and nothing turns
up on the network with an address nobody expected.

Bootstrap providers deliver the second benefit. Images stay generic and
configuration is injected at deploy time, so there are fewer golden images to
maintain and far less drift between environments.

## Rules learned

- **No DHCP in our VPC subnets**: that's the Supervisor's default, not a VPC
  limit. NSX allocates at the port, and the guest is told through a
  bootstrap provider.
- `cloudInit` (Linux), `sysprep` (Windows) and `vAppConfig` (appliances) are
  typed fields on the VM, not customisation specs.
- Appliance addresses must match the **realized** subnet. Fix the order of
  subnet creation if you want fixed addresses across pods.
- ESXi has **one** default gateway per stack. Set `-g` per vmk, or the Host
  Client lies to you and cross-subnet traffic exits wrong.
- A static IP plan is a feature in a lab: it's what makes screenshots,
  runbooks and pods identical.

## Broadcom documentation

- [Add a Subnet to a VPC](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/virtual-private-cloud-in-nsx/virtual-private-clouds-overview/add-a-subnet-for-the-vpc.html): a subnet's DHCP setting: none for static addresses, a DHCP server, or DHCP relay.
- [Understanding SpoofGuard Segment Profile](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/segments/segment-profiles/understanding-spoofguard-segment-profile.html): the port address bindings SpoofGuard enforces.
- [Provision a VM Using Self-Service](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/vm-service/provision-a-vm-using-the-iaas-services-console-in-vcf-automation.html): the four bootstrap methods, cloud-init, Sysprep, Linuxprep and vAppConfig, and static IP allocation.
- [Deploy VMs with Configurable OVF Properties in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-consumption/latest/vm-service/deploy-vms-with-configurable-ovf-properties-vsphere-iaas-control-plane.html): OVF properties set through the VM Service's vAppConfig transport.
- [Configure the VMkernel Adapter Gateway by Using esxcli Commands](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/vsphere/9-0/vsphere-networking/setting-up-vmkernel-networking/configure-the-vmkernel-adapter-gateway-by-using-esxcli.html): a gateway per VMkernel adapter, set with esxcli.

*Companion to [nested ESXi inside an NSX VPC](/posts/nested-esxi-nsx-vpc/).*

---
*Lab environment; opinions my own.*
