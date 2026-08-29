# The Nested Lab (working title)

Hugo + PaperMod blog. Posts live in `content/posts/` (markdown, `draft: true`
until ready).

## Local preview
    hugo server -D          # http://localhost:1313, drafts included

## Publish a post
1. Set `draft: false` in its front matter
2. `git add -A && git commit -m "post: <title>" && git push`
3. GitHub Actions builds and deploys automatically

## One-time launch steps
1. Create an empty GitHub repo (e.g. `blog`), then:
       git remote add origin https://github.com/<YOU>/blog.git
       git push -u origin main
2. Repo Settings -> Pages -> Source: **GitHub Actions**
3. First deploy runs automatically; site appears at the Pages URL
4. Custom domain (recommended): Settings -> Pages -> Custom domain, add DNS
   CNAME, then update `baseURL` in `hugo.toml`
5. Rename: change `title` + `params.homeInfoParams` in `hugo.toml`
6. Fill in the social links (commented out in `hugo.toml`)

## House rules (see ../PLAN.md)
- Employer sign-off before first publish
- Customer material never appears; techniques only
- Real output, trimmed never faked
