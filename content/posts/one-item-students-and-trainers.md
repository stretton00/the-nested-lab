---
title: "One catalog item, two audiences: a trainers list decides where the lab lands"
date: 2027-01-20
draft: false
tags: [vcf, vcf-automation, blueprints, property-groups, self-service, homelab]
series: ["The Lab Factory"]
cover:
  image: "/images/post28-hero-trainers.svg"
  alt: "A Phase 1 request with Lab: student04 meets one check on the server, whether env.requestedBy is on the trainers list in nestedLabSite: a trainer's lab lands in vpc-student04, everyone else's in their own VPC"
  hidden: false
summary: "Students request their own labs; trainers build a lab for any student. We kept two copies of each student blueprint to do it, and sharing one catalog item across projects did not reach the students on VCF Automation 9.1. Now one blueprint per phase decides on the server, from a trainers list in a property group, where each lab lands. The expression, the proof, and three test requests on f06."
---

Phase 1 of our lab catalog existed twice, and so did Phase 2. The catalog API
on f06 listed them like this:

```text
lab-phase-1-dc-build         global=False requestable=True  projects=['67df468d']
...
lab-phase-2-blank-hosts      global=False requestable=True  projects=['67df468d']
lab-phase-1-dc-build         global=False requestable=True  projects=['5330317d']
...
lab-phase-2-blank-hosts      global=False requestable=True  projects=['5330317d']
```

The first pair lived in the instructors' project (on f06 simply
`default-project`) with a lab name field, so a trainer could build or rebuild
any student's lab. The second pair lived in `lab-students`, bound to whoever
made the request, so a student's lab always went into their own VPC. Same
labs, same names, two blueprints each: every change meant ten blueprints to
generate, validate and release for eight kinds of lab. Two copies that must
stay in step except where they differ on purpose are how drift starts, and a
review of our release tool found it looking blueprints up by name alone,
which with two copies could pick the other project's. Publishing all six
phases to the students would have meant six of each.

I wanted one blueprint per phase. Here is how that works, and what I checked
first.

## Two audiences, one lab

A lab in this catalog is an isolated nested-ESXi environment in an NSX VPC of
its own. [Every lab uses the same addresses](/posts/three-datacenters-one-ip-plan/),
so each student has a VPC named after them: `vpc-student01` for `student01`,
and so on. The two audiences want different things from the same item:

- A student requests Phase 1 or 2 without typing a lab name or choosing a
  network, and cannot aim a request at someone else's VPC, even by accident.
- A trainer builds or rebuilds a lab for any student, and now and then one of
  their own.

The students' copies did their part with one expression. VCF Automation hands
every request the user who made it as [`env.requestedBy`](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/vcfa-overview/working-with-the-vcf-automation-catalog/maphead-designing-your-deployments/expressions-general/expressions-syntax.html), and the blueprint
turns that into a DNS label: the part before the `@`, lower case, dots as
hyphens. The label names everything in the lab: the VPC it attaches to, the
namespace (`ns-student01-` and a random suffix), the VMs (`esx01-student01`)
and the jump host.

## Sharing the item did not reach the students

The obvious fix was one item in the instructors' project, shared with every
project in the organization (Catalog Item Sharing, "allow all projects"). I
tried it with a throw-away blueprint. The organization's API service account
could not request in the students' project even as a member ("Bad project
ID ... Check project settings for your service roles"), so the test that
counted ran as `student01`:

```text
release: 201 RELEASED
student01's catalog: 200 ['lab-phase-1-dc-build', 'lab-phase-2-blank-hosts']
the shared item is NOT in the student's catalog
...
zz-share-test3               global=True  requestable=True  projects=['67df468d']
...
direct GET of the shared item: 404 {"message":"No value present","statusCode":404,"errorCode":0}
request from lab-students: 404 {"message":"No value present","statusCode":404,"errorCode":0}
```

The item was marked global, and the student could neither see it nor open it
by its ID. The 9.1 documentation says the all-projects setting makes a
catalog item [available to all other projects](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/setting-up-the-content-hub-in-vcf-automation-for-all-apps-organizations/publishing-content-to-the-vcf-automation-catalog/edit-blueprint-settings-in-vcf-automation.html); that is not what a
student in another project saw here.
Nor does the organization offer a policy type for sharing content:
its types are lease, day-2 action, approval and supervisor IaaS. On VCF
Automation 9.1, for us, an item reaches the members of its own project, so it
has to live where the students are.

## Let the blueprint decide

So the design turned around. Each phase that students may request lives once,
in `lab-students`, and trainers become members of that project too. The item
decides on the server, from the user who made the request, where the lab
goes. The trainers are a list, `trainers`, in the property group
`nestedLabSite`, which already holds [every site value](/posts/lab-catalog-property-groups/).
This is the VPC line of the released Phase 1:

```yaml
vpcName: ${'vpc-' + ((contains(propgroup.nestedLabSite.trainers, replace(to_lower(split(env.requestedBy, '@')[0]), '.', '-')) && input.labName != 'mine') ? input.labName :replace(to_lower(split(env.requestedBy, '@')[0]), '.', '-'))}
```

Read it from the inside: take the requester's label; if it is on the trainers
list and the Lab field says anything but "My own lab", the lab is the one
picked, otherwise it is the requester's own. The same expression names the
namespace, the VMs, the jump host and the lab ID in the jump host's config,
so the whole lab follows one identity. A student can pick `student04` on the
form; the blueprint ignores it.

The form carries both audiences' fields, and says who each one counts for:

```yaml
  labName:
    type: string
    title: Lab (trainers choose; a student always gets their own)
    description: >-
      Trainers: the lab to build, named after its student - its VPC is vpc-<lab>. Students: ignored - a
      student's lab always goes into their own VPC.
    default: mine
    oneOf:
      - title: "My own lab"
        const: mine
...
  jumpSize:
    type: string
    title: Jump host size (trainers only)
    description: "Students: not used - a student's lab takes the class default."
```

Four fields end with `(trainers only)`: the software release, the jump host
size and the two disk sizes. For anyone off the list, the blueprint reads the
class defaults from the property groups instead, with the same test, for
example `(contains(...) ? input.release :propgroup.nestedLabMedia.defaultRelease)`.
The request form puts those fields on a Trainer options tab, which is the
next post's story.

![The Phase 1 request form's Trainer options tab: a note that the settings do nothing for students, Lab set to My own lab, then the release, the jump host size and the two disk sizes, each marked trainers only](/images/ui/phase1-form-trainer-options.png)

The odd spacing in `? input.labName :replace(` is deliberate. Some of these
expressions are plain YAML scalars, and there a colon followed by a space
starts a mapping.

## Prove the rule first

Blueprint validation does not evaluate expressions, so before the generator
changed I deployed a namespace-only test blueprint whose outputs showed the
rule's parts. The first draft request tripped over exactly that colon:

```text
draft request: 400 {"message":"Failed to parse blueprint: mapping values are not allowed here\n in 'reader', line 31, column 176:\n     ... 0]), '.', '-')) ? input.labName : replace(to_lower(split(env.req ...
```

With the values quoted, and a few unrelated fixes to the test blueprint
itself, the draft deployed. `isTrainer` tested a literal list that held the
requester, `notTrainer` one that did not, and `lab` and `labOther` applied the
rule with each list to a Lab field set to `student05`. It ran as the API
service account, whose name I have masked:

```text
deployment: CREATE_SUCCESSFUL
outputs: {'lab': 'student05', 'whoami': '<api service account>', 'labOther': '<api service account>', 'isTrainer': True, 'notTrainer': False}
```

`contains()` works on a list, the requester is known on the server, and the
choice follows the list. Only then did the generator get its shared mode; the
list in the property group got its proof from real requests.

## The trainers list is data

The list lives in the site file. The generator writes it into `nestedLabSite`
in the form the expression compares (lower case, dots as hyphens), and the
sync tool pushes it. For the tests, `student06` played a trainer:

```text
nestedLabSite: 1 change(s)
  trainers: '(none)' -> ['student06']
  updated nestedLabSite (id 424a2fc4-f0b9-4c9e-b344-684b72f95493)
nestedLabMedia: up to date
```

That was the whole change. Blueprints read the property groups when a lab is
requested, so adding or removing a trainer needs no new blueprint version.
The list is also the one thing to guard. A user on it can build in any
student's VPC, and a trainer missing from it counts as a student: their
request would look for a VPC named after them, which does not exist.

## Three requests on f06

`student01`, not on the list, requested Phase 1 with Lab set to `student04`:

```text
request as student01: 200 inputs={'labName': 'student04'} [{"deploymentId": "7ce19793-dd85-4da2-aa5a-6ee648402ff9", "deploymentName": "student01-p1x"}]
15:46:11 namespace ns-student01-zcj76
15:47:49 VMs: dc01-student01=PoweredOn esx01-student01=PoweredOn esx02-student01=PoweredOn esx03-student01=PoweredOn esx04-student01=PoweredOn jump-student01=PoweredOff
```

The form said `student04`, and the lab took the student's own name. The delete
tool, which reads the lab's VPC from the deployment, later confirmed it:
`clean - vpc-student01 has no subnets left, a new lab can use it`.

Then `student06`, on the list, made the same request, and our follower tool
timed out:

```text
request as student06: 200 inputs={'labName': 'student04'} [{"deploymentId": "3d0a99e3-f16b-4806-bfd4-fb8afd1b74c8", "deploymentName": "student06-p1t"}]
16:05:52 time limit reached (15 min) - the deployment is not done yet
```

The deployment was fine. When a deployment does not report its namespace, the
follower guesses it from the deployment's name, and this one sent it looking
for `ns-student06-`. Asked directly, VCF Automation had it all:

```text
status: CREATE_SUCCESSFUL | owner: student06 | project: 5330317d-0ae5-48da-82de-e2378da48a2f
supervisor namespace: ns-student04-nfnny vpc: vpc-student04
```

In this design trainers are organization administrators, not organization
users. So the third request repeated the second with `student06` promoted for
the test, and with the deployment named after the lab it builds:

```text
request as student06: 200 inputs={'labName': 'student04'} [{"deploymentId": "1a54e483-9de6-4d44-b3eb-acc8fc151d97", "deploymentName": "student04-p1t"}]
16:10:50 namespace ns-student04-7lgnz
16:13:01 deployment done, all VMs powered on
```

Afterwards `student06` went back to Organization User and the list to empty
(`trainers: ['student06'] -> []`). The lesson for our tools: name a deployment
`<lab>-p<phase>`, after the lab it builds.

Note `owner: student06`. A lab a trainer builds is the trainer's deployment:
the student does not see it under Instances and cannot open its host
consoles, so a lab a student will work in is best requested by the student.

One limit is worth saying out loud. Every student VPC sits on the students'
project's Associated VPCs list, so it is the catalog, not the platform, that
keeps a student in their own VPC, as long as every item students can request
decides on the server like this one. A project per student would move that
boundary into the platform, with one more project per student to keep in step
with every release.

f06 now holds each phase once: after this change and a clean-up of old test
blueprints, nine blueprints for nine catalog items.

## Why this matters outside the lab

Self-service works when people can help themselves without being able to get
in each other's way. A student gets a lab with two decisions and no way to
land it in someone else's network. A trainer uses the very same catalog item
to build, rebuild or rescue any student's lab. What tells them apart is
checked by the platform when the request runs, not by what the form happens
to show.

It also halves the upkeep. One blueprint per phase means one change, one
validation and one release, and the two audiences cannot drift apart because
there is nothing left to drift. Who counts as a trainer is data in a property
group: onboarding a trainer is a one-line change with no new catalog version.

The pattern fits any catalog with requesters and operators, such as
developers who each get a sandbox while the platform team can build one for
any team.

## Rules learned

- On VCF Automation 9.1, an item shared with all projects did not reach
  another project's members for us (404). Publish it in the project its
  requesters belong to.
- Decide on the server. `env.requestedBy` is who asked; the form is only what
  they typed.
- Keep role lists in a property group and test them with
  `contains(propgroup.<group>.<list>, <requester>)`. Adding a trainer is a
  sync, not a release.
- Reduce the requester to one form everywhere (the part before `@`, lower
  case, dots as hyphens), and store the list in that form.
- In a plain YAML scalar, a colon followed by a space starts a mapping. Quote
  the value, or write a ternary as `? a :b`.
- Mark the fields that do nothing for some requesters, such as
  `(trainers only)`.
- Name a deployment after the lab it builds (`<lab>-p<phase>`), not after the
  requester.
- Test self-service as the people who will use it: the API service account
  could not even request in the students' project.

## Broadcom documentation

- [Expression syntax in VCF Automation for VM Apps](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/vcfa-overview/working-with-the-vcf-automation-catalog/maphead-designing-your-deployments/expressions-general/expressions-syntax.html): `env.requestedBy`, the ternary, and `contains`, `split`, `to_lower` and `replace`
- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): property groups shared with the organization or kept to one project
- [Publish a Blueprint to the Catalog in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/setting-up-the-content-hub-in-vcf-automation-for-all-apps-organizations/publishing-content-to-the-vcf-automation-catalog/publish-vcf-automation-blueprints-to-the-catalog.html): releasing a version, by default to the members of the blueprint's project
- [Share Blueprints with Other VCF Automation Projects and Organizations](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/setting-up-the-content-hub-in-vcf-automation-for-all-apps-organizations/publishing-content-to-the-vcf-automation-catalog/edit-blueprint-settings-in-vcf-automation.html): the documented setting that shares a catalog item with all other projects
- [Managing Predefined User Roles in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/administering-users-and-groups-in-vcf-automation-for-all-apps.html): organization administrator and user, and the project roles
- [Managing Policies in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/creating-policies-for-all-apps-orgs.html): the policy types: approval, day 2 action, lease, IaaS resource and infrastructure

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
