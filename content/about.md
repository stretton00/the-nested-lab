---
title: "About"
ShowToc: false
ShowReadingTime: false
ShowBreadCrumbs: false
summary: "Who writes this, what the lab is, and the one rule every post follows."
---

I'm **Adam Stretton** — a Lead Consultant who has spent the last decade
designing, deploying and automating VMware Cloud Foundation platforms for
enterprise customers, usually several layers of virtualisation deep.

The day job is end-to-end cloud transformation: VCF architecture and
deployment across private and hybrid estates; day-zero-to-day-two
automation with VCF/Aria Automation, PowerShell and infrastructure-as-code;
and governance, lifecycle and observability with VCF/Aria Operations. The
thread through all of it is the same — take the manual overhead out of
infrastructure delivery, standardise it, and give teams self-service they
can trust. I've found that works when technical precision, process and the
people involved move together, which is why a lot of what I do is bridging
operations, architecture and development teams rather than just building
things.

This blog is the lab notebook behind that work. Certifications, for the
curious: [credly.com/users/adam-stretton](https://www.credly.com/users/adam-stretton).

## What this blog is

VCF 9.x platform engineering, **proven live**. Nested ESXi, NSX VPC
networking, VCF Automation "All Apps", VKS, the observability stack — and
the failure modes the documentation doesn't mention. Every post follows one
rule: the commands, output and error messages you see were captured from a
running environment. Trimmed for length, never edited for outcome. Where a
capture is synthetic (a test-mode run, a simulated scrape) the caption says
so.

The posts group into series, and the series read in order:

- **[The VPC Pod Papers](/series/the-vpc-pod-papers/)** — what an NSX VPC
  is, why nested ESXi blackholes inside one, and the trunk-subnet design
  that turns cookie-cutter isolated environments into a catalog item.
- **[The Lab Factory](/series/the-lab-factory/)** — a complete nested VCF
  9.1 instance from one request form: hosts, bringup, day-N, `validateOnly`
  everywhere.
- **[All Apps in Practice](/series/all-apps-in-practice/)** — VKS clusters
  and demo stacks through VCF Automation's supervisor-native path.
- **[Observability on VCF](/series/observability-on-vcf/)** and **[LLM Ops
  on VCF](/series/llm-ops-on-vcf/)** — fluent-bit, Telegraf and a vLLM
  metrics pipeline into VCF Operations.
- **[Dark Site Notes](/series/dark-site-notes/)** — air-gapped VKS and GPU
  Operator upgrades, and everything that has to cross the airlock intact.
- **[The Windows Build Pipeline](/series/the-windows-build-pipeline/)** — a
  reboot-safe Windows Server 2025 provisioning state machine on Aria
  Automation.

## The lab

A multi-pod nested VCF estate: each pod is a full VCF 9.x instance
(vCenter, NSX, SDDC Manager, the fleet components, a vSphere Supervisor
with NSX VPC networking) running on nested ESXi hosts, built and rebuilt
by the automation described in the Lab Factory series. Identifiers you'll
see throughout — `res.lab`, `f06`, `172.30.0.0/16`, `192.168.144.x` — are
the lab's own. Nothing here is a customer environment.

## Disclaimer

This is a personal blog. Opinions are my own and not my employer's or
Broadcom's. Everything described here was performed in a lab environment;
test before you trust anything in production. Product names are the
property of their respective owners.

If something here saved you an afternoon — or cost you one because I got it
wrong — [tell me](/contact/).
