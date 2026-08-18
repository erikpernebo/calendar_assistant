#!/usr/bin/env python3
"""Check this repository for personal data before it is pushed.

This repo is public; the vault is private. Two real leaks have already made it
past a visual review -- a compiled .pyc with a home directory baked into it, and
a reminder UUID pasted into a doc as an example. Neither was visible by eye.

  privacy_audit.py            working tree, staged content, and full history
  privacy_audit.py --quick    skip the history scan

Exit 0 clean, 1 findings, 2 not configured.

Two kinds of check run:

  Terms      Literal strings that are personal -- names, emails, course codes,
             organisations, employers. These CANNOT live in this file, because
             this file is public. They are read from `private-terms.txt` in the
             vault. No terms file means no term checking, which is reported as a
             failure rather than a pass: an audit that checks nothing must never
             look like an audit that found nothing.

  Patterns   Shapes that are personal whatever their content -- home paths,
             email addresses, UUIDs, calendar and reminder identifiers. These
             need no list and are always checked.

History is scanned too. Rewriting a pushed commit is possible but ugly, and
GitHub keeps serving the orphaned object by SHA afterwards, so the only good
time to catch a leak is before the push.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TERMS_FILE = "private-terms.txt"

# Written so that no pattern matches its own source text -- the audit scans
# every tracked file, including this one, and a self-matching pattern would
# report a finding on every run until someone learned to ignore the output.
PATTERNS = [
    (r"[/]Users[/][A-Za-z0-9._-]+", "home directory path"),
    (r"[/]home[/][A-Za-z0-9._-]+", "home directory path"),
    (r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}", "email address"),
    (r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
     r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "UUID"),
    (r"x[-]apple[-]reminder://[0-9A-Za-z]{8}", "Apple Reminders identifier"),
    (r"@group[.]calendar[.]google[.]com", "Google calendar id"),
    (r"[A-Za-z0-9_-]{24,}@google[.]com", "Google calendar id"),
]

# Never belongs in a commit, whatever it contains.
FORBIDDEN_PATHS = [
    (r"\.pyc$", "compiled bytecode embeds the build path"),
    (r"(^|/)__pycache__/", "compiled bytecode embeds the build path"),
    (r"(^|/)\.DS_Store$", "Finder metadata"),
    (r"\.local\.json$", "local machine config points at the vault"),
]

# Examples in docs need placeholders, not redacted real values. An all-zero
# UUID reads as "there was a real one here", which is a hint, not a redaction.
ALLOWED = [
    re.compile(r"00000000-0000-0000-0000-000000000000"),
    re.compile(r"[/]absolute[/]path[/]to"),
    re.compile(r"[/]path[/]to[/]"),
]


def git(*args, check=False):
    return subprocess.run(["git", "-C", ROOT, *args],
                          capture_output=True, text=True, check=check)


def allowed(line):
    return any(p.search(line) for p in ALLOWED)


def load_terms():
    """Terms come from the vault, because they cannot live in a public repo."""
    cfg = os.path.join(ROOT, "vault.local.json")
    if not os.path.exists(cfg):
        return None, "vault.local.json is missing, so the term list cannot be found"
    try:
        vault = json.load(open(cfg))["vault"]
    except (ValueError, KeyError) as ex:
        return None, f"vault.local.json is unreadable: {ex}"
    path = os.path.join(vault, TERMS_FILE)
    if not os.path.exists(path):
        return None, (f"{TERMS_FILE} is missing from the vault. Create it with "
                      f"one personal term per line -- names, emails, course "
                      f"codes, organisations, employers.")
    terms = [ln.strip() for ln in open(path)
             if ln.strip() and not ln.startswith("#")]
    if not terms:
        return None, f"{TERMS_FILE} is empty"
    return terms, None


def grep(args, label, why, findings, revs=None, terms=None):
    """Run one git grep. Absent matches, git grep exits 1; that is not an error.

    Patterns are run one at a time rather than as one alternation. It costs a
    few extra processes on a repo this size and buys a finding that says which
    rule fired -- without that, a false positive is indistinguishable from a
    real leak and the whole report gets waved through.
    """
    p = git(*(["grep", "-n", "-I", "-i", *args] + (revs or [])))
    if p.returncode not in (0, 1):
        findings.append((label, why, p.stderr.strip() or "git grep failed"))
        return
    for line in p.stdout.splitlines():
        if allowed(line):
            continue
        detail = why
        if terms:
            hit = [t for t in terms
                   if re.search(r"\b" + re.escape(t) + r"\b", line, re.I)]
            detail = "term " + ", ".join(repr(h) for h in hit) if hit else why
        findings.append((label, detail, line))


def scan_all(label, findings, tmp, terms, revs=None):
    for pat, why in PATTERNS:
        grep(["-E", "-e", pat], label, why, findings, revs)
    if tmp:
        # -w matters: campus abbreviations and course codes are short, and a
        # substring match turns "repository" into a hit for a building called
        # POS. An audit that cries wolf is an audit nobody reads.
        grep(["-w", "-F", "-f", tmp.name], label, "term", findings, revs, terms)


def main():
    quick = "--quick" in sys.argv
    findings = []
    notes = []

    terms, problem = load_terms()
    tmp = None
    if terms:
        tmp = tempfile.NamedTemporaryFile("w", suffix=".txt", delete=False)
        tmp.write("\n".join(terms) + "\n")
        tmp.close()
        notes.append(f"{len(terms)} private terms loaded from the vault")
    else:
        notes.append(f"TERM CHECK DID NOT RUN: {problem}")

    # Working tree: tracked files plus anything untracked that is not ignored,
    # since an untracked file is one `git add .` away from being committed.
    scan_all("working tree", findings, tmp, terms)
    for pat, why in PATTERNS:
        grep(["--cached", "-E", "-e", pat], "staged", why, findings)
    if tmp:
        grep(["--cached", "-w", "-F", "-f", tmp.name], "staged", "term",
             findings, terms=terms)

    untracked = git("ls-files", "--others", "--exclude-standard").stdout.split()
    for path in untracked:
        full = os.path.join(ROOT, path)
        try:
            text = open(full, errors="ignore").read()
        except OSError:
            continue
        for i, line in enumerate(text.splitlines(), 1):
            if allowed(line):
                continue
            for pat, why in PATTERNS:
                if re.search(pat, line):
                    findings.append(("untracked", why, f"{path}:{i}:{line.strip()}"))
            for t in terms or []:
                if re.search(r"\b" + re.escape(t) + r"\b", line, re.I):
                    findings.append(("untracked", f"term {t!r}",
                                     f"{path}:{i}:{line.strip()}"))

    if not quick:
        revs = git("rev-list", "--all").stdout.split()
        if revs:
            scan_all("history", findings, tmp, terms, revs)
        else:
            notes.append("no commits yet, so history was not scanned")
    else:
        notes.append("history scan skipped (--quick)")

    for path in git("ls-files").stdout.split():
        for pat, why in FORBIDDEN_PATHS:
            if re.search(pat, path):
                findings.append(("tracked file", why, path))

    # A gitignore entry that does not actually match is a rule everyone
    # believes in and nobody is protected by.
    for probe, why in [("vault.local.json", "vault path config"),
                       (".claude/settings.local.json", "local settings"),
                       ("bin/__pycache__/x.pyc", "bytecode"),
                       (".DS_Store", "Finder metadata")]:
        if git("check-ignore", "-q", probe).returncode != 0:
            findings.append(("gitignore", why, f"{probe} is not ignored"))

    if tmp:
        os.unlink(tmp.name)

    for n in notes:
        print(f"  note: {n}")
    if problem:
        print("\nFAIL: the audit was not fully configured; treat this as a "
              "failure, not a pass.")
        return 2
    if not findings:
        print("\nclean")
        return 0

    print(f"\n{len(findings)} finding(s):\n")
    for where, why, detail in findings:
        print(f"  [{where}]{' ' + why if why else ''}\n    {detail}")
    print("\nNothing here should be pushed. Redact with a placeholder, not a "
          "blanked-out real value.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
