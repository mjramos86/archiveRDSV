#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Dump everything the Internet Archive's Wayback Machine holds for a site.

  python scripts/wayback_dump.py index     # build state/index.tsv (latest capture per URL)
  python scripts/wayback_dump.py fetch     # download, commit and push as it goes

Can be stopped at any time (Ctrl+C, closing the window, shutting the computer
down) and restarted later: it resumes where it left off. At most the last few
minutes of downloads are fetched again.

Runs either on GitHub Actions (DUMP_RUNNER=actions) or on a personal computer
(default). While a computer is working on it, the GitHub Actions runs step
aside: the computer writes a heartbeat (state/local-heartbeat.txt) every few
minutes, and Actions only resumes once it is more than 2 hours old.
Each runner keeps its own log (state/done-<runner>.tsv) so they never conflict.
"""
import argparse
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

DOMAIN = os.environ.get("DOMAIN", "jeuxvideo.rds.ca")
RUNNER = os.environ.get("DUMP_RUNNER", "local")
UA = "Mozilla/5.0 (personal archiving of jeuxvideo.rds.ca; github.com/mjramos86/archiveRDSV)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "state")
SITE = os.path.join(ROOT, "site")
HEARTBEAT = os.path.join(STATE, "local-heartbeat.txt")
MAX_BYTES = 95 * 1024 * 1024          # GitHub rejects files over 100 MB
WINDOWS = os.name == "nt"
os.makedirs(STATE, exist_ok=True)

# Pacing: archive.org refuses connections when requests come too fast. Cloud
# servers (GitHub) are throttled much harder than home connections. The pace
# adapts: it slows down after each refusal and speeds up again after a run of
# successes, never going below the floor.
FLOOR = float(os.environ.get("WAYBACK_FLOOR", "16" if RUNNER == "actions" else "2"))
PACE = {"interval": FLOOR, "streak": 0}
STATS = {}


def say(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


def lp(path):
    """Windows long-path support (paths over 260 characters)."""
    if WINDOWS:
        p = os.path.abspath(path)
        return p if p.startswith("\\\\?\\") else "\\\\?\\" + p
    return path


def get(url, timeout=90, tries=4):
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                body = r.read()
            PACE["streak"] += 1
            if PACE["streak"] >= 20 and PACE["interval"] > FLOOR:
                PACE["interval"] = max(FLOOR, PACE["interval"] * 0.85)
                PACE["streak"] = 0
            return 200, body
        except urllib.error.HTTPError as e:
            STATS[e.code] = STATS.get(e.code, 0) + 1
            if e.code in (403, 404, 410):
                return e.code, b""
            if e.code != 429 and e.code < 500:
                return e.code, b""
        except Exception as e:  # noqa: BLE001  (refused, reset, timeout…)
            name = type(e).__name__
            STATS[name] = STATS.get(name, 0) + 1
        # refused / throttled / server error: slow down and wait
        PACE["streak"] = 0
        PACE["interval"] = min(60.0, PACE["interval"] * 1.5 + 1)
        time.sleep(min(300, 30 * (attempt + 1)))
    return None, b""


def build_index():
    base = ("https://web.archive.org/cdx/search/cdx?url=" + urllib.parse.quote(DOMAIN + "/*")
            + "&output=json&fl=urlkey,timestamp,original,mimetype,statuscode,length"
            + "&filter=statuscode:200&showResumeKey=true&limit=100000")
    latest, key, page = {}, None, 0
    while True:
        url = base + (("&resumeKey=" + urllib.parse.quote(key)) if key else "")
        st, body = get(url, timeout=600)
        if st != 200:
            sys.exit(f"CDX query failed ({st}) on page {page}")
        rows = json.loads(body or b"[]")
        key = None
        if rows and rows[-1] and len(rows[-1]) == 1:
            key = rows[-1][0]
            rows = rows[:-2]
        for r in (rows[1:] if rows and rows[0] and rows[0][0] == "urlkey" else rows):
            if len(r) < 6:
                continue
            uk, ts, orig, mime, _sc, ln = r
            if uk not in latest or ts > latest[uk][0]:
                latest[uk] = (ts, orig, mime, ln)
        page += 1
        say(f"CDX page {page}: {len(latest)} distinct URLs so far")
        if not key:
            break
    with open(os.path.join(STATE, "index.tsv"), "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["urlkey", "timestamp", "original", "mimetype", "length"])
        for uk in sorted(latest):
            ts, orig, mime, ln = latest[uk]
            w.writerow([uk, ts, orig, mime, ln])
    say(f"index: {len(latest)} URLs")


RESERVED = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}


def clean_part(p):
    p = re.sub(r'[<>:"\\|?*\x00-\x1f]', "_", p)[:150].rstrip(" .") or "_"
    return p + "_" if p.split(".")[0].lower() in RESERVED else p


def local_path(orig, mime):
    u = urllib.parse.urlsplit(orig)
    host = (u.hostname or DOMAIN).lower()
    path = re.sub(r"/{2,}", "/", urllib.parse.unquote(u.path or "/"))
    if path.endswith("/"):
        path += "index.html"
    elif "." not in os.path.basename(path) and "html" in (mime or ""):
        path += "/index.html"
    if u.query:
        stem, ext = os.path.splitext(path)
        path = f"{stem}__q{hashlib.sha1(u.query.encode()).hexdigest()[:10]}{ext}"
    parts = [clean_part(p) for p in path.split("/") if p not in ("", ".", "..")]
    return os.path.join(SITE, host, *parts)


THUMB_RE = re.compile(r"-(\d{2,4})x(\d{2,4})(\.(?:jpe?g|png|gif|webp))$", re.I)


def drop_redundant_thumbs(rows):
    """WordPress keeps several resized copies of each upload (photo-300x200.jpg…).
    Skip a resized copy when the original, or a larger copy, is archived."""
    originals = {r["original"].split("?")[0].lower() for r in rows}
    best = {}
    for r in rows:
        url = r["original"].split("?")[0]
        m = THUMB_RE.search(url)
        if r["mimetype"].startswith("image/") and m:
            base, area = THUMB_RE.sub(r"\3", url).lower(), int(m.group(1)) * int(m.group(2))
            if base not in best or area > best[base][0]:
                best[base] = (area, r["urlkey"])
    largest = {k for _, k in best.values()}
    keep = []
    for r in rows:
        url = r["original"].split("?")[0]
        if r["mimetype"].startswith("image/") and THUMB_RE.search(url):
            if THUMB_RE.sub(r"\3", url).lower() in originals or r["urlkey"] not in largest:
                continue
        keep.append(r)
    say(f"skipping {len(rows) - len(keep)} resized image copies (original or a larger copy is archived)")
    return keep


def load_set(prefix):
    keys = set()
    for p in glob.glob(os.path.join(STATE, prefix + "*.tsv")):
        with open(p, encoding="utf-8") as f:
            keys.update(line.split("\t", 1)[0] for line in f if line.strip())
    return keys


def git(*args, check=False):
    return subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, check=check)


def local_runner_active():
    """True if a personal computer has been working on the dump in the last 2 hours."""
    git("fetch", "-q", "origin", "main")
    r = git("show", "origin/main:state/local-heartbeat.txt")
    if r.returncode != 0 or not r.stdout.strip():
        return False
    try:
        last = dt.datetime.fromisoformat(r.stdout.strip().split()[0])
    except ValueError:
        return False
    return dt.datetime.now(dt.timezone.utc) - last < dt.timedelta(hours=2)


def commit_and_push(msg):
    if RUNNER != "actions":
        with open(HEARTBEAT, "w", encoding="utf-8") as f:
            f.write(dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds") + f" {RUNNER}\n")
    git("add", "-A", "site", "state")
    if git("diff", "--cached", "--quiet").returncode == 0:
        return True
    if git("commit", "-q", "-m", msg).returncode != 0:
        say("! git commit failed (is git configured with your name and email?)")
        return False
    for _ in range(4):
        if git("push", "-q", "origin", "HEAD:main").returncode == 0:
            return True
        git("pull", "-q", "--rebase", "origin", "main")
        time.sleep(5)
    say("! push failed — files are saved and committed on this computer; they will be sent next time")
    return False


def fetch(budget, commit_every):
    start = time.time()
    if RUNNER == "actions" and local_runner_active():
        say("a personal computer is working on the dump right now — this run steps aside")
        return report(-1)
    with open(os.path.join(STATE, "index.tsv"), encoding="utf-8") as f:
        rows = drop_redundant_thumbs(list(csv.DictReader(f, delimiter="\t")))
    finished = load_set("done") | load_set("failed")
    todo = [r for r in rows if r["urlkey"] not in finished]
    # pages and article data first, then feeds, then images and the rest
    prio = lambda r: (0 if "html" in r["mimetype"] else 1 if "json" in r["mimetype"]
                      else 3 if r["mimetype"].startswith("image/") else 2)
    todo.sort(key=prio)
    say(f"{len(rows)} files to archive, {len(rows) - len(todo)} already done, {len(todo)} left")
    if not todo:
        return report(0)

    dlog = open(os.path.join(STATE, f"done-{RUNNER}.tsv"), "a", encoding="utf-8")
    flog = open(os.path.join(STATE, f"failed-{RUNNER}.tsv"), "a", encoding="utf-8")
    n = saved = since = 0
    last_commit = time.time()
    next_at = 0.0

    def checkpoint(reason=""):
        nonlocal since, last_commit
        dlog.flush(); flog.flush()
        el = max(1e-6, (time.time() - start) / 60)
        ok = commit_and_push(f"Wayback dump: +{since} files ({saved} saved this run, "
                             f"{saved / el:.1f}/min, pace {PACE['interval']:.0f}s, errors {STATS}){reason}")
        since, last_commit = 0, time.time()
        return ok

    try:
        for r in todo:
            if time.time() - start > budget:
                break
            wait = next_at - time.time()
            if wait > 0:
                time.sleep(wait)
            next_at = time.time() + PACE["interval"]
            st, body = get(f"https://web.archive.org/web/{r['timestamp']}id_/{r['original']}")
            if st == 200 and len(body) <= MAX_BYTES:
                p = local_path(r["original"], r["mimetype"])
                if os.path.isdir(lp(p)):
                    p = os.path.join(p, "index.html")
                os.makedirs(lp(os.path.dirname(p)), exist_ok=True)
                with open(lp(p), "wb") as fh:
                    fh.write(body)
                dlog.write(f"{r['urlkey']}\t{r['timestamp']}\t{r['original']}\t"
                           f"{os.path.relpath(p, ROOT).replace(os.sep, '/')}\n")
                saved += 1
            elif st in (403, 404, 410) or st == 200:
                flog.write(f"{r['urlkey']}\t{r['timestamp']}\t{r['original']}\t{st if st != 200 else 'too-large'}\n")
            # anything else (refused, timeouts, 5xx) is retried on the next run
            n += 1
            since += 1
            if n % 25 == 0:
                el = (time.time() - start) / 60
                say(f"{n} processed, {saved} saved, {saved / max(el, 1e-6):.1f}/min, "
                    f"pace {PACE['interval']:.1f}s, errors {STATS}")
            if since >= commit_every or time.time() - last_commit > 600:
                checkpoint()
                if RUNNER == "actions" and local_runner_active():
                    say("a personal computer took over — this run steps aside")
                    break
    except KeyboardInterrupt:
        say("stopped by you — saving progress…")
    finally:
        checkpoint()
        dlog.close(); flog.close()
    finished = load_set("done") | load_set("failed")
    return report(sum(1 for r in rows if r["urlkey"] not in finished))


def report(remaining):
    if remaining >= 0:
        say(f"{remaining} files left")
    with open(os.environ.get("GITHUB_OUTPUT", os.devnull), "a") as o:
        o.write(f"remaining={remaining}\n")
    return remaining


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["index", "fetch"])
    ap.add_argument("--budget", type=int, default=10**9, help="stop after N seconds")
    ap.add_argument("--commit-every", type=int, default=500)
    ap.add_argument("--workers", type=int, default=1, help="(ignored, kept for compatibility)")
    a = ap.parse_args()
    if a.cmd == "index":
        build_index()
    else:
        left = fetch(a.budget, a.commit_every)
        sys.exit(0 if left == 0 else 3)
