---
title: "fluent-bit two ways: VKS add-on and Windows agent, one log endpoint"
date: 2026-09-16T12:00:00+01:00
draft: false
tags: [observability, fluent-bit, vks, windows, vcf-operations-for-logs, logging]
series: ["Observability on VCF"]
cover:
  image: "/images/post19-hero-fluentbit.svg"
  alt: "Two fluent-bit shippers — a VKS package and a Windows service — converging on one Ops for Logs endpoint"
  hidden: false
summary: "The same log pipeline for two very different worlds: fluent-bit as a VKS package (values secret, CFAPI output, verified 200s per batch) and fluent-bit as a Windows service on Server 2025 shipping the event log to the same VCF Operations for Logs endpoint. One backend, two configs, and what each side taught me."
---

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

Auth is [enabled but optional by default](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/log-analysis/overview-of-log-management-agents/agent-authentication-for-log-ingestion.html):
the endpoint accepts events with or without a token, unless strict
authentication is enabled in Global Settings, which drops any request
without a valid Bearer token. Our shippers sent no token; the lab ran the
default. What matters for fluent-bit is the URI, the port, TLS, and a JSON body
shaped as `{"events":[...]}`. Both shippers below produce exactly that.

## Way 1: VKS package

VKS ships fluent-bit in its standard package repository. On a cluster with
the repo registered:

```
kubectl ... get packages -n tkg-system 2>&1 | Select-String -Pattern 'NAME|telegraf|prometheus|fluent|cert-manager|contour' | Out-String
NAME                                                                  PACKAGEMETADATA NAME                             VERSION                  AGE
...
fluent-bit.kubernetes.vmware.com.4.0.2+vmware.1-vks.1                 fluent-bit.kubernetes.vmware.com                 4.0.2+vmware.1-vks.1     55s
fluent-bit.kubernetes.vmware.com.4.0.5+vmware.1-vks.1                 fluent-bit.kubernetes.vmware.com                 4.0.5+vmware.1-vks.1     55s
fluent-bit.tanzu.vmware.com.2.2.3+vmware.1-tkg.2                      fluent-bit.tanzu.vmware.com                      2.2.3+vmware.1-tkg.2     56s
fluent-bit.tanzu.vmware.com.3.1.9+vmware.1-tkg.1                      fluent-bit.tanzu.vmware.com                      3.1.9+vmware.1-tkg.1     55s
fluent-bit.tanzu.vmware.com.3.2.7+vmware.1-tkg.1                      fluent-bit.tanzu.vmware.com                      3.2.7+vmware.1-tkg.1     55s
...
```

A values secret configures the output — the package's own default output
shape targets CFAPI, so the values are short:

```yaml
namespace: tanzu-system-logging
fluent_bit:
  config:
    outputs: |
      [OUTPUT]
        Name          http
        Match         *
        Host          f06-flt-log01.res.lab
        Port          9543
        URI           api/v2/events
        Format        json
        tls.debug     4
        tls           on
        tls.verify    off
        json_date_key timestamp
```

Then a `PackageInstall` referencing it:

```yaml
apiVersion: packaging.carvel.dev/v1alpha1
kind: PackageInstall
metadata: { name: fluent-bit, namespace: package-installs }
spec:
  serviceAccountName: pkgi-sa
  packageRef:
    refName: fluent-bit.kubernetes.vmware.com
    versionSelection: { constraints: 4.0.5+vmware.1-vks.1 }
  values:
  - secretRef: { name: fluent-bit-values }
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

**One trap** (shared with Telegraf, [next post](/series/observability-on-vcf/)):
a cluster created without `clusterNetwork.serviceDomain` produces in-cluster
service names of the form `...svc.` with no domain, which some add-ons
build into unresolvable URLs. It's immutable after create; set it
explicitly on every new cluster.

![VCF Operations — Logs: text contains vks-demo01, last 24 h, 1.74K events](/images/ui/l2-ops-logs-vks-demo01-query.jpg)
*The receiving end. One filter — `text contains vks-demo01` — and a day of the cluster's logs, one bar per hour.*

![The stream: container logs arriving with Kubernetes metadata — app, cluster, container, kubernetes_namespace, node, pod](/images/ui/l1-ops-logs-vks-demo01-24h.jpg)
*Every event carries the fields the package's filters add — `cluster`, `kubernetes_namespace`, `pod`, `container` — which is what makes the Windows-vs-VKS comparison in one explorer possible later.*


## Way 2: Windows Server 2025 service

fluent-bit ships a Windows build with a `winevtlog` input. On the
[pipeline-built W2025 server](/series/the-windows-build-pipeline/) I used the
portable zip rather than the MSI — no installer, a folder under `C:\`, a
service registered with `sc.exe`. A small script writes the config below
(`$LogsHost` is the appliance's FQDN, `$LogsPort` 9543); four of its lines
turned out to matter:

```ini
...

[INPUT]
    Name          winevtlog
    Channels      System,Application,Security
    Interval_Sec  5
    DB            $root\winevt.db
    String_Inserts On
    Tag           winevt

[FILTER]
    Name    modify
    Match   *
    Rename  Message  text
    Add     hostname $hostname
    Add     appname  v-windows
    Add     source   windows-server-2025

[OUTPUT]
    Name    http
    Match   *
    Host    $LogsHost
    Port    $LogsPort
    URI     /api/v2/events
    Format  json
    Header  Content-Type application/json
    tls     On
    tls.verify Off
    json_date_key    timestamp
    # ISO-8601 timestamps are rejected (400: not a valid Long); the API reads the number as epoch MILLISECONDS
    json_date_format epoch_ms
    net.dns.resolver LEGACY
    net.connect_timeout 20
    Retry_Limit      5
```

The service came up first time. Getting a single event to *land* took four
attempts, and each failure taught something the documentation doesn't say:

```
[error] [output:http:http.0] no upstream connections available to f06-flt-log01.res.lab:9543
```
**1. fluent-bit couldn't resolve a name Windows could.** `Resolve-DnsName`
worked; `Test-NetConnection … -Port 9543` worked; fluent-bit's own async
resolver didn't. `net.dns.resolver LEGACY` hands DNS back to the OS.

```
[error] [output:http:http.0] 10.26.5.25:9543, HTTP status=404
```
**2. The appliance routes on the Host header.** Sidestepping DNS by using
the IP gets a 404 for *every* path. Address it by FQDN.

```
{"errorMessage":"Cannot deserialize value of type `java.lang.Long` from String \"2026-09-16T10:55:00.000000Z\""}
```
**3. Timestamps must be numeric.** fluent-bit's `iso8601` output is a
string; the ingest API wants a Long. Worse: it reads that number as
**milliseconds**, so on the Windows agent the default `double` (epoch
*seconds*) is accepted with a 200 and files your events in January 1970.
`epoch_ms`. Our VKS values set no format at all, and those events land on
time.

```
{"received":0,"message":"events ingested","status":"ok"}
```
**4. The message field must be called `text`.** Anything else — `Message`
as `winevtlog` emits it, `message`, `log` — returns 200 and
`received: 0`. Silently dropped. Hence the `Rename` filter. Broadcom's own
[reference config for Windows](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/log-analysis/overview-of-log-management-agents/install-fluent-bit-on-windows-server-for-vcf-operations-for-logs.html) carries exactly this line; I found it the hard
way first.

Then, finally:

```
[ info] [output:http:http.0] f06-flt-log01.res.lab:9543, HTTP status=200
[ info] [output:http:http.0] f06-flt-log01.res.lab:9543, HTTP status=200
```

![Ops for Logs: hostname contains TEST-W2025 — Windows System, Application and Security events, with channel, computer, eventid and appname as fields](/images/ui/w3-ops-logs-test-w2025-events.jpg)
*Fifty events in the first five minutes: service state changes, a "system time was changed" security event with its full subject block, all searchable with the same fields as everything else.*

![The same explorer with both hostnames in one filter: TEST-W2025 and vks-demo01](/images/ui/w4-ops-logs-windows-and-vks-filter.jpg)
*One filter, two worlds. A Windows server and a Kubernetes cluster, in the same query, in the same store.*

One more Windows-specific note: a bare `fluent-bit.exe` registered with
`sc.exe` isn't a proper service binary — it ignores the stop signal and
Windows sits at "waiting for service to stop" until you kill the process.
The MSI installs a real service wrapper; use it for anything that isn't a
lab.

## The shape they share

| | VKS package | Windows service |
|---|---|---|
| Install | `PackageInstall` | MSI / `sc.exe create` |
| Config | values Secret | `fluent-bit.conf` |
| Inputs | pre-wired (containers, kubelet, systemd) | `winevtlog` channels you choose |
| Output | `http` → CFAPI :9543 `api/v2/events` | `http` → CFAPI :9543 `/api/v2/events`, `epoch_ms`, resolver and header lines |
| Verify | pod log `HTTP status=200` | service log `HTTP status=200` — and check the *date* on what arrived |
| Restart safety | Kubernetes | `DB` bookmark file |

Both outputs post JSON events to the same :9543 endpoint. They differ in
the URI form, the date handling (fluent-bit's default against `epoch_ms`)
and the resolver and header lines only Windows carries. That's the lesson:
standardise the *sink* and let each platform own its *source*.

## Why this matters outside the lab

The business outcome is one place to look. Windows servers, Kubernetes
clusters and the platform itself all ship logs to the same VCF Operations
for Logs, with the same fields, searchable in one query — so an incident
that spans a Windows service and a container gets investigated in one
screen instead of three tools. Standardising the *destination* while
letting each platform keep its native shipper is also what keeps the
estate maintainable: one endpoint to secure and retain, no bespoke agent
per team.

## Rules learned

- Ops for Logs ingestion = CFAPI `:9543/api/v2/events`, JSON. One endpoint
  serves every shipper.
- On VKS, use the **package**; decide only the output. Verify from the
  pod log — the Ops API is awkward to script against.
- Set `serviceDomain` on every new VKS cluster; it's immutable.
- On Windows: FQDN not IP (Host-header routing), `net.dns.resolver LEGACY`,
  `Rename Message text`, `json_date_format epoch_ms`. Each one fails
  differently and two of them fail *silently*.
- A `200` is not proof. `received: 0` is a drop; a seconds timestamp from
  the Windows agent is a 200 filed in 1970. Look for the event in the explorer before you call it done.
- Prove "one endpoint" with one explorer view showing both sources.

## Broadcom documentation

- [Install Fluent Bit Package](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kuberenetes-service-clusters-and-workloads/installing-standard-packages-on-tkg-service-clusters/installing-standard-packages-on-tkg-cluster-using-tkr-for-vsphere-8-x/install-fluent-bit/install-fluent-bit-package.html): the VKS standard package, `fluent-bit.kubernetes.vmware.com` from 4.0.x, installed with a data values file
- [Fluent Bit Package Reference](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-0/managing-vsphere-kuberenetes-service-clusters-and-workloads/installing-standard-packages-on-tkg-service-clusters/standard-package-reference/fluent-bit-package-reference.html): the package's values, with an `http` output to VCF Operations on port 9543
- [Set up the Windows system to collect logs in VCF Operations](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/log-analysis/overview-of-log-management-agents/install-fluent-bit-on-windows-server-for-vcf-operations-for-logs.html): Broadcom's fluent-bit MSI and `winevtlog` config for Windows Server 2022 and 2025, `Rename Message text` and `epoch_ms` included
- [Agent Authentication for Log Ingestion](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/log-analysis/overview-of-log-management-agents/agent-authentication-for-log-ingestion.html): optional Bearer-token authentication on HTTP ingestion, fluent-bit included

*Next: [Telegraf on Windows Server 2025 — unsupported, works anyway](/series/observability-on-vcf/).*

---
*Lab environment; opinions my own.*
