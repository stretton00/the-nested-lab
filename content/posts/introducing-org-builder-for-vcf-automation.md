---
title: "Introducing Org Builder for VCF Automation"
date: 2026-10-05
draft: false
tags: [vcf, vcf-automation, blueprints, automation, air-gap, nested-esxi, nsx]
products: ["VCF Automation", "NSX"]
series: ["Org Builder for VCF Automation"]
seriesPart: 1
tldr:
  - "We build complete VCF Automation catalog services in our lab. Getting one into someone else's organization used to mean rebuilding it by hand across three portals: 11 steps, about three working days, 8 h 30 of typing."
  - "Org Builder is a web page on an administrator's workstation that reads the platform, writes one site file, previews every change and then builds the organization through the APIs. Nobody types a password into it."
  - "It records every object as made or found, so an uninstall takes back only what it made. The next two posts show it on film: one install from nothing, and one organization exported and imported in 53 minutes."
tested: "VCF 9.1"
cover:
  image: "/images/post43-hero-org-builder.svg"
  alt: "Three portals on the left, VCF Automation, vCenter and NSX, each with a long list of pages to click through; on the right one web page, Org Builder, with its stages Connect, Discover, Choose, Validate, Plan and Install, reading a site file and talking to all three by API"
  hidden: false
summary: "What Org Builder for VCF Automation is and why we built it: the problem of rebuilding a lab-built catalog by hand in another organization, and the tool that reads the platform, writes a site file, previews and builds instead. A walk through its stages in screenshots."
---

In our lab we build complete VCF Automation catalog services. Not a blueprint
that works once, but the whole thing: images, networks, projects, property
groups, request forms and the catalog items that tie them together, tested as
the people who'll use them. This blog has a few:
[seven demo apps from one request](/posts/demo-apps-via-vcfa/),
[a Kubernetes cluster two ways](/posts/vks-kubectl-vs-vcfa-all-apps/) and
[a lab factory that builds whole VCF instances](/posts/one-catalog-item-one-vcf-instance/).
The nested VCF labs for training classes have a series of their own,
[Nested Labs as Code](/series/nested-labs-as-code/).

Then someone else wants one. A customer, a partner, a colleague with a
platform of their own, in an organization of their own. That moment is what
this post, and this short series, is about.

## The problem: three portals and a lot of typing

A catalog service that works in dev-01, our lab organization, is not a file
you can hand over. It's spread across three portals. In VCF Automation there
are projects, the content library, property groups, blueprints, their request
forms and the catalog items released into the right project.

In vCenter there are the images, each uploaded into a library and then known
by a new id. In NSX there are the VPCs, their profiles and the networking the
labs run in. A binaries server sits in the middle, holding the installers the
labs download.

Rebuilding that by hand means walking through all three, in the right order,
copying values from one page into the next. Our own implementation guide for
the nested lab catalog budgets 11 steps, about three working days of elapsed
time and 8 hours 30 minutes of hands-on work for one site. Every value typed
is a chance to be wrong. An image id is seventeen hexadecimal characters, and
the site file holds five of them.

Nothing in that walk is difficult. It's the length of it, and the number of
places where one wrong character means the lab doesn't build until someone
finds it, usually the next morning. We wanted the walk done by something
that doesn't get bored.

## What Org Builder is

Org Builder for VCF Automation is a web page that runs on an administrator's
workstation. Nothing is installed on the platform. The page talks to VCF
Automation, vCenter and NSX through their APIs, the same ones the portals use,
so what it builds is exactly what you'd have clicked together, minus the
clicking.

A few things it always does:

- **It reads before it writes.** Discover looks at the platform first:
  hosts, storage, images, networks, what the organization already holds.
- **It shows the plan before it acts.** Validate and Plan change nothing;
  Install shows what each component will do, and asks before anything is
  removed.
- **Nobody types a password into it.** Sign-ins live in files on the
  workstation, the same files the command-line tools use.
- **It records every object as made or found.** What it found, it leaves
  alone; an uninstall takes back only what it made.

Its unit of work is the **site file**: one file holding one site's own
values, from the platform's addresses to the names of the student projects.
What to build comes from **packages**: a package says what, the site file
says where. The same packages have built a throwaway test organization, four
trial copies of our lab organization and the brand-new one in the next post's
film.

It has two jobs. **Install** builds an organization from the kit. **Move**
exports an organization into a bundle and imports it somewhere else. The
rest of this post walks through Install in screenshots, with Move at the
end.

## Connect

![Org Builder's Connect stage: the workstation's sign-ins picked, the site file site-f06.yaml, the new organization acme named with its client ID and token prefix, and three cards reading Signed in for VCF Automation, vCenter and NSX Manager](/images/org-builder-connect.jpg)
*Connect: the platform's addresses come from a site file, the tokens and passwords from this workstation's own files. Three systems, three green Signed in badges, no password field.*

The page signs in to an organization, so the organization has to exist. In
the film it was made a few minutes earlier by one command, empty apart from
its quota, its networking and a first administrator. Everything else is
built from here.

## Discover

![Discover: 10 of 12 reads done in 7 seconds, and a grid of tiles: VCF Automation acme with 1 project and 0 catalog items, Supervisor running, host memory 209 GiB free, vSAN 54 percent used, 2028 external IPs free, NSX with 1 VPC, 0 images, 5 nested VM classes, binaries server not yet, DNS resolving 5 names](/images/org-builder-discover.jpg)
*Discover only reads. Seven seconds later: a working platform, and an organization with nothing in it yet.*

Discover is the part a person usually skips, which is why it exists. It
reads the platform once and keeps the answers for every later stage, so a
pick-list offers what's really there and a check knows what's really free.

## Packages

![Packages: where the packages folder and the media bundle are, and the foundation package's card: version 1.2.0, not installed, with Plan, Carry on and Uninstall buttons and an Install until setting of the end, every component](/images/org-builder-packages.jpg)
*Packages: three of them, each a card. The foundation sets the organization up inside; the binaries server and the catalog follow, in that order, from one Install.*

The kit's big files, installer ISOs and appliance images, travel apart from
the packages as a media bundle, every file named by its SHA-256. The page
reads the bundle's manifest and checks the files are the ones the packages
expect.

## Choose

![Choose, the platform group: region f06, zone domain-c9, namespace class nested-lab, storage policy and storage class, each a pick-list with a found badge, and the vCenter address with a follows badge](/images/org-builder-choose.jpg)
*Choose fills in the new site file. Everything the platform already has is a pick-list of what Discover found, marked found, so there's nothing to mistype.*

![Choose, the images group: the Windows Server template set to a copy of W2025v6 from vCenter library nested-lab, marked built in step 6.7, with the lab addressing fields below following the VPC range](/images/org-builder-choose-images.jpg)
*The Windows template is a copy of our own, from another library inside vCenter. Nothing is uploaded, and the new image id goes into the site file by itself.*

A new site starts from the template; a site that already has a file starts
from that. The organization, its client ID and its token files come straight
from the sign-in. The checks run again after every choice, so a bad pick is
caught at the pick, not at the install.

## Validate

![Validate: the results list, each with a pass or to build badge and the runbook steps that build it: the content libraries hold every image the site file names, the binaries server answers, the external IP block has room for every lab VPC, every vSAN disk has room, VM classes with nested virtualisation exist](/images/org-builder-validate.jpg)
*Validate: pass, or to build. What isn't there yet, the install makes; a real failure comes first, with the runbook step that fixes it.*

## Plan

![Plan: the new site file named site-acme.yaml beside the guides, and a diff against the template with the chosen values set in place and the template's comments kept](/images/org-builder-plan.jpg)
*Plan writes the new site file, and shows it as a diff against the template first. The comments survive, so the file still explains itself to the next person.*

![Plan, after Write: a What comes next card listing the commands in order: point the guide's tools at the new file, run the install inside the organization, upload the images, discover and choose again, tell the runner what is done](/images/org-builder-plan-next.jpg)
*After Write, the page says what comes next, with the commands. A console could carry on from here; so could the page.*

## Install

![Packages after Install: the foundation's components listed with their runbook steps and an installed badge each, workstation, site file, storage, VM classes, and below them the install job's panel running the nested lab catalog up to its last item](/images/org-builder-install.jpg)
*One Install walks the foundation, the binaries server and the catalog. Each component says how it went in: by the installer, by part of it, or by the runbook's own steps.*

Some steps are still a person's: a profile ID that only the platform team
knows, a directory that may or may not exist, a DNS domain the template
can't guess. The install stops at each, asks on the page, and waits. Done,
Skip or an answer, and the walk goes on. Everything it did is in the record,
so a stopped install carries on from where it stopped rather than from the
top.

The install in the next post's film took about an hour and a half of real
time, most of it waiting for files to move. The 12 GB vCenter installer ISO
alone took 23 minutes to upload, and then VCF Automation spent another 16
minutes copying it into vCenter. The page reported that as a plain
not-ready at the time, which caused a certain amount of staring at a
progress bar that wasn't there. It now says what's happening.

![acme's own VCF Automation portal afterwards: the Catalog page with the six lab-phase tiles, each released into lab-students or default-project, and 9 items in the corner](/images/org-builder-result-catalog.jpg)
*And afterwards, in VCF Automation itself: acme's catalog, nine items, released into its two projects. Nobody clicked inside this portal to get here.*

## Move: the same idea, backwards and forwards

The second job takes an organization that works and moves it. Export reads
the source organization and writes a bundle: a folder of content, with no
passwords and no image files. Import opens the bundle with the destination's
own site file, asks about the handful of values that are the lab's rather
than the catalog's, previews everything, and builds.

![Export: the organization to export, dev-01, and what goes into the bundle: 59 items, among them 1 organization, 2 projects, 4 namespace classes, 8 VPCs, 5 VPC security profiles, 1 content library, the identity source and 3 groups, 8 images, 2 property groups, 9 blueprints, 6 request forms, 9 catalog items and 1 binaries server](/images/org-builder-export.jpg)
*Export: 59 things make up our lab organization. Discover found them and their dependencies; nothing was listed by hand.*

![Import, the images step: 8 images totalling 58.1 GiB, each set to copy from dev-01's library inside vCenter, no upload, with one button to set them all](/images/org-builder-import-images.jpg)
*Import: the eight images, 58.1 GiB of them, copied inside vCenter from the source library. Nothing crosses the wire twice.*

![Import finished: Imported 57 of 57 done, with three green bars, organization setup 21 of 21, binaries server 11 of 11, catalog 25 of 25, and the job line reading finished after 53 min](/images/org-builder-import-done.jpg)
*Fifty-seven of fifty-seven, in 53 minutes. The organization, its binaries server and its catalog, where before there was nothing.*

These three screenshots are from an earlier recording, when the tool was
still called the Lab Catalog Installer. It outgrew the name on 5 October,
so I've cropped the old header off rather than pretend it never existed.

## What it is not

It's our lab tooling, not a Broadcom product. It's proven on VCF 9.1, in our
lab and in rehearsals of a real install, and the next two posts are the
evidence. Some things are still being proven: catalog icons set through the
API, a full Phase 6 lab built under packages, sign-in through OpenID Connect,
and a production signing key for the packages. Each has its own line in the
next post, and will keep it until it's done.

## What's next

The next post, *One command for a whole lab catalog*, shows one whole install
on film: a brand-new organization built from the kit in one sitting, Connect
to Install. The questions it asked are in it, and so is the clock. The one after
shows an organization exported and imported, 59 resources in 53 minutes,
also on film. Both are narrated, so you can watch them with the sound on and
a cup of tea.

## Why this matters outside the lab

Anyone who runs a VCF Automation platform for more than one team has this
problem in some form. A catalog built in a development organization has to
reach a production one. A service built for one customer has to reach the
next. A training catalog has to reach the classroom. Today that's a runbook
and a careful person, and the careful person is the bottleneck.

What the pattern enables, once the walk is a tool rather than a document:

- **Reproducible organizations.** The same packages and a different site file
  give the same organization on another platform, with the differences in
  one place.
- **An honest uninstall.** Because every object is recorded as made or found,
  a trial can be taken down again without taking the platform's own things
  with it.
- **Handover without a hand.** A partner or a customer can install from the
  kit with the page in front of them, and the record shows what was done.

## Rules learned

- Read the platform before writing to it; a pick-list of what exists beats a
  text box every time.
- One file for one site's values. If a value isn't in the site file, the
  tool asks for it; it never invents one.
- Record made or found for every object, before the work, so an uninstall
  and a retry both know the truth.
- Preview is not optional. Every stage that changes nothing earns the one
  that does.
- Never type a password into a page. Files on the workstation, read by the
  tools, and nothing on screen.

## Broadcom documentation

- [Reusing a Group of Properties in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/managing-blueprints-in-vcf-automation/property-groups.html): property groups shared with the organization or kept to one project
- [Publish a Blueprint to the Catalog in VCF Automation](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-9-0-and-later/9-1/organization-management/setting-up-the-content-hub-in-vcf-automation-for-all-apps-organizations/publishing-content-to-the-vcf-automation-catalog/publish-vcf-automation-blueprints-to-the-catalog.html): releasing a version, by default to the members of the blueprint's project
- [Creating and Managing Content Libraries for Stand-Alone VMs in vSphere Supervisor](https://techdocs.broadcom.com/us/en/vmware-cis/vcf/vcf-service-administration-and-development/9-1/provision-and-manage-virtual-machines/deploying-and-managing-virtual-machines-in-vsphere-iaas-control-plane/creating-and-managing-content-libraries-for-stand-alone-vms-in-iaas-platform.html): the libraries that hold a release's images

---
*Lab environment; opinions my own. The screenshots are from live sessions on
our VCF 9.1 platform, recorded by a script that drove the page and captured
what it showed; nothing in them was edited apart from cropping.*
