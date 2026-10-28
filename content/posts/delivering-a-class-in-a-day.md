---
title: "Delivering a class in a day"
date: 2026-11-18
draft: false
tags: [vcf, vcf-automation, nested-labs, training, dark-site, delivery]
products: ["VCF Automation", "VCF"]
series: ["Lab Builder"]
seriesPart: 3
tldr:
  - "Delivery starts with a site survey that fills in one site file, and everything after it is generated from that file."
  - "The kit is one zip with its own runtime, so an air-gapped workstation installs the catalog with nothing downloaded."
  - "The install is a numbered runbook the tool can run for you, and the day ends with a class check rather than a hopeful handshake."
tested: "VCF 9.1"
cover:
  image: "/images/lab-builder-validate.jpg"
  alt: "Lab Builder's Validate step: the class's student and trainer counts, the lab VPCs' security profile, a Run the checks button, and five counters reading 7 pass, 4 to build, 1 warn, 0 fail, 0 skipped"
  hidden: false
summary: "How a classroom actually gets delivered at an air-gapped site: a survey that becomes a site file, a kit that carries its own runtime, a numbered install, and a check at the end that proves a student can request a lab."
---

The first two posts in this series covered what [Lab Builder]({{< ref "/posts/introducing-lab-builder-for-vcf" >}})
is and [what a student gets]({{< ref "/posts/a-vcf-lab-each" >}}).
This one is the delivery: what we actually do, in what order, at a site with no
internet and a finite amount of goodwill.

## It starts with a survey, not a shipment

Before anything is built we fill in a site survey. Not a formality: it is the
list of things that will stop the install dead if they are wrong.

The organization and projects. The region and the zone. The network plan for a
lab, which VLANs carry it, and the address blocks it may use. Which VCF media
the site has, and which build. The students' accounts and the trainers' group in the site's own directory. DNS
names, and who can create them.

The answers become one file, `site-<name>.yaml`. From then on, that file is the
site. The blueprints read it, the documents are rendered from it, the diagrams
are drawn from it, and the install runs against it.

A survey answered properly takes an afternoon. A survey answered optimistically
takes an afternoon as well, and then a day on site to find out which answers
were aspirational.

## Check the file before you travel

The site file is checked offline, long before anyone is on site. A check names
every value still unanswered, and the blueprints can be validated against VCF
Automation without saving anything.

This matters more than it sounds. Install day at a dark site is a fixed window
with a room booked, and the failures you want are the ones you had at your desk
three weeks earlier.

## The kit

The kit is one folder, and it unpacks from one zip.

It carries its own Python and PowerShell, so nothing is installed on the
workstation and nothing is fetched during the install. Beside the tooling it
carries the documentation set, the packages that make up the catalog, and a
checklist of the VCF media the site must supply. The media stay out of the kit,
because a kit you can email beats a kit you must ship.

Every file in it is listed in a manifest with its size and SHA-256, so a
half-copied kit is caught by a check rather than by a strange error two hours
in.

## Install day

The install is a numbered runbook. A human can follow it, and the tool can run
the same steps itself with a button per check, which is what usually happens. The
steps below are this example's; a site whose catalog holds something else gets the
same shape with its own contents.

![Lab Builder part way through an install: a list of the components it is installing, each with its type and the runbook steps it marks done, and a banner saying which one is running now](/images/lab-builder-install-step.jpg)
*Part way through, from an install we recorded end to end into a brand-new organization. Every component says what it is and which runbook steps it satisfies, and the banner says what is running now.*

1. Lay the kit on the workstation and check it.
2. Connect to VCF Automation, vCenter and NSX, read-only first, and report what
   it found.
3. Create the organization, the projects, the VPCs and the networking.
4. Upload the images and build the content library.
5. Stand up the binaries server that serves the installers inside the lab.
6. Install the catalog packages and release the items.
7. Put the trainers' group and the students' accounts in place.
8. Build one real lab, end to end, as a student would.

Step 8 is the one that counts. Everything before it is plumbing, and plumbing
reports success with enthusiasm it has not always earned. A lab that actually
builds is the only evidence worth having.

Here is the whole install, start to finish, on a brand-new organization:

{{< video src="/images/lab-catalog-packages-install.mp4" poster="/images/lab-catalog-packages-install-poster.jpg" ratio="1440 / 992" narrated="true" captions="/images/lab-catalog-packages-install.vtt" caption="Connect, Discover, Packages, Choose, Validate, Plan, then one Install, and the organization in VCF Automation's own portal at the end. Narrated: press play for sound, CC for subtitles." >}}

## What the install leaves in VCF Automation

Nothing it builds is a special Lab Builder object. When the install finishes, the
site has an ordinary VCF Automation organization: a catalog of released items, a
content library of images, projects, and a VPC for each student. A trainer who never
opens Lab Builder again still has all of it.

![VCF Automation's own Catalog page in the new organization, showing the lab phase items as cards with the project each is released into, nine items in all](/images/lab-builder-vcfa-catalog.jpg)
*The catalog in VCF Automation's own portal, in an organization that was empty an hour earlier. Each item is released into the project that should see it: the student phases to the students' project, the rest to the trainers'.*

![VCF Automation's Virtual Private Clouds page listing the organization's VPCs: the default one, a shared services VPC, and one named for each student, each with its transit gateway, private CIDR and a Success status](/images/lab-builder-vcfa-vpcs.jpg)
*The networking the same install made: a VPC per student, named in the site file, beside the shared-services VPC the binaries server lives in.*

The images came with the kit and were uploaded during the install, and the server the
labs read their installers from is itself a deployment, requested by the
organization's own service account.

![VCF Automation's Content Libraries page in the new organization, listing one library named nested-lab with a Ready status, its region and its version](/images/lab-builder-vcfa-library.jpg)
*The content library the install filled, with the lab images inside it. The kit carried them; nothing was downloaded.*

![VCF Automation's Instances page listing one deployment named binaries, from the shared-binaries-server catalog item, requested by the organization's service account an hour earlier](/images/lab-builder-vcfa-instance.jpg)
*And the binaries server, deployed from the catalog like anything else. An hour old at this point, and the only thing the labs need to reach while they build.*

## Handing the labs out

On the morning itself students request their own labs from the catalog, which is
rather the point. A trainer can also request one for any student from the same page
they watch the class on: pick the student, pick the phase, review what is about to
be sent, submit. Either way the request is made as that student, so the lab is
theirs from the first second.

Labs go out one at a time, with a gap between them, so each student's network has a
moment to settle. A trainer who wants the room ready starts the labs before the
lesson and walks away: the page does the watching, and hands out a Remote Desktop
file for each lab as it comes ready.

![VCF Automation's Instances page listing three deployments - student02-p1, student01-p1 and the binaries server - with student01-p1 open beside them showing its owner student01, the students' project and a Create Successful status](/images/lab-builder-vcfa-instances.jpg)
*The same labs in VCF Automation's own portal: one deployment per student, each owned by the student who asked for it, beside the binaries server they all read from.*

![The trainer page's student networks table: a summary reading twelve networks, five labs, one lab server and seven free, then a row per student with the phase requested, the status, the age of the lab and its Remote Desktop address](/images/lab-builder-class-rows.jpg)
*A class part way through, with example values: one lab finished and addressable, one twelve minutes into its build, one flagged to look at.*

## Ending the day

Delivery ends with a check, not a handshake.

A class check asks the platform what a trainer would want to know: do the
students exist, can they see the catalog, is each student's network ready, and
did a lab build. It prints a line per student. When those lines are all good,
the room is a classroom.

Then the trainers get the runbook written for them, and the students get theirs.
Both came out of the same site file as the labs, so the addresses in the
pictures are the addresses in the room.

## Why this matters outside the lab

Nothing in this delivery is specific to teaching.

A survey that becomes a machine-readable file. A kit that carries its own
runtime. An install that is a numbered runbook a tool can run. A check at the end
that exercises the thing a real user does. That is a shape for any delivery into
somewhere you cannot reach from your desk. The classroom just makes the last step
easy to name, because a lab either builds or it does not.

## Rules learned

- Put the survey before the shipment. Most install-day failures are survey
  answers nobody checked.
- Check the site file offline, weeks early. A dark site is a bad place to
  discover a missing DNS record.
- Keep the media out of the kit and in a checklist. The tooling is small; the
  ISOs are not.
- Finish by building a real lab as a student. Every other check can pass while
  the thing a student does still fails.
- Hand over a check, not a promise. A trainer needs a command that says the
  class is ready, on a morning when we are not there.

## Broadcom documentation

- [VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/vcf-automation.html): the platform the catalog is installed into.
- [Content Libraries](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/vsphere/9-0/vsphere-virtual-machine-administration/using-content-libraries.html): where the lab images live.
- [VPCs in VCF](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/advanced-network-management/vpcs.html): the networking created during the install.

---
*Lab environment; opinions my own. Lab Builder for VCF is our own tooling, not a
Broadcom product. VMware, VCF and VCF Automation are trademarks of Broadcom Inc.
or its subsidiaries.*
