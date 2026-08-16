#!/usr/bin/env python3
"""Split the Adamantius 'Autore' field into individual author strings.

The field mixes two conventions, sometimes inside a single string:
  'Guinot J.-N.'                      surname-first
  'J. Dorival B. Barc G. Favrelle'    initials-first, several authors
  'Radice R. A.P. Bos'                both conventions in one string
  'Hoek A. van den'                   surname-first with trailing particle
Method: an author unit is complete once it holds at least one block of
initials AND at least one true name word (particles do not count); the next
non-particle token then opens a new unit. The verbatim string is always kept
alongside the split (authors_raw), so nothing is lost.
"""
import re

INIT = re.compile(r"^[A-ZÀ-ÖØ-Þ]\.(?:[-–]?[A-ZÀ-ÖØ-Þ]\.)*$")
PARTICLE = {"van", "den", "der", "de", "von", "le", "la", "du", "des", "di",
            "della", "dei", "dos", "el", "al", "ter", "ten", "zu", "y", "af",
            "do", "da", "van't", "op"}


def _kind(tok):
    if INIT.match(tok):
        return "I"
    if tok.lower().strip(",.") in PARTICLE:
        return "p"
    return "w"


def split_authors(raw):
    raw = (raw or "").strip(" ;,")
    if not raw:
        return []
    toks = raw.split()
    kinds = [_kind(t) for t in toks]
    if "I" not in kinds:
        return [raw]

    authors = []
    buf, has_init, has_word = [], False, False
    for t, k in zip(toks, kinds):
        complete = has_init and has_word
        if complete and k != "p":
            authors.append(" ".join(buf))
            buf, has_init, has_word = [], False, False
        buf.append(t)
        if k == "I":
            has_init = True
        elif k == "w":
            has_word = True
    if buf:
        authors.append(" ".join(buf))
    return [a.strip(" ,;") for a in authors if a.strip(" ,;")]


if __name__ == "__main__":
    tests = [
        "Guinot J.-N.", "J. Dorival B. Barc G. Favrelle M. Petit J. Tolila",
        "G. Reale R. Radice", "Hoek A. van den", "Hengel M. Schwemer A.M.",
        "Radice R. A.P. Bos", "Jonas H. R. Farina M. Simonetti",
        "Broek R. van den", "Carbone S.P.", "P. Sacchi L. Troiani",
        "G. Dorival A. Le Boulluec M. Alexandre M. Fedou A. Pourkier J. Wolinski",
        "Crouzel H.", "", "Anonimo",
    ]
    for t in tests:
        print("%-74s -> %s" % (repr(t), split_authors(t)))
