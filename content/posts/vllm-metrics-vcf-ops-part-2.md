---
title: "vLLM metrics into VCF Operations, part 2: monitor the monitor"
date: 2026-10-14
draft: false
tags: [vllm, llm, observability, vcf-operations, telegraf, powershell, alerting]
series: ["LLM Ops on VCF"]
cover:
  image: "/images/post14-hero-vllm-ops.svg"
  alt: "Telegraf runs the script every 60 s; the script's stdout is one integer; the integer is the health of the integration"
  hidden: false
summary: "The design from part 1 is only useful if it runs every minute, forever, and tells you when it stops. The stdout contract that lets Telegraf monitor the integration itself, batched pushes, log rotation, the four alerts to configure on day one, and the offline test mode that lets you build all of this without a GPU."
---

[Part 1](/posts/vllm-metrics-vcf-ops-part-1/) was about *what* to push.
This is about making it boring: scheduled, self-monitoring, alertable, and
testable without a live model.

## Execution pipeline

Each run does seven things:

1. **Authenticate once** to VCF Operations (PowerCLI's Ops module for the
   token; native `Invoke-RestMethod` for everything after — far faster).
2. **Iterate targets** from the config file.
3. **Resolve the resource** — look up the Ops object by name. The target
   must already exist in Ops (a VM, a container object, a custom
   application). Exact match first, partial match with a warning second.
4. **Scrape** the Prometheus text from `:8000/metrics`.
5. **Parse and transform** — gauges, counters, histograms; percentiles,
   deltas, derived scores; drop-list applied.
6. **Push in batches of 1000** stats per request. Ops rejects oversized
   payloads; a busy model produces ~150 stats per run, but a config with
   ten targets doesn't.
7. **Persist state** — counters and timestamps per target. Targets removed
   from the config are pruned from the state file automatically.

## The stdout contract

The single most useful design choice: when run non-interactively, **the
script prints exactly one integer** — the total number of stats pushed.

That makes it a Telegraf `inputs.exec` plugin with zero glue:

```toml
[[inputs.exec]]
  commands = ['powershell.exe -NoProfile -File C:\monitoring\Push-LLMMetrics.ps1']
  timeout = "50s"
  interval = "60s"
  data_format = "value"
  data_type = "integer"
  name_override = "llm_metrics_pushed"
```

Telegraf now has a series called `llm_metrics_pushed` that should read ~150
every minute. If it reads 0, the scrape failed. If it's *missing*, the
script didn't run. The integration monitors itself by construction, and the
thing watching it is the same Telegraf you already run.

(Task Scheduler or cron work too — `powershell.exe -File Push-LLMMetrics.ps1`
every 60 s — you just lose the free self-monitoring.)

## Configuration

Credentials and targets live in a JSON file beside the script, never in it:

```json
{
  "vrops": {
    "server": "vcfops.example.lab",
    "user": "svc_vllm_metrics",
    "password": "<from-credential-store>",
    "auth_source": "local"
  },
  "targets": [
    { "subject": "LLM01", "metrics_url": "http://10.0.0.5:8000/metrics" },
    { "subject": "LLM02", "metrics_url": "http://10.0.0.6:8000/metrics" }
  ]
}
```

`subject` must match the Ops resource name exactly. `-ConfigPath` overrides
the location for scheduled tasks. `auth_source` is `local` or your AD
domain.

## Logging that doesn't fill the disk

Interactive runs get colour-coded console output. Silent runs mirror
everything to `llm-metrics.log`, which rotates itself to `.old` at 5 MB.
The three warnings you'll actually see:

| Log line | Meaning | Action |
|---|---|---|
| `Resource NOT found with exact name 'LLM01' - looking for partial match` | Ops object name doesn't match `subject` | create the object or fix the spelling |
| `Rates are exactly 0` | no traffic since last run | normal when idle |
| `Time gap too large (>300s). Resetting baseline` | scheduler paused / host rebooted | normal; rates resume next run |

And one error: `API Error on batch: 401 Unauthorized` — the service
account expired or locked. It's the only failure that needs a human.

## The offline test mode

You do not need a GPU to build this. `metrics_url` accepts `file://`:

```json
{ "subject": "LLM01", "metrics_url": "file://C:/temp/llm_metrics.txt" }
```

Save one real `/metrics` scrape to a text file, point the config at it,
and iterate on parsing and Ops resource mapping at your desk. To test the
rate maths, bump the counter values in the file between runs — the script
can't tell the difference, and neither can Ops.

## The four alerts to configure on day one

Everything in part 1 was designed so these four symptoms are one metric
each:

| Alert | Symptom | What it means |
|---|---|---|
| **vLLM Engine Down** | `vllm\|system\|is_up` missing or < 1 | container crashed or `/metrics` unreachable |
| **OOM Imminent** | `vllm\|perf\|system_saturation_score` > 90 | KV cache full, queue stacking — new prompts will be rejected |
| **Severe End-User Lag** | `vllm\|perf\|live_avg_tpot_ms` > 100 | generating slower than people read (~50 ms/token); users see stutter |
| **Queue Spillage** | `vllm\|queue\|requests_swapped` > 0 | engine evicting live requests to CPU RAM — should *always* be 0 |

Suggested thresholds for the rest, from the field:

- `live_avg_ttft_ms` — warn 1000, critical 3000 (TTFT drives abandonment)
- `queue|pressure_ratio` — warn 0.5, critical 1.0 (more waiting than running → scale out)
- `memory|kv_cache_pct` — warn 85, critical 95
- `queue|preemptions_per_sec` — warn > 0
- `http|requests_per_sec` ≫ `throughput|requests_per_sec` — users are getting 429/503 at the front door


## What running it against a fresh Ops taught me

I re-ran the collector in `file://` mode against a lab VCF Operations 9.1
that had never seen it, pointing at an existing VM object. Three findings
in the first ten minutes, all worth knowing before you deploy:

1. **The stdout integer lied once.** The first two runs logged
   `[ERR] The SSL connection could not be established` on the push — and
   still printed `Total stats pushed: 76`. The counter tallies stats
   *prepared*, not batches *accepted*. Telegraf would have seen a healthy
   76 while nothing landed. Fix for v6.4: increment only on a 2xx from the
   batch push, and print 0 on any batch error. Until then, alert on the
   log's `[ERR]` lines too.
2. **The push path needs its own certificate handling.** The PowerCLI
   connect honours `Set-PowerCLIConfiguration -InvalidCertificateAction
   Ignore`; the native `Invoke-RestMethod` pushes don't. On PowerShell 7,
   `$PSDefaultParameterValues['Invoke-RestMethod:SkipCertificateCheck']=$true`
   before the run (or trust the Ops CA properly) — otherwise auth succeeds
   and every push fails.
3. **Metric names drift between vLLM versions.** Newer vLLM exposes
   `vllm:time_per_output_token_seconds`; the key builder was written for
   `vllm:request_time_per_output_token_seconds`, so the newer name fell
   through the hierarchy and landed as a raw top-level metric in Ops
   (`vllm_time_per_output_token_seconds`) instead of `vllm|perf|tpot|*`.
   Everything else — `vllm|perf|ttft|p95_ms`, `vllm|throughput|total_tokens_per_sec`,
   `vllm|perf|system_saturation_score`, the `http|request_duration` percentiles —
   arrived exactly where the design says. Add the new name to the mapping
   and treat "unexpected top-level metric" as a check in the smoke test.

Everything else worked first time: resource resolved by name, 89 stats per
run, batches accepted, rates flowing from the second run onwards.

![VCF Operations: the vllm metric tree on the target object — requests, system|is_up, throughput, tokens — with prompt_total and live_avg_generation_tokens_per_req charted over the last hour](/images/ui/o5-ops-vllm-metric-tree.jpg)
*The tree as an operator sees it, browsable without a manual. Captured from the `file://` test run above — the pipeline and the Ops side are real; the model behind the numbers was a saved scrape with advancing counters.*

## What I'd change

Two things, honestly:

- It's PowerShell because the monitoring host was Windows and PowerCLI was
  already there. The same design ports to Python in an afternoon; the
  value is the *transformation*, not the language.
- Ops resource resolution by *name* is fragile. Resolving by an identifier
  stored in the config after first lookup would survive a rename.

## Rules learned

- Make the collector's **stdout a single integer** and let the scheduler
  (Telegraf) monitor the integration for free.
- Batch pushes (1000 stats). Authenticate once per run, not per push.
- `file://` targets let you develop the whole pipeline with zero GPUs.
- Four alerts cover 90 % of incidents: down, saturated, laggy, swapping.
  Everything else is a threshold on an existing gauge.
- Log rotation is part of the script, not an ops afterthought.

*Previously: [don't ship the histogram](/posts/vllm-metrics-vcf-ops-part-1/).
Related: [Telegraf on Windows Server 2025](/series/observability-on-vcf/) —
where this script actually runs.*

---
*Lab environment; opinions my own. Config sanitised.*
