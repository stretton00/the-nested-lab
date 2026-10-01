"""Check every link on the built site (1 Oct 2026; .github/workflows/linkcheck.yaml runs it weekly).

  python3 linkcheck.py <public dir> <site base URL> <report.md>

Internal links (relative, or on the site's own host) must resolve to a file in the build. External links are fetched
once each, with a browser User-Agent and two retries. Broken = 404 or 410, or a host that does not resolve. Hosts that
refuse robots (401, 403, 429, LinkedIn's 999) and timeouts are listed as unverified, without failing the check.
Placeholders are skipped: localhost, private addresses, .local, .lab, the example domains.
Writes the report (also to the job summary) and exits 1 when anything is broken."""
import concurrent.futures, html.parser, ipaddress, os, socket, sys, time, urllib.error, urllib.parse, urllib.request

PUBLIC, BASE, REPORT = sys.argv[1], sys.argv[2].rstrip("/") + "/", sys.argv[3]
SITE_HOST = urllib.parse.urlparse(BASE).hostname
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36"
SKIP_SUFFIX = (".local", ".lab", ".internal", ".example", ".test", ".invalid", ".svc")
SKIP_HOSTS = {"localhost", "example.com", "example.org", "example.net"}
UNVERIFIED = {401, 403, 405, 429, 999}


class Links(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.found = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        for key in {"a": ["href"], "img": ["src"], "source": ["src"], "video": ["poster"]}.get(tag, []):
            if a.get(key):
                self.found.append(a[key])


def skip(host):
    if not host or host in SKIP_HOSTS or host.endswith(SKIP_SUFFIX) or "{" in host or "<" in host:
        return True
    if any(host.endswith("." + d) for d in SKIP_HOSTS):       # RFC 2606 example domains, as quoted in schema texts
        return True
    try:
        ip = ipaddress.ip_address(host)
        return ip.is_private or ip.is_loopback or ip.is_link_local
    except ValueError:
        return False


def internal_ok(path):
    path = urllib.parse.unquote(path.split("#")[0].split("?")[0])
    full = os.path.join(PUBLIC, path.lstrip("/"))
    if path.endswith("/"):
        return os.path.isfile(os.path.join(full, "index.html"))
    return os.path.isfile(full) or os.path.isfile(os.path.join(full, "index.html"))


def fetch(url):
    last = "?"
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})
            with urllib.request.urlopen(req, timeout=25) as r:
                return r.status, ""
        except urllib.error.HTTPError as e:
            if e.code in (404, 410) or e.code in UNVERIFIED:
                return e.code, ""
            last = "HTTP %d" % e.code
        except urllib.error.URLError as e:
            if isinstance(e.reason, socket.gaierror):
                return "dns", str(e.reason)
            last = str(e.reason)
        except Exception as e:                          # timeouts, resets
            last = type(e).__name__
        time.sleep(3 * (attempt + 1))
    return "unreachable", last


pages = {}
for root, _, files in os.walk(PUBLIC):
    for f in files:
        if f.endswith(".html"):
            p = os.path.join(root, f)
            parser = Links()
            with open(p, encoding="utf-8", errors="replace") as fh:
                parser.feed(fh.read())
            pages["/" + os.path.relpath(p, PUBLIC).replace(os.sep, "/").replace("index.html", "")] = parser.found

broken, unverified, external = [], [], {}
for page, links in sorted(pages.items()):
    for link in links:
        link = link.strip()
        if not link or link.startswith(("#", "mailto:", "tel:", "javascript:", "data:", "blob:")):
            continue
        u = urllib.parse.urlparse(urllib.parse.urljoin(BASE + page.lstrip("/"), link))
        if u.scheme not in ("http", "https"):
            continue
        if u.hostname == SITE_HOST or (u.hostname or "").endswith("." + SITE_HOST):
            if u.hostname == SITE_HOST and not internal_ok(u.path):
                broken.append((page, link, "not in the build"))
            continue
        if skip(u.hostname):
            continue
        external.setdefault(urllib.parse.urlunparse(u._replace(fragment="")), set()).add(page)

with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
    results = dict(zip(external, pool.map(fetch, external)))
for url, (status, why) in sorted(results.items()):
    where = ", ".join(sorted(external[url])[:3]) + (" and %d more" % (len(external[url]) - 3) if len(external[url]) > 3 else "")
    if status in (404, 410, "dns"):
        broken.append((where, url, "%s %s" % (status, why)))
    elif status == "unreachable" or status in UNVERIFIED:
        unverified.append((where, url, "%s %s" % (status, why)))

lines = ["# Link check of %s" % BASE, "",
         "%d pages, %d external links checked: %d broken, %d unverified." % (len(pages), len(external), len(broken), len(unverified)), ""]
if broken:
    lines += ["## Broken", "", "| Page | Link | Result |", "|---|---|---|"] + ["| %s | %s | %s |" % b for b in broken] + [""]
if unverified:
    lines += ["## Unverified (the host refused a robot, or timed out)", "", "| Page | Link | Result |", "|---|---|---|"] + \
             ["| %s | %s | %s |" % u for u in unverified] + [""]
text = "\n".join(lines)
with open(REPORT, "w", encoding="utf-8") as fh:
    fh.write(text)
if os.environ.get("GITHUB_STEP_SUMMARY"):
    with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
        fh.write(text + "\n")
print(text)
sys.exit(1 if broken else 0)
