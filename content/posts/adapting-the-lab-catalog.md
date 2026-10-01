---
title: "Make it yours: a new site, a new release, a new lab"
date: 2026-12-02
draft: false
tags: [vcf, vcf-automation, blueprints, property-groups, nested-esxi, automation, air-gap]
products: ["VCF Automation"]
series: ["Nested Labs as Code"]
seriesPart: 6
tldr:
  - "Everything that ties our lab catalog to one platform sits in a single site file, checked offline by `site_check.py`."
  - "When the binaries server moved house, the catalog needed four values in one property group and no new blueprint version."
  - "Keep what changes often in property groups, and leave in the blueprint only what has to be there."
tested: "VCF 9.1"
cover:
  image: "/images/post39-hero-make-it-yours.svg"
  alt: "A site file filled in with the wizard passes site_check.py and is installed step by step by the install runner; afterwards a new release is a library item plus one entry in nestedLabMedia, and a new trainer is one line in nestedLabSite, with no new blueprint version"
  hidden: false
summary: "Everything that ties our lab catalog to a platform lives in one site file. What it holds, which changes need only a sync, and how new releases, sizes, address plans and dark sites fit in."
---

On 28 September we rebuilt the binaries server, the machine the labs fetch
their build scripts and appliance files from. It came back at a new address.
For the catalog, the move was four values in one
[property group](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups/constant-property-groups-in-vcf-automation-for-all-apps.html):

```text
nestedLabSite: 4 change(s)
  binariesUrl: 'http://172.31.0.34/binaries/' -> 'http://172.31.0.2/binaries/'
  nfs.host: '172.31.0.34' -> '172.31.0.2'
  scriptsUrl: 'http://172.31.0.34/binaries/scripts/' -> 'http://172.31.0.2/binaries/scripts/'
  toolsUrl: 'http://172.31.0.34/binaries/tools/' -> 'http://172.31.0.2/binaries/tools/'
  updated nestedLabSite (id 424a2fc4-f0b9-4c9e-b344-684b72f95493)
nestedLabMedia: up to date
```

No blueprint changed and no version was released. The next labs simply read
the new address. As house moves go, that one was painless.

[Post 5](/posts/inside-the-lab-blueprint/) opened up the blueprints. Making
them yours is mostly a matter of knowing where each change belongs:

| Change | Where | New blueprint version? |
|---|---|---|
| Platform values, addresses, trainers, the students' defaults | site file, then a property-group sync | no |
| A new ESXi, vCenter and VCF Operations release | library, binaries server, site file, sync | once, for the Release list |
| Host sizes | VM classes, then site file and sync | only for the size titles on the form |
| The lab's shape, the domain's accounts, the form's starting values | site file, then a release | yes |
| What a lab builds inside | build scripts on the binaries server | no |

## One file per platform

Each platform has one site file. Ours, `site-f06.yaml`, is 332 lines: 158 of
settings and 153 of comments that say why. That's nearly a line of comment for
every line of setting, because future me forgets things.

A new platform starts from `site-example-acme.yaml`, a template with every key
the tools read and made-up values for a platform called Acme. `SITE_FILE`
tells the generator and every tool which file to read.

`tools\site_check.py` reads that file without touching the platform. It does
four things with it:

- lists the values still to be filled in, each with its line and the install
  step that supplies it;
- compares the keys with the template;
- checks the values against each other;
- runs the generator for all eight blueprints and both property groups, so the
  generator's own rules apply too.

Then it prints the site at a glance. Here's ours, run while writing this:

```text
Site file   site-f06.yaml
Platform    VCF Automation https://f06-vcfa01.res.lab, organization dev-01; vCenter f06-m01-vc01.res.lab; NSX f06-m01-nsx01.res.lab (project dev-01); region f06, zone domain-c9
Catalog     lab-students: Phase 1, Phase 2, shared by students and trainers (trainers: none)
            default-project: Phase 3, Phase 4, Phase 5, Phase 6, and the jump and dc items
            8 items generate: lab-phase-1-dc-build, lab-phase-2-blank-hosts, ...
Students    6 VPCs: vpc-student01, vpc-student02, vpc-student03 .. vpc-student06; one lab per VPC at a time
...
Sizes       hosts small by default (8 vCPU / 32 GiB each); vCenter small; VCF Operations small
Releases    vcf-9.1.0 (default): VCF 9.1.0 - ESXi 9.1.0.0200, vCenter 9.1.0.0200, VCF Operations 9.1.0.0400
Binaries    http://172.31.0.2/binaries/ (admin 192.168.144.10)
Groups      property groups nestedLabSite and nestedLabMedia

Notes:
  - trainers is empty: on the items shared with the students, no one can build a lab for a student

site file OK
```

That block is the quickest review there is with whoever supplied the values.
The note is expected: f06 has no trainers at the moment.

## Data, not versions

Both property groups are generated from the site file and pushed with
`sync_propgroups.py`. It compares before it writes, so a value someone
changed in the UI shows up before it's overwritten.

On f06, `nestedLabSite` holds 74 values: the platform, the sizes, every lab
address, the trainers and the students' defaults. `nestedLabMedia` holds 13,
the releases. Labs read them when they're requested, so a change needs a sync
and nothing more.

Adding a trainer is one name in the site file's `trainers` list
(`trainers: [trainer01]` in the template), then a sync.
[Post 4](/posts/six-phases-one-catalog/) shows what that list changes for a
student and a trainer. Moving the students to another release is
`defaultRelease` and a sync.

A new blueprint version is needed only for what the blueprints carry
themselves. That's the lab's shape, the domain's accounts, the form's starting
values and the Release list, because an input's list of choices can't hold an
expression.

## A new software release

A release is a set of builds that belong together, named once and picked on
the form. The generator writes it into `nestedLabMedia` in the shape the
blueprints read:

```json
    "properties": {
      "defaultRelease": {
        "type": "string",
        "const": "vcf-9.1.0"
      },
      "releases": {
        "type": "object",
        "const": {
          "vcf-9.1.0": {
            "title": "VCF 9.1.0 - ESXi 9.1.0.0200, vCenter 9.1.0.0200, VCF Operations 9.1.0.0400",
            "esxAppliance": "vmi-06c9d169cecd2eb9d",
            "esxApplianceGuestId": "vmkernel8Guest",
            "esxApplianceBaseGi": 44,
            "esxBlank": "vmi-9feae8e2deca8e3ab",
            "esxBlankGuestId": "vmkernel9Guest",
            "esxIso": "vmi-e400a813bbd5d52a5",
            "vcsaIso": "vmi-35b64cde89930b706",
            "vcsaFolder": "vcenter/9.1.0.0200-25573614/ovf/",
            "vcsaSparseFolder": "vcenter/9.1.0.0200-25573614/sparse/",
            "opsFolder": "ops/9.1.0.0400-25541561/ovf/",
            "opsSparseFolder": "ops/9.1.0.0400-25541561/sparse/"
          }
        }
      }
    },
```

A second release takes four moves:

1. Put its nested ESXi appliance and the ESXi and vCenter Server Appliance
   (VCSA) ISOs into the
   [content library](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/creating-and-managing-content-libraries-for-stand-alone-vms-in-iaas-platform.html).
2. Put its vCenter and VCF Operations appliances on the binaries server, where
   `rebuild-binaries.py add-vcenter` and `add-ops` file each build in a folder
   of its own.
3. Add an entry beside `vcf-9.1.0` in the site file, and sync.
4. Release, apply the forms again and release once more, so the Release list
   offers it.

Nothing is overwritten. Running labs keep their release, and students move
only when `defaultRelease` does. Build one Phase 4 lab on a new release before
a class relies on it.

## Sizes

The nested hosts come in Small, Medium and Large. Each is a
[VM class](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/working-with-vm-classes-in-vsphere-with-tanzu.html)
with nested hardware virtualisation, plus the vCPUs and memory the namespace
limits count. From the template:

```yaml
# VM classes with nested hardware virtualization (configSpec nestedHVEnabled: true); cpu / memMi as in the class
hostSizes:
  small:  {vmClass: nested-esx-small,  cpu: 8,  memMi: 32768}     # Phases 1-3 only: too small to run the vCenter
  medium: {vmClass: nested-esx-medium, cpu: 16, memMi: 65536}     # the default for Phases 4-6
  large:  {vmClass: nested-esx-large,  cpu: 32, memMi: 131072}
```

Resizing one takes two changes. First the class in vCenter, with
`vmclass_api.py update <class> <vCPUs> <MiB>`. Then the same numbers in
`hostSizes`, and a sync. A changed class applies to new VMs only, so running
labs keep their size.

When we resized all three on 28 September, the sync carried nine values. The
next release updated the size titles on the form, which are text.

The vCenter appliance comes in Small or Medium: Tiny lived down to its name
and starved inside a nested host. VCF Operations comes in Extra small, Small
or Medium. The site file sets where each form starts.

## The IP plan

Every lab uses the same addresses inside its own VPC. The plan lives in
`lab.network`. Here's the template's, for its made-up platform:

```yaml
  network:                    # the same inside every lab; one lab per VPC
    mask: 255.255.255.224
    mgmt:    {cidr: 10.50.0.32/27, gateway: 10.50.0.33, vlan: 2610}
    vmotion: {cidr: 10.50.0.64/27, gateway: 10.50.0.65, vlan: 2611}
    vsan:    {cidr: 10.50.0.96/27, gateway: 10.50.0.97, vlan: 2612}
    jumpIp: 10.50.0.34        # the jump host when it is also the DC (the 'jump' dev item)
    dcIp: 10.50.0.34
    dcJumpIp: 10.50.0.35
    vcenterIp: 10.50.0.50
    opsIp: 10.50.0.51
    firstHostIp: 40
    firstVmotionIp: 70
    firstVsanIp: 100
```

The generator derives the rest, down to each host's three addresses and the
reverse zone. The check keeps it consistent:

- every subnet inside the VPC range;
- each gateway inside its subnet;
- the fixed addresses inside the management subnet, and clear of the hosts;
- three different VLANs.

Ours is the same shape on 172.30.0.x, and
[post 3](/posts/lab-network-no-router/) explains why it needs no router. Any
plan the check accepts will do, as long as no server the labs must reach (a
DNS forwarder, say, or the binaries server) sits inside it.

## Another platform

[Post 1](/posts/nested-labs-as-code/) argued that code pays off when labs move
to another platform. The route is short: copy the template, check it,
generate, install. It follows our implementation guide's eleven steps, with
`SITE_FILE` pointing at the new file.

Where Python can't run on the day, `tools\export_catalog.py` writes the
by-hand route's files from the same site file:

- both property groups, as the JSON bodies the API takes;
- one blueprint per item, in a folder named after its project;
- a README saying which goes where.

## Dark sites

A platform without internet takes everything as files. The
[GPU Operator post](/posts/vks-gpu-operator-dark-site/) shows what that means
for vSphere Kubernetes Service (VKS). For the catalog, the rule that matters
comes after the kit ships. Once someone is copying it, it's frozen. Changes
travel in an update folder beside it, which holds only new and changed files,
under the same paths.

Its manifest carries each file's SHA-256. For a file that replaces one in the
kit, it also carries the SHA-256 of the version it replaces:

```json
  {
   "path": "6-lab-catalog/guides/gen_lab_blueprint.py",
   "size": 116779,
   "sha256": "3998745c02c9433cc9cca151c1e33d94566e4094c1f8e539717dd5549c3049b0",
   "replaces": "ec18467a0198999affe5972952a8a8cc499f24c6102331480ed6e2f642fa1f66"
  },
  ...
  {
   "path": "6-lab-catalog/guides/tools/export_catalog.py",
   "size": 4913,
   "sha256": "a468ec5b55f08b001acdcd55185ed1e8eaa977568d30c4a1bff12b6615d7cf47",
   "replaces": null
  },
```

The receiving side can prove that a file arrived intact, and that it lands on
the version it was built against. The builder also refuses a changed file
without a one-line reason, which goes into the update's README. It's stricter
with me than I would be.

## Extending the lab

The generator has no plug-in interface. A new phase is a code change, in
places the existing phases already show. The modes are named in one list, and
what a mode does comes from the sets it belongs to:

```python
VC_MODES = ("vcenter", "ops", "full")
...
OPS_MODES = ("ops", "full")
...
BLANK_MODES = ("build", "builddc")      # the hosts arrive blank and the class installs ESXi
```

A new VM or appliance can join a lab in two ways. If the blueprint creates it,
like `dc01`, it gets a resource template in the generator, a size in
`nestedLabSite` and a term in the namespace limits.

If the lab deploys it into its nested cluster, like VCF Operations, it gets:

- a block in the jump host's `lab-config.json`;
- a script on the binaries server;
- a step in the vCenter build that runs the script when the block is there.

The VCF Operations step is the whole pattern:

```powershell
if ($labCfg.ops) {
    $opsScript = Join-Path (Split-Path $log) ($labCfg.ops.script)
    if (-not (Test-Path $opsScript)) {
        & (Join-Path (Split-Path $log) 'Get-LabFile.ps1') -Url ($scriptsUrl + $labCfg.ops.script) -OutFile $opsScript -TimeoutSec 120
    }
    Say "handing over to $($labCfg.ops.script) - progress in ops-build.log"
    & $opsScript
}
```

Then the marker goes on the lab page and into the status tool, and the mode
gets a title and a catalog name. The phase number goes into the tools that
know phases by number: release, forms, export, check and status. The lint
makes the new pieces read the property groups like everything else.

## Two tools for the first install

Two tools make the first install easier still.

The site-file wizard is a single HTML page that works offline: no server, no
network, nothing to install. It's generated from the template, so it knows
every key the tools read, with the template's comments as help text.

It builds a site file from scratch or completes a half-filled one. It shows
each value still to come with the install step that fills it, and downloads
the finished file. Here it has a copy of the template open, with three
endpoints still to come:

![The site-file wizard with a half-filled site file: the Endpoints section filtered to its three values still to come, each with the install step that fills it](/images/ui/wizard-values-to-come.png)

Its Survey tab prints the same answers by section, with what's still to come
at the top. It's the page to go through with whoever supplies the values.

![The wizard's survey view: the three values still to come with their line, key and step, then every setting by section with its status](/images/ui/wizard-survey.png)

`site_check.py` stays the gate. Here it is on the file the wizard wrote:

```text
Platform    VCF Automation https://TBC-vcfa.fqdn, organization acme-training; vCenter TBC-vcenter.fqdn; NSX TBC-nsx.fqdn (project acme-training); region acme-dc1, zone domain-c9
Catalog     lab-students: Phase 1, Phase 2, shared by students and trainers (trainers: trainer01)
...
Still TBC (3) - fill in at the step named:
  line  38  endpoints.vcfa                     https://TBC-vcfa.fqdn                        step 2
  line  43  endpoints.vcenter                  TBC-vcenter.fqdn                             step 2
  line  45  endpoints.nsx                      TBC-nsx.fqdn                                 step 2

site file OK - 3 value(s) still TBC
```

The page and the check agree on what's left, line for line. The wizard's own
tests hold it to that on every build.

The install runner, `tools\install_runner.py`, runs the implementation guide's
scripted steps in order from the admin workstation. It records each one, so a
second run carries on where the first stopped. When a step runs on another
machine or in a browser, the runner hands it to the operator, with the section
of the guide to follow.

Its first run on f06 started at step 2.1, and stopped at the first step it
handed over:

```text
Site file   X:\VCFA Workflows\Export\guides\site-f06.yaml   (sha256 460cba78a1b84a88)
  vcfa            https://f06-vcfa01.res.lab
...
Carry on with this site file and these addresses? [y/N] y

====================================================================================================
2.1  What is still TBC in the site file   [W] check   (Step 2 - Site file)
====================================================================================================
> python tools\site_check.py
Site file   X:\VCFA Workflows\Export\guides\site-f06.yaml
...
site file OK
2.1: done   (log logs\install\2.1-20261001-014455.log)

====================================================================================================
2.2  Fill in the step-2 values   [W] manual   (Step 2 - Site file)
====================================================================================================
  In site-f06.yaml: the endpoints vcfa, vcenter, esxHost, nsx and supervisor; lab.upstreamDns (one or more DNS
...
  Guide: Step 2 - Site file
  [d]one, [s]kip, [q] stop, [o]pen the site file: q
stopped - the step stays pending
```

Anticlimactic, which is exactly what you want from an installer. With step 1
recorded as done by hand (`--mark`), a plain second run went straight back to
2.2. And `--plan` shows where the install stands:

```text
  id        title                                                        where kind    status           when
  --------- ------------------------------------------------------------ ----- ------- ---------------- ------------
  1.1       Check the copy against every manifest                        W     run     done (marked)    01 Oct 01:45
  ...
  2.1       What is still TBC in the site file                           W     check   done             01 Oct 01:45
> 2.2       Fill in the step-2 values                                    W     manual  pending
  2.C       Check: the whole file, the platform addresses, the values... W     check   pending
```

We tested the runner with dry runs over the whole install, and real runs of
the steps that only read. The implementation guide stays the reference.

## Why this matters outside the lab

Any catalog that must exist in more than one place meets the same question.
The other place might be a second region, a disconnected site or a partner's platform.
Which part is the design, and which is the place?

Keep the place in one checked file and the design in generated code. Then a
new site is a data exercise with a known list of steps. And a new release, a
resized class or a moved server becomes an afternoon's routine.

## Rules learned

- One site file per platform, plus a template that names every key.
- Check the site file offline first, and name the line and the step in every
  message.
- Keep what changes often in property groups. Leave in the blueprint only what
  has to be there.
- Name releases as sets, and look up every image and folder through the set.
- Ship updates to a frozen kit as a delta, with each file's hash and the hash
  it replaces.
- Extend along the patterns the code already has, and let the lint check the
  new pieces.

## Broadcom documentation

- [Constant Property Groups in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups/constant-property-groups-in-vcf-automation-for-all-apps.html): fixed values that become part of each deployment
- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): input and constant property groups, maintained in one place
- [Working with VM Classes in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/working-with-vm-classes-in-vsphere-with-tanzu.html): what a VM class defines and how namespaces get it
- [Edit a VM Class Using the vSphere Client](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/working-with-vm-classes-in-vsphere-with-tanzu/edit-or-delete-a-vm-class-in-vsphere-with-tanzu.html): changing a class; deployed VMs keep theirs
- [Creating and Managing Content Libraries for Stand-Alone VMs in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/creating-and-managing-content-libraries-for-stand-alone-vms-in-iaas-platform.html): the libraries that hold a release's images
- [Importing or Exporting Blueprints in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/import-or-export-a-stateful-blueprint-in-vcf-automation.html): moving blueprints between organizations as YAML or a zip

---
*Lab environment; opinions my own. Everything above was captured from a live VCF 9.1 environment - output trimmed for length, never edited for outcome.*
