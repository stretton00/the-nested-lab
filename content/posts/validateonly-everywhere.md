---
title: "validateOnly everywhere: plan mode for infrastructure"
date: 2027-03-02
draft: false
tags: [automation, vro, vcf-automation, opinion, platform-engineering]
series: ["The Lab Factory"]
cover:
  image: "/images/post18-hero-validateonly.svg"
  alt: "One checkbox on every form: validateOnly. Tick everything, plan the whole stack, change nothing."
  hidden: false
summary: "Terraform has plan. Kubernetes has --dry-run. Your vRO workflows have nothing — unless you give them a validateOnly input and make the wrapper cascade it. A short argument for the single most valuable checkbox in the lab factory, with the failures it caught."
---

Terraform has `plan`. Kubernetes has `--dry-run=server`. Ansible has
`--check`. Every mature infrastructure tool grew a way to say "tell me what
you'd do, then don't" — because the alternative is finding out at 2am, two
hours into a bringup, that a hostname doesn't resolve.

vRO workflows don't come with one. This is the case for adding it to every
single one you write, and cascading it through every wrapper.

## The shape

Every catalog item in [the lab factory](/posts/one-catalog-item-one-vcf-instance/)
has a boolean input, `validateOnly`, default false. When true the workflow
does *everything it can without changing anything*:

- authenticate to every endpoint it would touch
- resolve every name it would use, and fail on the ones that don't
- generate every spec it would submit, and run the target's own validation
  API on it where one exists (the VCF Installer has one; use it)
- check for collisions — names, IPs, existing objects
- report what it *would* have created, then return `CREATE_SUCCESSFUL`

The wrapper — the one form that chains hosts, bringup, supervisor, fleet
components, identity — has the same checkbox, and **cascades** it to every
component. Tick everything, tick validateOnly, request. Thirty seconds to
a few minutes later you have a full-stack plan against the *live*
environment, and nothing has moved.

## What it caught

Not hypothetically. On a built environment, the cascaded dry run of the
whole stack reported:

- edge cluster: **already exists** — correctly recorded, wrapper carried on
- Ops for Logs: **IP_IN_USE** on the planned address — right, it's deployed
- Ops for Networks: same
- supervisor: the existing one would be reused; the per-service plan
  listed which services were already active
- identity: bind succeeded, group resolved, no changes needed

That's a plan output. On a *fresh* environment the same run has caught, at
various times: a DNS record missing for one of ~40 required names (the
installer's own pre-flight found it, in seconds, instead of bringup
finding it in hour two); a stale content-library image ID; a form field
arriving `null` because a custom form hadn't finished re-importing — which
is a *publishing* bug the dry run surfaced before anyone requested
anything real.

## The argument against, answered

"It doubles the code." It doesn't — it moves the `if (!validateOnly)` guard
around the mutating call, and the validation logic is code you should have
had anyway. What it *does* force is separating "compute what to do" from
"do it", which is how the workflows should have been structured in the
first place.

"Some things can't be validated without doing them." True. Say so in the
result summary — "would deploy X; no pre-validation available" — rather
than skipping the item. Partial plans are still plans.

"We have a test environment." You have *a* test environment. A dry run
against the *target* is what catches the collision with the thing that's
already there.

## Make it the smoke test

The best consequence: a validateOnly request against a known environment
is a **regression test for the automation itself**, runnable on every
change. The factory's smoke runner does exactly this — request every item
with `validateOnly: true`, assert `CREATE_SUCCESSFUL`, diff the plan
summary against the last run. It takes minutes and it has caught more
bugs in the workflows than any amount of code review.

![Deploy VCF Stack request form: one checkbox per component, and validateOnly](/images/ui/f2-f00-stack-form-validateonly.jpg)
*The same form, real or dry-run. One checkbox decides.*

## Rules learned

- Add `validateOnly` to **every** workflow. Default false. Wrappers
  cascade it.
- Dry-run does everything but mutate: auth, resolve, generate, call the
  target's validator, check collisions, report.
- Where a step truly can't be pre-validated, *say so* in the summary.
  Never skip it silently.
- A dry run against the real target is a plan. A dry run on every change
  is a smoke test. Same checkbox.
- The refactor it forces — compute, *then* act — is the one you wanted.

*Part of [The Lab Factory](/series/the-lab-factory/).*

---
*Lab environment; opinions my own.*
