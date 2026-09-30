---
title: "VCF Operations forgot our AD users two minutes after the build"
date: 2026-12-30
draft: false
tags: [vcf, vcf-operations, active-directory, ldap, rbac, troubleshooting, homelab]
series: ["Observability on VCF"]
cover:
  image: "/images/post30-hero-ops-ad.svg"
  alt: "An AD group imported into VCF Operations by its short name becomes a new, unlinked group that the group sync empties; imported by its distinguished name, the sync fills it from AD"
  hidden: false
summary: "The lab build signed alice in to VCF Operations as its last check, and passed. Five minutes later she was refused. Two wrong turns, a workaround I didn't like, and the one field in the API reference that explained it: AD groups are imported by distinguished name."
---

The last thing our Phase 6 lab build does is prove that the lab's Active
Directory users can sign in to VCF Operations. On the overnight test lab it
did exactly that:

```text
03:50:00  AD sign-in: group gg_vcf_ops_administrators imported as Administrator
03:50:01  AD sign-in: group gg_vcf_ops_operators imported as PowerUser
03:50:02  AD sign-in: group gg_vcf_ops_readonly imported as ReadOnly
03:50:05  AD sign-in: group gg_vcf_ops_administrators has 2 member(s)
03:50:05  AD sign-in: group gg_vcf_ops_operators has 1 member(s)
03:50:06  AD sign-in: group gg_vcf_ops_readonly has 1 member(s)
03:50:06  AD sign-in: checked - alice@acme.lab signs in
```

Five minutes later I ran the same sign-in by hand:

```text
alice    sign-in: HTTP 401 <!DOCTYPE html>
carol    sign-in: HTTP 401 <!DOCTYPE html>
bob      sign-in: HTTP 200 token issued
```

Nothing had touched the lab in between. Two of the three groups were empty;
bob's still held him.

## The setup

Phase 6 of our [lab catalog](/posts/lab-catalog-property-groups/) builds a
lab with its own AD domain, `acme.lab` on a domain controller `dc01`, plus a
vCenter and VCF Operations 9.1, all nested. The VCF Operations step adds the
domain as an Active Directory authentication source
(`POST /suite-api/api/auth/sources`) and imports three groups with a role
each (`POST /auth/usergroups`): `gg_vcf_ops_administrators` as
Administrator, `gg_vcf_ops_operators` as PowerUser, `gg_vcf_ops_readonly` as
ReadOnly. alice, carol and bob sit in one group each; labadmin is a second
administrator.

VCF Operations 9.1 signs in only users it has imported, so the build imported
the members too (`POST /auth/sources/{id}/users`).

## Wrong turn one: the import that drops the groups

Earlier that night, on the previous test lab, every AD user was refused. Two
details narrowed it down. A wrong password got a JSON 401, the right one an
HTML page titled "Not Authorized", and an LDAP bind as alice worked. So the
password was fine and the authorisation was not. The users existed in VCF
Operations, but only in Everyone:

```text
group Everyone: roles= perms=/all= users=5
group gg_vcf_ops_operators: roles=PowerUser perms=PowerUser/all=False users=0
group gg_vcf_ops_administrators: roles=Administrator perms=Administrator/all=False users=0
group gg_vcf_ops_readonly: roles=ReadOnly perms=ReadOnly/all=False users=0
alice sign-in: HTTP 401 <!DOCTYPE html> <html> <head> <title>Not Authorized</title> ...
```

The build had imported each user with their group IDs, and VCF Operations
had dropped them. A `PUT` on the group answered 500 "Database Error". Importing
the same users again, this time with each user's own ID from
`GET /auth/users`, filled the groups and all three signed in. The build got
that second import, and a real sign-in as its last check: the check that
passed at 03:50.

## Wrong turn two: blame the timing

After I put the members back by hand, the groups held for nine minutes. So I
replayed the build's sequence from a clean slate and polled the groups every
10 seconds:

```text
04:07:35 group gg_vcf_ops_administrators created
...
04:07:37 first import
04:07:39 re-import
04:07:39 administrators=[alice,labadmin] operators=[carol] readonly=[bob]
04:09:26 administrators=[] operators=[] readonly=[]
04:14:59 end: administrators=[] operators=[] readonly=[]
```

Every group emptied about 105 seconds after it was created, and the
authentication source had its group sync (`autoSync`) on. My workaround that
morning turned the sync off, waited until 150 seconds after the import,
re-imported any group that came up short and signed in one member of each.
It passed, fresh and on a re-run.

It also meant VCF Operations no longer followed AD: a user added to a group
could not sign in until someone ran the script again. And a group mapped to
a role should not lose its members to its own sync. Either the product was
broken or I was using it wrong.

## One field

The appliance serves its own API reference at
`/suite-api/docs/rest/index.html`. The entry for `POST /api/auth/usergroups`
starts with the sentence that explained the night:

> For LDAP/AD groups the distinguishedName should be provided in the name
> field.

The rest of the note says that `displayName` only matters at import and takes
the value of `name` when it is left out. It also advises checking first that
the group exists in the source, with `/api/auth/sources/{id}/usergroups/search`,
because importing a group the source does not know is not an error: VCF
Operations creates a new group of that name instead.

Our build sent `name: "gg_vcf_ops_readonly"`. No group has that
distinguished name, so VCF Operations neither refused the call nor warned. It
created a new group of that name, attached to the lab domain's source and
linked to nothing in AD. The role was right, and so were the members pushed
in by hand. Then the group sync did its job: as far as it could tell, that
group had no members in AD, so it emptied it. The search call the note
mentions returns the DN to use.

![Short name: a new, unlinked group the sync empties. DN: the AD group, which the sync fills](/images/vcf-ops-ad-groups-by-dn-diagram.svg)

## The proof

On the rehearsal lab I deleted the read-only group and bob's imported user,
imported the group by its DN with the short name as `displayName`, switched
the source's sync back on and started a sync:

```text
14:37:43 deleted user bob@acme.lab
14:37:43 imported by DN: id=fd90400d-... name=CN=gg_vcf_ops_readonly,OU=Lab Groups,DC=acme,DC=lab displayName=gg_vcf_ops_readonly role=ReadOnly members=0
14:37:44 source autoSync on
14:37:44 synchronize: ok
14:37:45    1 s  members 1: bob@acme.lab | bob@acme.lab signs in
14:40:19  155 s  members 1: bob@acme.lab | bob@acme.lab signs in
...
14:45:28  464 s  members 1: bob@acme.lab | bob@acme.lab signs in
```

Nobody imported bob this time: the sync did, within a second, and he stayed
for eight minutes.

Then the part the workaround had given up: following AD. I created a user
`dave` in the lab domain, with a user principal name, and added him to the
group:

```text
15:34:28 AD: user dave created (dave@acme.lab), enabled
15:34:28 AD: dave added to gg_vcf_ops_readonly
15:34:28 dave before a sync: refused: HTTP 401 {"type":"Error","message":"The provided username/pa
15:34:29 forced group sync sent
15:34:44 Ops members after the sync: alice@acme.lab,dave@acme.lab,bob@acme.lab
15:34:45 dave after the sync: signs in
```

alice is in that list because an earlier test had added her to the group in
AD. The automatic sync had not picked her up in six minutes of watching; it
runs roughly every 45 minutes. A sync by hand makes an AD change count at
once: `PUT /auth/sources/{id}/usergroups/synchronize`, or in the UI
**Administration** > **Access Control** > **Authentication Sources**.
Another test found the last gap: the lab's `student` account, added to the
group, never appeared. It had no user principal name, and the source
identifies users by `userPrincipalName`, so VCF Operations' own user search
could not find it.

## What the build does now

The VCF Operations step looks up each group's DN and members in AD over LDAP,
then imports the group by DN, with the short name as the display name:

```powershell
$g = Invoke-Json POST "$suite/auth/usergroups" @{ authSourceId = $src.id; name = $w.dn; displayName = $gn; 'role-permissions' = @(@{ roleName = $w.role; allowAllObjects = $true }) } $auth
```

It creates the source with the group sync on and starts a sync. It waits up
to five minutes for the members, and imports directly any the sync missed,
twice, because of the first-import drop. It checks 150 seconds after the
import that the groups kept their members, and signs in one member of each
group. A failure leaves `OPS-AD-FAILED.txt` on the jump host's desktop with
the reason and the command that runs the step again; a run that succeeds
removes it.

A run on a lab built before the fix replaces the short-name groups and turns
the sync back on. The rehearsal lab still had two of them:

```text
15:21:54  AD sign-in: group gg_vcf_ops_administrators was imported by its short name (not linked to AD) - replacing it
15:21:55  AD sign-in: group gg_vcf_ops_administrators imported as Administrator (CN=gg_vcf_ops_administrators,OU=Lab Groups,DC=acme,DC=lab)
...
15:21:56  AD sign-in: group sync started
15:22:28  AD sign-in: waiting 118 s, then checking that the groups kept their members
15:24:27  AD sign-in: group gg_vcf_ops_administrators has 2 member(s) of 2 in AD
15:24:28  AD sign-in: group gg_vcf_ops_operators has 1 member(s) of 1 in AD
15:24:28  AD sign-in: group gg_vcf_ops_readonly has 1 member(s) of 1 in AD
15:24:29  AD sign-in: checked - alice@acme.lab signs in (gg_vcf_ops_administrators)
15:24:29  AD sign-in: checked - carol@acme.lab signs in (gg_vcf_ops_operators)
15:24:29  AD sign-in: checked - bob@acme.lab signs in (gg_vcf_ops_readonly)
```

The sync brought every member itself.

## Why this matters outside the lab

Connected by hand, you pick the group from a directory search, and the
search result carries its distinguished name. Automation that types the
group's name skips that step, and this API accepts it. Everything then looks
right: the group exists, it has its role, the first sign-in works. It fails
later, for the users rather than for the build.

Directory-backed roles are what make access manageable and auditable: people
join and leave once, in the directory, and every tool follows. A tool that has
quietly stopped following keeps whatever it was last told. And an API that
turns an unknown reference into a new object instead of an error is common
well beyond VCF Operations. The cure is the same everywhere: read back what
you created, check it is linked to what you meant, and check again after the
platform's background jobs have had their turn.

## Rules learned

- For an AD or LDAP group, `POST /auth/usergroups` takes the distinguished
  name in `name` and the short name in `displayName`. A short name creates a
  new, unlinked group, without an error.
  `POST /auth/sources/{id}/usergroups/search` returns the DN.
- An unlinked group loses its members at the next group sync, here about
  105 seconds after the import. Turning the sync off hides the bug and stops
  VCF Operations following AD.
- VCF Operations 9.1 signs in imported users only. A linked group's sync
  imports its members that have the source's user name attribute, here
  `userPrincipalName`.
- A first direct user import can drop the users' groups; importing again with
  each user's `id` sets them.
- A wrong password gets a JSON 401; a user with no role gets an HTML "Not
  Authorized" page.
- Check after the background jobs: one real sign-in per group, minutes after
  the import, not seconds.

---
*Lab environment; opinions my own. Everything above was captured from a live
VCF 9.1 environment - output trimmed for length, never edited for outcome.*
