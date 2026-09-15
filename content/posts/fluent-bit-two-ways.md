---
title: "fluent-bit two ways: VKS add-on and Windows agent, one log endpoint"
date: 2027-04-28
draft: true
tags: [observability, fluent-bit, vks, windows, vcf-operations-for-logs, logging]
series: ["Observability on VCF"]
cover:
  image: "/images/post19-hero-fluentbit.svg"
  alt: "Two fluent-bit shippers — a VKS package and a Windows service — converging on one Ops for Logs endpoint"
  hidden: false
summary: "The same log pipeline for two very different worlds: fluent-bit as a VKS package (values secret, CFAPI output, verified 200s per batch) and fluent-bit as a Windows service on Server 2025 shipping the event log to the same VCF Operations for Logs endpoint. One backend, two configs, and what each side taught me."
---

> **DRAFT STATUS:** VKS half is complete from live evidence. Windows half
> needs a capture session on the W2025 box (install, config, first events
> arriving in Ops for Logs). Marked **[CAPTURE]** below.

Logs from a Kubernetes cluster and logs from a Windows server end up in
the same place — VCF Operations for Logs — but the paths there couldn't
look more different. On VKS, fluent-bit is a *package*: declare a values
secret, reconcile, done. On Windows it's a *service*: install, write a
config by hand, restart, tail the debug log. Same binary, same output
plugin, same endpoint. This post is both, side by side, so the shared
shape is obvious.

## The endpoint

VCF Operations for Logs ingests over its **CFAPI** on port 9543:

```
https://<ops-logs>:9543/api/v2/events
```

Auth is Ops-side (the ingestion endpoint accepts from configured sources);
what matters for fluent-bit is the URI, the port, TLS, and a JSON body
shaped as `{"events":[...]}`. Both shippers below produce exactly that.

## Way 1: VKS package

VKS ships fluent-bit in its standard package repository. On a cluster with
the repo registered:

```
kubectl get packages -A | grep fluent-bit
  fluent-bit.fluent-bit.tanzu.vmware.com   4.0.5+vmware.1-vks.1
```

A values secret configures the output — the package's own default output
shape targets CFAPI, so the values are short:

```yaml
fluent_bit:
  config:
    outputs: |
      [OUTPUT]
        Name    http
        Match   *
        Host    f06-flt-log01.res.lab
        Port    9543
        URI     /api/v2/events
        Format  json
        tls     On
        tls.verify Off
        json_date_key    timestamp
        json_date_format iso8601
```

Then a `PackageInstall` referencing it:

```yaml
apiVersion: packaging.carvel.dev/v1alpha1
kind: PackageInstall
metadata: {name: fluent-bit, namespace: tanzu-packages}
spec:
  serviceAccountName: tanzu-packages-sa
  packageRef: {refName: fluent-bit.fluent-bit.tanzu.vmware.com, versionSelection: {constraints: 4.0.5+vmware.1-vks.1}}
  values: [{secretRef: {name: fluent-bit-values}}]
```

`Reconcile succeeded`, and the proof is in the pod logs, not the Ops UI —
Ops for Logs' API auth is identity-broker federated, so scripted
verification from the shipper side is far easier:

```
[ info] [output:http:http.0] f06-flt-log01.res.lab:9543, HTTP status=200
[ info] [output:http:http.0] f06-flt-log01.res.lab:9543, HTTP status=200
```

One 200 per batch. That's the whole VKS side, and it's why the packaged
path is the one to recommend: the inputs (container logs, kubelet,
systemd) are pre-wired, the parsers are right, and the only decision you
make is the output.

**One trap** (shared with Telegraf, [next post](/posts/telegraf-windows-2025/)):
a cluster created without `clusterNetwork.serviceDomain` produces in-cluster
service names of the form `...svc.` with no domain, which some add-ons
build into unresolvable URLs. It's immutable after create; set it
explicitly on every new cluster.

![VCF Operations — Logs: text contains vks-demo01, last 24 h, 1.74K events](/images/ui/l2-ops-logs-vks-demo01-query.jpg)
*The receiving end. One filter — `text contains vks-demo01` — and a day of the cluster's logs, one bar per hour.*

![The stream: container logs arriving with Kubernetes metadata — app, cluster, container, kubernetes_namespace, node, pod](/images/ui/l1-ops-logs-vks-demo01-24h.jpg)
*Every event carries the fields the package's filters add — `cluster`, `kubernetes_namespace`, `pod`, `container` — which is what makes the Windows-vs-VKS comparison in one explorer possible later.*

> **[SHOT]** optional: `kubectl get pkgi -A` (Reconcile succeeded) + the pod-log `HTTP status=200` lines.

## Way 2: Windows Server 2025 service

**[CAPTURE]** — the section below is the plan; fill in with the live run.

fluent-bit ships a Windows build with `winevtlog` and `winlog` inputs. On
the [pipeline-built W2025 server](/posts/windows-2025-aria-part-1/):

1. Install the MSI (or unzip the portable build to `C:\fluent-bit`).
2. `conf\fluent-bit.conf`:

```ini
[SERVICE]
    Flush        5
    Log_Level    info
    Parsers_File parsers.conf

[INPUT]
    Name         winevtlog
    Channels     System,Application,Security
    Interval_Sec 5
    DB           C:\fluent-bit\winevt.db
    Tag          winevt

[FILTER]
    Name    modify
    Match   *
    Add     hostname ${COMPUTERNAME}
    Add     source   windows-server-2025

[OUTPUT]
    Name    http
    Match   *
    Host    f06-flt-log01.res.lab
    Port    9543
    URI     /api/v2/events
    Format  json
    tls     On
    tls.verify Off
    json_date_key    timestamp
    json_date_format iso8601
```

3. Register as a service and start:

```
sc.exe create fluent-bit binpath= "C:\fluent-bit\bin\fluent-bit.exe -c C:\fluent-bit\conf\fluent-bit.conf" start= auto
sc.exe start fluent-bit
```

4. Verify the same way as VKS — from the shipper: `HTTP status=200` lines
   in the fluent-bit log, then the events in Ops for Logs filtered by
   `hostname`.

Things to check during capture: the `DB` bookmark file so restarts don't
replay the whole Security log; `Security` channel needs the service to run
as an account with the *Event Log Readers* right (or SYSTEM); event
`Message` fields are large — consider `String_Inserts On` and dropping
the raw XML.

> **[CAPTURE]** Shots: services.msc with fluent-bit Running; the log 200s;
> Ops for Logs showing a Windows Security event beside a VKS container log
> in the same explorer view — that's the money shot for "one endpoint".

## The shape they share

| | VKS package | Windows service |
|---|---|---|
| Install | `PackageInstall` | MSI / `sc.exe create` |
| Config | values Secret | `fluent-bit.conf` |
| Inputs | pre-wired (containers, kubelet, systemd) | `winevtlog` channels you choose |
| Output | `http` → CFAPI :9543 `/api/v2/events` | identical |
| Verify | pod log `HTTP status=200` | service log `HTTP status=200` |
| Restart safety | Kubernetes | `DB` bookmark file |

The output stanza is byte-identical. That's the lesson: standardise the
*sink* and let each platform own its *source*.

## Rules learned

- Ops for Logs ingestion = CFAPI `:9543/api/v2/events`, JSON. One output
  stanza serves every shipper.
- On VKS, use the **package**; decide only the output. Verify from the
  pod log — the Ops API is awkward to script against.
- Set `serviceDomain` on every new VKS cluster; it's immutable.
- On Windows, `winevtlog` + a `DB` bookmark; run as SYSTEM or grant Event
  Log Readers for `Security`.
- Prove "one endpoint" with one explorer view showing both sources.

*Next: [Telegraf on Windows Server 2025 — unsupported, works anyway](/posts/telegraf-windows-2025/).*

---
*Lab environment; opinions my own.*
