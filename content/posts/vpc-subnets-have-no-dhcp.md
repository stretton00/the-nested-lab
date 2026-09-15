---
title: "VPC subnets have no DHCP — and that's fine"
date: 2026-12-08
draft: false
tags: [vcf, nsx, vpc, cloud-init, ovf, esxi, bootstrap]
series: ["The VPC Pod Papers"]
cover:
  image: "/images/post7-hero-nodhcp.svg"
  alt: "Three bootstrap paths into a VPC subnet: cloud-init, sysprep, vAppConfig"
  hidden: false
summary: "The nested-ESXi appliance sat at 'waiting for DHCP' forever. VPC subnets don't hand out addresses — the VM Service does, through bootstrap providers. cloud-init for Linux, sysprep for Windows, OVF guestinfo for appliances, and the per-vmk gateway detail that makes the Host Client tell the truth."
---

The second trap from [part 1](/posts/nested-esxi-nsx-vpc/) deserves its
own short post, because it catches everything, not just ESXi: **a VPC
subnet has DHCP deactivated.** Drop a stock appliance onto one and it will
boot, sit at "waiting for DHCP", and wait politely until the heat death of
the universe.

This isn't a gap. It's the model: NSX allocates the address at the *port*
and pins it there with address bindings; the *guest* has to be told what
it was given. The VM Service does that telling through **bootstrap
providers**, and once you know the three of them, static addressing stops
being a chore and starts being a feature.

## Three providers, three guest types

| Guest | Provider | Carries |
|---|---|---|
| Linux | `cloudInit` | user-data (users, `write_files`, `runcmd`) + network config |
| Windows | `sysprep` | unattend XML / sysprep spec, identity, network |
| Appliances (OVF) | `vAppConfig` | OVF properties (`guestinfo.*`) the appliance reads on boot |

All three are **typed fields on the `VirtualMachine` object**, not bolt-on
customisation specs. The network side is already known to the platform —
the VM Service knows which subnet each interface landed on and what NSX
allocated — so for cloud-init and sysprep the addressing is injected for
you. Appliances are the exception, because each one has its own idea of
which properties it wants.

## Appliances: vAppConfig

The nested-ESXi appliance reads `guestinfo.*` OVF properties. In the VM
Service spec that's:

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

The one that trips people: **the address you give must be the one NSX
allocated to the port.** In a standard subnet that's enforced by
SpoofGuard; on a trunk subnet the VLAN subnets have their own allocations
and you're choosing addresses within them. Either way, pick from the
realized range — and remember [recreating a VM reallocates its
addresses](/posts/nested-esxi-nsx-vpc/), so the fixed `.40`/`.41` in a
[deterministic pod](/posts/three-datacenters-one-ip-plan/) is a design
choice, not luck.

## Linux: cloud-init

A Secret holding user-data, referenced from the VM:

```yaml
bootstrap:
  cloudInit:
    cloudConfig:
      users:
        - name: lab
          hashed_passwd: "$6$..."
          sudo: ALL=(ALL) NOPASSWD:ALL
          ssh_authorized_keys: ["ssh-ed25519 AAAA..."]
      write_files:
        - path: /var/www/html/index.html
          content: "shared-svc repo01\n"
      runcmd:
        - [systemctl, enable, --now, nginx]
```

Networking arrives via the platform's own network-config; you don't
write it. The `svc-repo01` VM from [the shared-services
post](/posts/shared-services-for-isolated-tenants/) was exactly this —
`write_files` + `runcmd`, web page verified from three pods.

## Windows: sysprep

```yaml
bootstrap:
  sysprep:
    sysprep:
      guiUnattended: {autoLogon: true, autoLogonCount: 1, timeZone: 85}
      identification: {joinWorkgroup: WORKGROUP}
      userData: {fullName: Lab, orgName: Lab, computerName: {name: win01}}
```

Or `rawSysprep` with an unattend XML in a Secret if you already have one.
The ISO from [the blueprint post](/posts/nested-esxi-via-vcfa-all-apps/)
can ride along as a declarative `hardware.cdrom` — handy for tools and
agents on first boot.

## The ESXi footnote: one gateway, many vmks

Once the appliance is up and you add vMotion and vSAN vmks on their own
subnets, you hit a detail that makes the Host Client *look* wrong:

![Host Client: vmk0/1/2, one service each](/images/ui/u12-hostclient-vmk-adapters.jpg)

ESXi's default TCP/IP stack has **one** default gateway — vmk0's `.33` —
and the UI repeats it on every vmk row. Same-subnet vMotion never uses a
gateway so nothing breaks, but each NSX subnet *does* have its own
gateway, and cross-subnet traffic from vmk1/vmk2 would take the wrong exit.
Set per-vmk override gateways:

```
esxcli network ip interface ipv4 set -i vmk1 -t static -I 172.30.0.70  -N 255.255.255.224 -g 172.30.0.65
esxcli network ip interface ipv4 set -i vmk2 -t static -I 172.30.0.100 -N 255.255.255.224 -g 172.30.0.97
```

Now the display is truthful and the routing is correct. (The full-realism
alternative is a dedicated `vmotion` netstack for vmk1; I kept the default
stack so the service tags stay visible in the Host Client.)

## Rules learned

- **No DHCP in VPC subnets** — by design. NSX allocates at the port; the
  guest is told via a bootstrap provider.
- `cloudInit` (Linux), `sysprep` (Windows), `vAppConfig` (appliances) —
  typed fields on the VM, not customisation specs.
- Appliance addresses must match the **realized** subnet; fix the order
  of subnet creation if you want fixed addresses across pods.
- ESXi has **one** default gateway per stack. Set `-g` per vmk, or the
  Host Client lies to you and cross-subnet traffic exits wrong.
- A static IP plan is a feature in a lab: it's what makes screenshots,
  runbooks and pods identical.

*Companion to [nested ESXi inside an NSX VPC](/posts/nested-esxi-nsx-vpc/).*

---
*Lab environment; opinions my own.*
