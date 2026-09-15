---
title: "Driving the VCF Installer API from vRO: generate, validate, start, walk away"
date: 2027-03-30
draft: false
tags: [vcf, bringup, vcf-installer, vro, vcf-automation, api, nested-esxi]
series: ["The Lab Factory"]
cover:
  image: "/images/post23-hero-installer.svg"
  alt: "Spec derived from X, validated by the installer, bringup started, task id returned; a second run polls without the catalog's leash"
  hidden: false
summary: "Stage 2 of the lab factory: a vRO workflow that turns an environment number into a complete VCF 9.1 deployment spec, runs the installer's own validation, starts bringup and hands back a task id — because the request dies long before the eight-hour build does. Plus how the wrapper slips the two-hour leash."
---

The [nested hosts exist](/posts/porting-a-powershell-deploy-script/). Now
they need to become a VCF instance: vCenter, NSX, SDDC Manager, the fleet
components. The VCF 9.1 Installer appliance does that from a deployment
spec — a few hundred lines of JSON — through an API. This post is the vRO
workflow that drives it, and the three design constraints that shaped it:
nobody edits the spec by hand, the request can't outlive two hours, and
nested hosts fail hardware validation.

Unlike stage 1 this isn't VM provisioning, so it's not a cloud template.
It's a **vRO workflow published directly as a catalog item** through an
Orchestrator content source.

## The spec is generated, never edited

A vRO action, `buildVcfDeploymentSpec(environment, hostFqdns, labPassword,
…)`, returns the whole spec as a string. Its structure was reconciled
against a *validated* export from a real bringup — the installer UI lets
you export the spec it accepted — and everything variable derives from the
environment number X:

| Element | Pattern | f03 |
|---|---|---|
| Names | `f0X-m01-*` | `f03-m01-vc01.res.lab` |
| Subnets | `10.(20+X).<sub>.0/24` | `10.23.1.0/24` (mgmt) |
| VLANs | `2X0<sub>` | 2301 mgmt … 2306 TEP |
| Gateways | `.254` | `10.23.1.254` |
| vMotion / vSAN ranges | `.1–.16` | `10.23.3.1-16` |
| NSX TEP pool | `.6.1–.6.32` | `10.23.6.1-32` |
| SDDC Manager | `f0X-vcf01.res.lab` | `f03-vcf01.res.lab` |

```javascript
var n   = parseInt(environment.substring(1), 10);   // "f03" -> 3
var pfx = environment + "-m01";
var net = "10." + (20 + n);
function vlan(o) { return 2000 + (n * 100) + o; }
function gw(sub) { return net + "." + sub + ".254"; }
```

Static across environments: DNS, NTP, subdomain, component sizes, vSAN ESA
FTT=1, and the component build versions pinned to the installer binaries.
One lab password feeds every credential field (the UI export scrubs them;
the action puts them back per the API schema).

Two spec-level decisions worth stealing:

- `skipEsxThumbprintValidation: true` instead of carrying per-host
  `sslThumbprint`. Supported, and the right trade-off for a lab.
- Ops and Automation are **checkboxes** that add their blocks to the spec
  — and the installer only accepts a `licenseServerSpec` when Ops is
  present, so the action adds them together or not at all.

## The workflow: authenticate → validate → start → return

```
1. POST /v1/tokens                 installer login
2. POST /v1/sddcs/validations      the installer's OWN pre-flight on the spec
   (poll until COMPLETED; fail on any FAILED check)
3. if validateOnly -> return the validation report; touch nothing
4. POST /v1/sddcs                  start bringup -> sddcTaskId
5. return { sddcTaskId, installerUrl }
```

Step 2 is the [validateOnly](/posts/validateonly-everywhere/) story made
concrete: the installer will tell you, in seconds, that
`f03-m01-nsx01.res.lab` doesn't resolve, that an IP is in use, that a host
isn't reachable. Two hours into a bringup is a bad time to learn that.
Every one of the ~40 DNS records the pre-flight wants is created ahead of
time by a one-shot PowerShell script (`New-LabEnvDnsRecords.ps1`) — DNS is
a prerequisite, not a step.

## The two-hour leash, and how to slip it

A request from the catalog carries a token with a roughly **two-hour**
lifetime, and a bringup takes around **eight**. So by default the workflow
is fire-and-forget: `waitForCompletion=false`, return the task id, watch
progress in the installer UI. A `watchTaskId` input lets you re-attach
later and poll an already-running bringup from a new request.

The wrapper that chains *everything* — hosts, bringup, then the day-N
components that need bringup to be finished — has a neater trick. The
catalog-bound parent deploys the hosts, submits bringup, and then
**re-executes itself as a plain vRO run** (Orchestrator → Run, no catalog
token, no two-hour kill) carrying the hidden `bringupWatchTaskId`. That
continuation polls the installer task to completion — eight hours, fine —
and then runs certificates, fleet items, edge, supervisor and identity.
Watch it under *Orchestrator → Activity → Runs*. The catalog request
itself completes in under an hour — 47 minutes on the run pictured below — having
*started the work correctly and handed off*.

![Orchestrator runs: the catalog-bound parent (13:12→14:00) and the continuation it spawned (14:00 → 01:56 next day)](/images/ui/f5-f00-vro-runs-parent-continuation.jpg)
*Two rows, one build. The parent returns inside the catalog's window; the continuation waits out the bringup and does the day-N work.*

![The deployment's stackSummary output: hosts ready, bringup completed, continuation started — watch it in Orchestrator › Activity › Runs](/images/ui/f4-f00-stack-outputs-continuation.jpg)


## Nested-host frictions

Three things a physical bringup never meets:

- **HCL validation vs virtual NVMe.** The installer's hardware check
  blocks the virtual NVMe controller. Fix at the vLCM layer:
  `enforce_hcl_validation=false` on the image policy. The vSAN health test
  `nvmeonhcl` also complains; silenced via the vSAN API, best-effort with
  manual fallback.
- **DVS compatibility appears late.** After bringup, NSX takes 1–2 hours
  to settle before the supervisor's zones endpoint stops returning 500.
  If the supervisor stage fails "No compatible DVS" on a fresh instance,
  wait and re-run just that item.
- **TSM-SSH.** Bringup wants SSH on the hosts; the wrapper enables it
  host-direct via SOAP before submitting.

## Stale schema: the failure that looks like a bug and isn't

Add an input to the vRO workflow after the catalog item exists and the
form will show the new field, the request will record its value, and the
workflow will receive **null** — Service Broker keeps the old request
schema until the content source re-imports. The workflow null-guards every
boolean and aborts with "inputs not mapped" rather than running with
silently-wrong options. Fix: re-import the content source, confirm the
schema, submit a *new* request (resubmitting an old one reuses the old
payload).

There are actually three async layers between "publish" and "mappable
request" — vRO processing the import, the catalog schema after re-import,
and the form service still enforcing the previous custom form for a minute
or two. Same symptom for all three. Check timing before assuming a bug.

## Rules learned

- **Generate the spec** from a validated export plus one number. Nobody
  hand-edits JSON at 2am.
- Run the **installer's own validation** first, and make it a mode you
  can request on its own.
- Pre-create DNS. Enable SSH. Disable HCL enforcement on virtual NVMe.
- Respect the request lifetime: **start, return a task id, re-attach**.
  For a long chain, have the workflow re-run itself outside the catalog.
- Null-guard every input and fail loud; stale schemas are a fact of life
  after adding inputs.
- On a fresh instance, give NSX an hour before you expect DVS
  compatibility.

*Part of [The Lab Factory](/series/the-lab-factory/). Previously:
[porting the host script](/posts/porting-a-powershell-deploy-script/).*

---
*Lab environment; opinions my own. Bringup verified end-to-end on a
rebuilt environment: 305/305 tasks, `COMPLETED_WITH_SUCCESS`.*
