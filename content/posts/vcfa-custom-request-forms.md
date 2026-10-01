---
title: "Custom request forms in VCF Automation 9.1: two tabs, a text box, and the version that keeps its own copy"
date: 2027-01-27
draft: false
tags: [vcf, vcf-automation, blueprints, custom-forms, self-service, homelab]
series: ["The Lab Factory"]
cover:
  image: "/images/post29-hero-forms.svg"
  alt: "The blueprint's formId points at the custom form with its Your lab and Trainer options tabs; each new version copies it as <name>/<version> with a formId of its own, and the request page shows the released version's copy; a CCI content update clears formId, so the release tool puts it back before versioning"
  hidden: false
summary: "We built a friendlier request form for our lab catalog: two tabs and a text box with the rules. The form service saved it, its renderer served it, and the request page kept showing the generated form. How VCF Automation 9.1 actually picks a request form, why our release tool wiped it on every release, and the upkeep a custom form brings."
---

The form was saved. The form service said so, and its renderer, asked for the
form by the blueprint's ID, answered with our two tabs (asked by the catalog
item's ID, it still had the generated form's single page, General):

```text
lab-phase-2-blank-hosts (lab-students): catalog item 1b035714-2499-3377-a8bc-df55802f55e5, blueprint 367e85a3-4bef-417e-b5b1-fdcd4280521e, custom forms now: none
  tab Your lab:        hostSize, jumpPassword
  tab Trainer options: labName, release, jumpSize, capacityDiskGi, bootDiskGi
  stored: form e5e72baa-d312-49d6-8931-754945b1b9c4, status ON

catalog item formId: None
== sourceType=com.vmw.blueprint&sourceId=1b035714-2499-3377-a8bc-df55802f55e5&formType=reques 200 pages: ['General']
== sourceType=com.vmw.blueprint&sourceId=367e85a3-4bef-417e-b5b1-fdcd4280521e&formType=reques 200 pages: ['Your lab', 'Trainer options']
```

Signed in as `student01`, the request page for the same item showed VCF
Automation's generated form: one page, one section per field, no tabs and no
text.

![VCF Automation's generated request form on nested-esxi-lab-jump: one page with Project, Deployment Name, Lab, the jump host password, Software release and Jump host size, and no tabs or text](/images/ui/generated-form-lab-jump.png)
*Every phase has its own form now, so this is the generated form on an item that still has none: a jump-host-only test item, requested as an administrator.*

## Why a custom form

The people who request labs from this catalog are mostly new to VCF
Automation; that is why they are in a class. The design goal is that nobody
should need to understand the blueprint to request a lab, and the generated
form works against it. It lists every input on one page in blueprint order,
so on the Phase 1 and 2 items that [students and trainers now share](/posts/one-item-students-and-trainers/),
five of the seven fields do nothing for a student. And a password that breaks
the rule is refused with the rule itself as the message: a regular
expression.

So each phase got a form of its own, on two tabs. "Your lab" opens with a
text box holding the rules people trip over, then the host size and the
passwords. "Trainer options" says who its fields count for, then holds the
Lab list, the release, the jump host size and the disk sizes.

## Built from the generated form

Our tool, `lab_forms.py`, does not write forms from scratch. It asks the form
service for the item's generated form (`designer/request` with the item's
schema), keeps every field as generated, with its values, defaults and rules,
and moves the fields onto pages; the only field it rewrites is the jump host
password's help and error text. A page is a tab. The text box is the
designer's Text element. I found no form with one to copy, so its format
started as a guess; the designer and the request page both render it:

```python
def text_field(fid, text):
    """a read-only text on the form (the designer's Text element)"""
    return ({"id": fid, "display": "text", "state": {"visible": True, "read-only": True}},
            {"label": "", "type": {"dataType": "string", "isMultiple": False}, "default": text})
```

A student's first tab starts: "Your lab is built in your own network,
vpc-<your user name>. You can have one lab at a time: before you request
another, delete this one (Instances, your lab, Actions > Delete) and wait 5
minutes after it has disappeared from Instances." It uses the portal's own
words and names no script, because the people reading it work in the portal.
The second tab starts: "These settings are for trainers. For students they
have no effect: a student's lab always goes into their own network and uses
the class defaults."

The password rule needed words too. The generated schema carries the pattern,
and the jump host's pattern spells each refused word in both cases, because a
form pattern cannot ignore case:

```text
 "label": "Jump host password for user 'student' (RDP)",
 ...
 "constraints": {
  "min-value": 12,
  "max-value": 64,
  "pattern": {
   "value": "^(?!.*(?:[sS][vV][cC]-[dD][oO][mM][aA][iI][nN][jJ][oO][iI][nN]|[sS][vV][cC]-[mM][oO][nN][iI][tT][oO][rR][iI][nN][gG]|...
```

That pattern was the error text a requester saw. The pattern object takes a
`message`, and the tool sets it: "This password will not work: use 12 to 64 characters with upper and
lower case letters, a number and one of ! @ # * _ = + . , ? -, start with a
letter or a number, and leave out the words listed in the help (i)."

## Where the request page looks

The form service keys a blueprint's form by a source ID, so I had stored it
under the classic blueprint ID, and then under the catalog item ID as well.
Its renderer served our tabs for both, and the request page still showed the
generated form. A new version, 2.1.2, changed nothing, and the blueprint's
form designer still offered "New Form", as if no form existed.

So I let the designer show me. I imported our JSON with Actions > Import
form, clicked Create, and versioned the blueprint in the UI as 2.1.3. The
designer showed the tabs, and the records showed what had changed:

```text
form {"formId": "4bcd5911-11f4-4267-a1f5-e3cfa6d2ca83", "formName": "lab-phase-2-blank-hosts/2.1.3", "sourceType": "com.vmw.blueprint", "imported": false, ...}
version {'version': '2.1.3', 'status': 'RELEASED', 'createdAt': '2026-09-30T13:37:18.305076Z', 'createdBy': 'adam'}
...
{'updatedAt': '2026-09-30T13:36:28.221597Z', 'updatedBy': 'adam', 'totalVersions': 12, 'totalReleasedVersions': 2, 'formId': '85d36ae4-d5ad-4206-8d78-8135237e1254', ...}
```

That is the mechanism. The classic blueprint record
(`/blueprint/api/blueprints/{id}`) has a `formId`, and the designer's Create
sets it. Creating a version copies that form into a new one named
`<name>/<version>`, with a `formId` of its own on the version, and the request
page renders the released version's copy. A form stored by source ID alone is
never read by the request page, however `ON` its status; the renderer does
return it, which is what had misled me. The catalog item's own `formId`
stayed empty throughout, and the admin API that might have set it answered
403 to our service account. It was never needed.

## The release tool wiped it

`lab_forms.py` now points the blueprint at its form with a PUT of the classic
record, as the designer does. The first release through our normal release
tool undid it:

```text
release 2.1.4: 200
2.1.4 formId: None
blueprint formId after the release's PUT: None
```

Our release tool updates the content through the CCI API, where a blueprint
is a Kubernetes-style `Blueprint` object whose spec holds only the content and
the description. After that PUT the classic record's `formId` was empty, so
every release would have gone out with the generated form. The tool now reads
`formId` before the content update and writes it back before it creates the
version:

```python
# 30 Sep: a custom request form hangs on the blueprint (formId, set by tools/lab_forms.py or the designer's Create), and
# each new version takes a copy of it - but the content PUT below clears formId, so remember it and put it back first
FORM_BID, _cb = classic_blueprint() if code == 200 else (None, None)
FORM_ID = (_cb or {}).get("formId")
...
if FORM_ID:
    _bid, _b = classic_blueprint()
    if _b:
        body = {k: _b.get(k) for k in ("name", "description", "content", "projectId", "requestScopeOrg")}
        body["formId"] = FORM_ID
        c3, r3 = call("PUT", "%s/%s" % (CL, _bid), body)
```

`classic_blueprint()` matches the project as well as the name, because the
same blueprint name once lived in two projects. The next release shows both
IDs, the blueprint's form and the version's own copy:

```text
PUT blueprint: 200 OK
ContentValid: True
custom form kept on the blueprint (0725938e-73b7-4c54-adbd-85d20b795f94): 200 OK
create version 2.1.5: 200
version 2.1.5 request form: custom (b5c56c2a-8eb5-40eb-861a-2ae407d1d14b)
un-release 2.1.4: 200
release 2.1.5: 200
```

That `request form:` line costs one GET, and it turns a silent fallback into a
line in the log. When the blueprint has a custom form and the new version did
not get one, the line ends in a warning.

## One retry

Applying the forms to all six phases hit one refusal, straight after the tool
had deleted the phase's previous form:

```text
  create form failed: 400 {"timestamp":"2026-09-30T13:49:18.233+0000","path":"/form-service/api/forms","status":400,"error":"Bad Request",...
```

A second run went through. The tool now waits five seconds and retries once,
and a comment says why, so nobody removes it as noise. The next release gave
all six phases their own copies, and when I opened the Phase 1 and Phase 6
request pages, both showed the two tabs. My only notes were about the
wording.

![The Phase 1 request page with its custom form: the Your lab and Trainer options tabs, and the rules text above the two fields a student fills in](/images/ui/phase1-form-your-lab.png)

## A form is a copy

The price is upkeep. The stored form is a full copy of the generated form at
the moment the tool built it: labels, help texts, defaults, the choices of
every list, the password patterns. Each field is still tied to its input by
name, but its choices and starting value are copies, and every version then
takes a copy of that copy. When a blueprint input changes, say a new entry in
the Release list, the next version carries the new input in its content and
the old choices on its form, until the forms are built again from the new
version and released once more.

So a change to a field is two releases: one for the blueprint, one for the
rebuilt forms. f06's last catalog refresh went out that way, as 2.1.9 with
the new blueprints and 2.1.10 with the forms rebuilt from them:

```text
  stored: form 8334f47a-091d-45d1-b551-2be9c3716dcb, status ON
  blueprint formId -> 8334f47a-091d-45d1-b551-2be9c3716dcb: 200
...
== lab-phase-1-dc-build (lab-students, shared) -> blueprint-nested-esxi-lab-builddc.yaml 2.1.10, 59737 bytes
   version 2.1.10 request form: custom (57266e03-7b31-4db8-94fe-6b8d38d29552)
   release 2.1.10: 200
...
== nested-esxi-lab-jump (default-project, labname) -> blueprint-nested-esxi-lab-jump.yaml 2.1.10, 49780 bytes
   version 2.1.10 request form: VCF Automation's generated form
```

The two dev items keep the generated form on purpose; only the six phases
have custom ones.

## Why this matters outside the lab

A request form is the front door of a self-service catalog, and most people
who come through it will never read a blueprint. Putting the rules on the
form, in the portal's own words, answers the questions that would otherwise
become tickets: where does my lab go, why can I only have one, what do I do
with blank hosts. Moving the fields that don't concern a requester to another
tab keeps the first screen down to the decisions they actually make.

The mechanism matters because the failure is silent. A form that falls back
to the generated one after a release breaks nothing a monitor would notice;
the first sign is a confused user. Treat custom forms as release artefacts,
like the blueprint itself: know which object the platform reads, keep it
intact in the pipeline, and make every release say which form it shipped.

## Rules learned

- VCF Automation 9.1's request page shows the released version's copy of the
  custom form. A form stored by source ID alone is not used, whatever the
  renderer returns.
- The classic blueprint's `formId` points at the form, and the designer's
  Create sets it. Set it before you create a version: the version copies the
  form as `<name>/<version>` with a `formId` of its own.
- A content update through the CCI blueprint API clears `formId`. Remember it
  and PUT it back on the classic record before versioning.
- Text element: a read-only layout field with `display: text`, plus a string
  schema entry whose `default` is the text. Pages are tabs.
- Put a pattern's failure text in `constraints.pattern.message`, or the user
  gets the regular expression.
- A custom form keeps its own copy of each field's choices and defaults.
  After changing an input, rebuild the forms and release once more.
- Make every release report which form each version got.

## Broadcom documentation

- [Creating Custom Forms for Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/learn-more-about-custom-forms-in-vcfa-for-all-apps.html): building a request form in the designer, and its import and export; each blueprint version is coupled with a form
- [Custom Form Designer Field Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/learn-more-about-custom-forms-in-vcfa-for-all-apps/custom-form-designer-field-properties-in-vcf-automation-for-all-apps.html): display types, defaults and value lists, and a regular expression with its own failure message
- [Versioning Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/blueprint-versioning.html): creating versions and releasing one to the catalog

*Companion to [one catalog item, two audiences](/posts/one-item-students-and-trainers/).*

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
