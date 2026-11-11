#!/usr/bin/env python3
"""
Dump everything the Internet Archive's Wayback Machine holds for a site.

  python3 scripts/wayback_dump.py index            # build state/index.tsv (latest capture per URL)
  python3 scripts/wayback_dump.py fetch --budget 18000 --commit-every 1200

- index : queries the CDX API (paged) for every capture of DOMAIN/*, keeps the
          most recent successful (HTTP 200) capture of each distinct URL and
          writes state/index.tsv  (urlkey, timestamp, original, mimetype, length)
- fetch : downloads each capture in its original form (Wayback "id_" mode, no
          toolbar or rewritten links) into site/<host>/<path>, skipping what is
          already done (state/done.tsv) or failed permanently (state/failed.tsv).
          Commits and pushes progress every N files and stops cleanly before the
          time budget runs out so the next run can resume.
"""
import argparse, concurrent.futures as cf, csv, hashlib, json, os, re, subprocess, sys, time
import urllib.parse, urllib.request, urllib.error

DOMAIN = os.environ.get("DOMAIN", "jeuxvideo.rds.ca")
UA = "Mozilla/5.0 (archive-dump for personal archiving; github actions)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
SITE = os.path.join(ROOT, "site")
MAX_BYTES = 95 * 1024 * 1024          # GitHub rejects files over 100 MB
os.makedirs(STATE, exist_ok=True)


def get(url, timeout=120, tries=6):
    delay = 5
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.status, r.read(), dict(r.headers)
        except urllib.error.HTTPError as e:
            if e.code in (404, 403, 410):
                return e.code, b"", {}
            if e.code == 429 or e.code >= 500:
                time.sleep(delay); delay = min(delay * 2, 120); continue
            return e.code, b"", {}
        except Exception:
            time.sleep(delay); delay = min(delay * 2, 120)
    return None, b"", {}


def build_index():
    base = ("https://web.archive.org/cdx/search/cdx?url=" + urllib.parse.quote(DOMAIN + "/*")
            + "&output=json&fl=urlkey,timestamp,original,mimetype,statuscode,length"
            + "&filter=statuscode:200&showResumeKey=true&limit=100000")
    latest, key, page = {}, None, 0
    while True:
        url = base + (("&resumeKey=" + urllib.parse.quote(key)) if key else "")
        st, body, _ = get(url, timeout=600)
        if st != 200:
            sys.exit(f"CDX query failed ({st}) on page {page}")
        rows = json.loads(body or b"[]")
        key = None
        if rows and rows[-1] and len(rows[-1]) == 1:          # resume key row
            key = rows[-1][0]; rows = rows[:-2]                   # (preceded by an empty row)
        for r in rows[1:] if rows and rows[0] and rows[0][0] == "urlkey" else rows:
            if len(r) < 6:
                continue
            uk, ts, orig, mime, sc, ln = r
            if uk not in latest or ts > latest[uk][0]:
                latest[uk] = (ts, orig, mime, ln)
        page += 1
        print(f"CDX page {page}: {len(latest)} distinct URLs so far", flush=True)
        if not key:
            break
    with open(os.path.join(STATE, "index.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["urlkey", "timestamp", "original", "mimetype", "length"])
        for uk in sorted(latest):
            ts, orig, mime, ln = latest[uk]
            w.writerow([uk, ts, orig, mime, ln])
    print(f"index: {len(latest)} URLs")


def local_path(orig, mime):
    u = urllib.parse.urlsplit(orig)
    host = (u.hostname or DOMAIN).lower()
    path = urllib.parse.unquote(u.path or "/")
    path = re.sub(r"/{2,}", "/", path)
    if path.endswith("/"):
        path += "index.html"
    elif "." not in os.path.basename(path) and "html" in (mime or ""):
        path += "/index.html"
    if u.query:
        stem, ext = os.path.splitext(path)
        h = hashlib.sha1(u.query.encode()).hexdigest()[:10]
        path = f"{stem}__q{h}{ext}"
    parts = [re.sub(r'[<>:"\\|?*\x00-\x1f]', "_", p)[:150] for p in path.split("/") if p not in ("", ".", "..")]
    return os.path.join(SITE, host, *parts)


def load_set(name):
    p = os.path.join(STATE, name)
    if not os.path.exists(p):
        return set()
    with open(p, encoding="utf-8") as f:
        return {line.split("\t", 1)[0] for line in f if line.strip()}


def git_commit(msg):
    subprocess.run(["git", "add", "-A", "site", "state"], cwd=ROOT, check=True)
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode == 0:
        return
    subprocess.run(["git", "commit", "-q", "-m", msg], cwd=ROOT, check=True)
    for _ in range(5):
        if subprocess.run(["git", "push", "-q", "origin", "HEAD"], cwd=ROOT).returncode == 0:
            return
        subprocess.run(["git", "pull", "-q", "--rebase", "origin", "main"], cwd=ROOT)
        time.sleep(5)


THUMB_RE = re.compile(r"-\d{2,4}x\d{2,4}(\.(?:jpe?g|png|gif|webp))$", re.I)


def drop_redundant_thumbs(rows):
    """WordPress keeps many resized copies (photo-300x200.jpg…) of each upload.
    Skip a resized copy when the full-size original is archived too."""
    originals = {r["original"].split("?")[0].lower() for r in rows}
    keep, skipped = [], 0
    for r in rows:
        url = r["original"].split("?")[0]
        if r["mimetype"].startswith("image/") and THUMB_RE.search(url) \
                and THUMB_RE.sub(r"\1", url).lower() in originals:
            skipped += 1
            continue
        keep.append(r)
    # no original archived: keep only the largest resized copy of each image
    size_re = re.compile(r"-(\d{2,4})x(\d{2,4})(\.(?:jpe?g|png|gif|webp))$", re.I)
    best = {}
    for r in keep:
        url = r["original"].split("?")[0]
        m = size_re.search(url)
        if r["mimetype"].startswith("image/") and m:
            base, area = size_re.sub(r"\3", url).lower(), int(m.group(1)) * int(m.group(2))
            if base not in best or area > best[base][0]:
                best[base] = (area, r["urlkey"])
    largest = {k for _, k in best.values()}
    final = []
    for r in keep:
        url = r["original"].split("?")[0]
        if r["mimetype"].startswith("image/") and size_re.search(url) and r["urlkey"] not in largest:
            skipped += 1
            continue
        final.append(r)
    print(f"skipping {skipped} resized copies (original or a larger copy is archived)", flush=True)
    return final


def fetch(budget, commit_every, workers):
    start = time.time()
    with open(os.path.join(STATE, "index.tsv"), encoding="utf-8") as f:
        rows = drop_redundant_thumbs(list(csv.DictReader(f, delimiter="\t")))
    done, failed = load_set("done.tsv"), load_set("failed.tsv")
    todo = [r for r in rows if r["urlkey"] not in done and r["urlkey"] not in failed]
    print(f"{len(rows)} URLs, {len(done)} done, {len(failed)} failed, {len(todo)} to fetch", flush=True)
    dlog = open(os.path.join(STATE, "done.tsv"), "a", encoding="utf-8")
    flog = open(os.path.join(STATE, "failed.tsv"), "a", encoding="utf-8")

    def one(r):
        src = f"https://web.archive.org/web/{r['timestamp']}id_/{r['original']}"
        st, body, hdr = get(src)
        return r, st, body

    n = since = 0
    with cf.ThreadPoolExecutor(workers) as ex:
        it = iter(todo)
        futs = set()
        def refill():
            while len(futs) < workers * 2 and time.time() - start < budget:
                try:
                    futs.add(ex.submit(one, next(it)))
                except StopIteration:
                    break
        refill()
        while futs:
            fin, _ = cf.wait(futs, return_when=cf.FIRST_COMPLETED)
            for fu in fin:
                futs.discard(fu)
                r, st, body = fu.result()
                if st == 200 and body is not None and len(body) <= MAX_BYTES:
                    p = local_path(r["original"], r["mimetype"])
                    os.makedirs(os.path.dirname(p), exist_ok=True)
                    if os.path.isdir(p):
                        p = os.path.join(p, "index.html")
                    with open(p, "wb") as fh:
                        fh.write(body)
                    dlog.write(f"{r['urlkey']}\t{r['timestamp']}\t{r['original']}\t{os.path.relpath(p, ROOT)}\n")
                elif st in (403, 404, 410) or (st == 200 and len(body) > MAX_BYTES):
                    flog.write(f"{r['urlkey']}\t{r['timestamp']}\t{r['original']}\t{st if st != 200 else 'too-large'}\n")
                # transient failures (None / 5xx after retries) are retried next run
                n += 1; since += 1
                if since >= commit_every:
                    dlog.flush(); flog.flush()
                    git_commit(f"Wayback dump: +{since} files ({n} this run)")
                    since = 0
            refill()
    dlog.close(); flog.close()
    git_commit(f"Wayback dump: +{since} files ({n} this run)")
    finished = load_set("done.tsv") | load_set("failed.tsv")
    remaining = sum(1 for r in rows if r["urlkey"] not in finished)
    print(f"run finished: {n} processed, {remaining} remaining", flush=True)
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        o.write(f"remaining={remaining}\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "fetch"])
    ap.add_argument("--budget", type=int, default=18000)
    ap.add_argument("--commit-every", type=int, default=1500)
    ap.add_argument("--workers", type=int, default=4)
    a = ap.parse_args()
    build_index() if a.cmd == "index" else fetch(a.budget, a.commit_every, a.workers)
