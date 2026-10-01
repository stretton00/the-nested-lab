---
title: "vLLM metrics into VCF Operations, part 1: don't ship the histogram"
date: 2026-09-30
draft: false
tags: [vllm, llm, observability, vcf-operations, prometheus, powershell, gpu]
products: ["VCF Operations", "Private AI"]
series: ["LLM Ops on VCF"]
seriesPart: 1
tldr:
  - "Send vLLM's few hundred Prometheus series per model straight into VCF Operations, and the dashboard tells an operator nothing."
  - "VCF Operations stores gauges and has no `histogram_quantile`, so the pipeline works out P50, P95 and P99 before pushing."
  - "Push four gauges per histogram, keep state so counters become rates, and treat the drop-list as design, not housekeeping."
tested: "VCF 9.1"
cover:
  image: "/images/post13-hero-vllm.svg"
  alt: "Prometheus histogram buckets in; flat P50/P95/P99 gauges out"
  hidden: false
summary: "vLLM exposes about 200 Prometheus series per model, and pushing them raw into VCF Operations is a cardinality bomb. A pipeline that computes the useful numbers client-side and drops what can't be graphed."
---

vLLM's `/metrics` endpoint is generous. Every model instance exposes a few
hundred Prometheus series: counters, gauges and histograms. The histograms
are the problem, with dozens of buckets each.

Point a naïve scraper at it, push everything into VCF Operations, and you
get two things. One is a time-series database (TSDB) full of
`_bucket{le="0.05"}` series nobody will ever graph. The other is a
dashboard that tells an operator nothing, in tremendous detail.

This two-parter is the pipeline that fixed that. Part 1 is the design:
what to compute, what to drop, and why. [Part 2](/series/llm-ops-on-vcf/)
is the operations story: scheduling, self-monitoring and alerts.

## The core decision: percentiles are computed here, not there

A Prometheus histogram is a set of cumulative bucket counters:

```
vllm:time_to_first_token_seconds_bucket{le="0.1"}   1203
vllm:time_to_first_token_seconds_bucket{le="0.25"}  4871
vllm:time_to_first_token_seconds_bucket{le="0.5"}   7120
...
vllm:time_to_first_token_seconds_bucket{le="+Inf"}  7412
vllm:time_to_first_token_seconds_sum                1812.4
vllm:time_to_first_token_seconds_count              7412
```

Prometheus turns that into a P95 at query time with `histogram_quantile`.
VCF Operations has no such function: it stores gauges. So the pipeline
does the interpolation *before* pushing:

```powershell
function Get-Percentile {
    param([array]$Buckets, [double]$Total, [double]$Percentile)
    $target = $Percentile * $Total
    $prevLe = 0.0; $prevCount = 0.0
    foreach ($b in $Buckets) {                    # sorted by le, +Inf last
        if ($b.Count -ge $target) {
            if ($b.Le -eq [double]::PositiveInfinity) { return $prevLe }
            $frac = ($target - $prevCount) / ($b.Count - $prevCount)
            return $prevLe + $frac * ($b.Le - $prevLe)   # linear within the bucket
        }
        $prevLe = $b.Le; $prevCount = $b.Count
    }
}
```

That's linear interpolation within the bucket that crosses the target
rank, the same approximation Prometheus makes. Out come **four flat gauges
per histogram**: `p50_ms`, `p95_ms`, `p99_ms` and `avg_ms` (from
`_sum/_count`). Twenty-odd series become four, and they're the four an
operator reads.

It's applied to time to first token (TTFT), end-to-end latency,
inter-token latency, time per output token, prefill time, decode time,
inference time and queue time.

## Rates need memory

Counters (`generation_tokens_total`, `request_success_total`) are useless
as absolute values. What you want is tokens *per second*, and that needs
the previous sample. So the script keeps state. `llm-metrics-state.json`
holds the last counters and timestamp for each target, and each run works
out the deltas:

```
tokens_per_sec = (tokens_now - tokens_prev) / (t_now - t_prev)
```

The same trick goes one step further for **live latency**. `_sum` and
`_count` are both counters, so `Δsum / Δcount` is the *mean over the last
interval*, not the all-time mean the histogram gives you. That's how you
get a `live_avg_ttft_ms` that reflects the last 60 seconds instead of the
last fortnight.

Two guards make this safe:

- **Stale-state protection.** If the gap since the last run is over 300 s
  (scheduler stopped, server rebooted), the baseline is dropped. Otherwise
  you'd get a diluted "per-second" rate, averaged over an hour.
- **Restart detection.** A counter that went *down* means vLLM restarted,
  because counters don't go backwards for fun. The delta for that cycle is
  discarded.

## Derived metrics: what the raw numbers won't tell you

Two computed values earn their place at the top of the dashboard.

**Queue pressure ratio:** `(waiting + swapped) / (running + 1)`. Above
1.0, more requests are waiting than being served, so scale out.

**System saturation score** (0–100):

```powershell
$saturation = ($kvCachePct * 0.5) + ($queuePressure * 25.0)
if ($saturation -gt 100) { $saturation = 100 }
```

A full KV (key-value) cache alone scores 50, and queue pressure of 2.0
scores the other 50. It's a heuristic, and it's deliberately one number.

Think of it as a dial that goes red when the engine is about to start
swapping requests to CPU memory. That's the moment latency falls off a
cliff. Warning is at 75, critical at 90.

![vllm|perf|system_saturation_score over the last hour in VCF Operations](/images/ui/o6-ops-vllm-saturation-score.jpg)
*The dial, as Ops draws it: one gauge climbing towards the warning line as KV-cache use and queue pressure rise together. (Test-mode data: see part 2.)*

Also derived:

- prefix-cache hit rate, live and all-time;
- average request size, from the dropped `http_request_size_bytes` `_sum`;
- uptime in days;
- `is_up = 1` on every successful scrape, so the *absence* of the metric
  is the alert.

That last one does its most useful work by not turning up.

## What gets dropped, and why

The `$DropPrefixes` list is as important as anything computed:

| Dropped | Why |
|---|---|
| `python_gc_*`, `python_info` | runtime noise; static text can't be graphed |
| `process_max_fds`, `vllm:cache_config_info`, `vllm:engine_sleep_state` | static configuration, not performance |
| `vllm:request_params_*` | **cardinality explosion** — a series per distinct `max_tokens`/`n` |
| `vllm:iteration_tokens_total` | redundant with tokens/s |
| `http_request_duration_highr_seconds` | "high-resolution" = hundreds of buckets; the standard one suffices |
| `http_request/response_size_bytes` buckets | dropped, but `_sum` harvested for an average |
| `*_created` | bucket-initialisation timestamps; pure noise |

Everything that survives is truncated to two decimals before the push.
It's a small mercy for the TSDB.

## The key hierarchy

Ops shows metrics as a tree, so the names are designed for browsing:

```
vllm|system|is_up
vllm|throughput|total_tokens_per_sec
vllm|perf|live_avg_ttft_ms
vllm|perf|ttft|p95_ms
vllm|queue|pressure_ratio
vllm|memory|kv_cache_pct
vllm|cache|live_prefix_hit_rate_pct
vllm|process|rss_memory_gb
```

`vllm | category | metric [| percentile]`. An operator who has never seen
vLLM can find "time to first token, 95th percentile" without a manual.

![The key hierarchy as it lands in VCF Operations](/images/ui/o5-ops-vllm-metric-tree.jpg)
*`vllm | category | metric` in the Ops metric picker — see [part 2](/series/llm-ops-on-vcf/) for how this was captured.*

## Why this matters outside the lab

Organisations putting language models into service soon discover that "is
it up?" isn't the question. The real questions are these. How long are
users waiting for the first word? Is the service about to run out of
memory? Do we need another GPU before Friday?

This pipeline answers them inside the same VCF Operations console the
infrastructure team already lives in. So AI services get the same capacity
planning, alerting and dashboards as everything else. There's no second
monitoring stack, and no new team to staff it.

## Rules learned

- **Never push raw histogram buckets** into a gauge-oriented TSDB.
  Interpolate P50/P95/P99 client-side and push four gauges.
- Counters need **state**: keep the last sample, compute deltas, and drop
  the baseline after a long gap (300 s) rather than dilute the rate.
- `Δsum/Δcount` gives you *live* mean latency, which is far more useful
  than the all-time mean.
- One derived **saturation score** beats six raw gauges at the top of a
  dashboard. Make it explainable (KV% × 0.5 + pressure × 25).
- The drop-list is a design artefact, not housekeeping. `request_params_*`
  alone can double your series count.
- Name for browsing: `product | category | metric`.

## Broadcom documentation

- [Super Metric Functions and Operators](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/configuring-super-metrics/super-metrics-tab/super-metric-functions-and-operators.html): the functions an Ops formula can use; none of them is a percentile
- [Using the API with VCF Operations](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/administration-sdks-cli-and-tools/understanding-the-vr-ops-api/using-the-api-with-vrealize-operations-manager.html): the REST API the pipeline pushes through, and the Swagger reference on the appliance
- [Generate a List of All Metrics for the Object](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/administration-sdks-cli-and-tools/understanding-the-vr-ops-api/getting-started-with-the-api/generate-a-list-of-all-metrics-for-the-object.html): reading an object's stat keys back, grouped with `|` as in `mem|host_workload`
- [Symptom Definitions in VCF Operations](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/infrastructure-operations/configuring-alerts-and-actions/symptom-definitions.html): metric symptoms at Warning and Critical levels, as for the saturation score

*Part 2: [running it as a service, monitoring the monitor, and the four
alerts](/series/llm-ops-on-vcf/).*

---
*Lab environment; opinions my own. Config shown is sanitised; the script's
test mode reads a local metrics file instead of a live endpoint.*
