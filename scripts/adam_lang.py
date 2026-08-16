#!/usr/bin/env python3
"""Weighted stopword language guess for Adamantius titles.

Returns a two-letter code only when one language wins clearly; otherwise None.
The database renders apostrophes as backticks, so elided forms (dell`, l`, d`)
are matched on the backtick.
"""
import re

# (regex, weight) per language. High weight = distinctive of that language.
MARKERS = {
    "it": [(r"\b(della|dello|degli|delle|nella|nello|negli|nelle|sulla|sullo|dalla|dalle|allo|agli|alla)\b", 3),
           (r"(?:dell|nell|all|sull|dall|quell|un|nel)`", 3),
           (r"\b(di|nel|nei|dal|dai|gli|che|come|secondo|studi|ricerche|tra|fra|questione|storia|pensiero)\b", 2),
           (r"\b(il|lo|una|un|per|non|con|suo|sua|alcuni|nella|nel|sui|sul)\b", 1),
           (r"\b(?:l|d)`[aeiouàèéìòù]", 1),
           (r"\b(padri|scuola|chiesa|vita|cultura|opere|lettera|commento|pensiero|problema|rapporto|figura|testo|libro|antico|antica|nuovo|nuova|primo|greco|cristiana|cristiano|ancora|anche|dopo|contro)\b", 2)],
    "fr": [(r"\b(dans|selon|chez|aux|entre|entre|étude|études|autour|entre|ainsi|celui|leur|ses|cette|quelques)\b", 3),
           (r"\b(?:qu|j|c|s|n|m|t)`[a-zàâçéèêëîïôûùüÿœ]", 3),
           (r"\b(?:l|d)`[a-zàâçéèêëîïôûùüÿœ]", 1),
           (r"\b(père|pères|église|vie|oeuvre|lettre|commentaire|pensée|problème|figure|thème|texte|livre|ancien|nouveau|premier|grec|chrétienne|chrétien)\b", 2),
           (r"\b(des|une|du|sur|pour|et|par|est|ou|au|à|son|son|son)\b", 2),
           (r"\b(ancienne|ancien|nouvelle|nouveau|autour|depuis|jusqu|encore|même|aussi|contre|avant|après|face)\b", 2),
           (r"\b(la|le|les|de|en|se|ce|qui|que|ne)\b", 1)],
    "de": [(r"\b(die|der|das|den|dem|und|zur|zum|über|bei|für|eines|einer|einem|nach|zwischen|durch|seine|ihre|als|nicht|sich|zwei)\b", 3),
           (r"\b(untersuchungen|studien|beiträge|beitrag|geschichte|frage|bemerkungen|anmerkungen|auslegung|deutung|verhältnis)\b", 3),
           (r"\b(von|im|des|ein|eine|auf|aus|mit|vom|am|zu)\b", 2)],
    "en": [(r"\b(the|and|of|to|for|from|between|according|with|its|his|her|their|some|early|new|this|about|towards|through|against)\b", 3),
           (r"\b(studies|essays|study|notes|remarks|reading|interpretation|thought|problem|question)\b", 2),
           (r"\b(in|on|a|an|as|by|is|are|was|were)\b", 1)],
    "es": [(r"\b(el|los|las|según|españa|papel|hacia|sobre|entre|desde|una|del|para|escuela|teología|filosofía|pensamiento|estudios)\b", 3),
           (r"\b(de la|y|en|que|su|no)\b", 1)],
    "nl": [(r"\b(het|van|een|door|zijn|niet|bij|over|naar|uitleg|receptie|christelijke|joodse|tussen|deze)\b", 3),
           (r"\b(de|en|in|te|op)\b", 1)],
    "la": [(r"\b(apud|liber|libri|opera|omnia|secundum|atque|quaestiones|commentarii|editio|epistulae|fragmenta|adversus|hominis)\b", 3),
           (r"\b(de|in|ad|contra|super|et|ex|cum)\b", 1)],
}
COMPILED = {k: [(re.compile(p, re.I), w) for p, w in v] for k, v in MARKERS.items()}


def guess_language(text, min_score=3, margin=2):
    t = (text or "").strip()
    if len(t) < 12 or len(t.split()) < 3:
        return None
    scores = {}
    for lang, pats in COMPILED.items():
        scores[lang] = sum(len(p.findall(t)) * w for p, w in pats)
    ranked = sorted(scores.items(), key=lambda kv: -kv[1])
    best, bs = ranked[0]
    second_score = ranked[1][1]
    if bs < min_score or bs - second_score < margin:
        return None
    return best


if __name__ == "__main__":
    tests = [
        ("Origène face à l`altérité juive", "fr"),
        ("Des huit esprits de perversité d`Évagre du Pont", "fr"),
        ("La Bibbia negli scritti polemici di Gerolamo. Problemi e piste di ricerca", "it"),
        ("Jewish and Christian Academies in Roman Palestine: Some Preliminary Observations", "en"),
        ("El papel de la filosofía en la escuela teológica de Alejandría", "es"),
        ("Motivi paolini nell`epistolario di Gerolamo", "it"),
        ("La tradizione esegetica alessandrina sui Salmi: alla ricerca dell`Origene perduto", "it"),
        ("`Un astre se lèvera de Jacob`. L`interprétation ancienne de Nombres 24, 17", "fr"),
        ("La vie de saint Jean higoumène de Scété au VIIe siècle", "fr"),
        ("Apatheia bei den Stoikern und Akedia bei Evagrios Pontikos - ein Ideal und die Kehrseite seiner Realität?", "de"),
        ("Wisdom, Sense Perception, Nature, and Philo`s Gender Gradient", "en"),
        ("Het zelfbewustzijn van een bespotte minderheid. De receptie en uitleg van 1 Kor.", "nl"),
        ("Das Gebet bei Origenes", "de"),
        ("Der Septuaginta-Psalter als Dokument jüdischer Eschatologie", "de"),
        ("Théologie liturgique de Philon d`Alexandrie et d`Origène", "fr"),
        ("Hegemonikon in the Soul", "en"),
        ("Josephus and Philo", "en"),
    ]
    ok = 0
    for t, exp in tests:
        g = guess_language(t)
        flag = "ok " if g == exp else "XX "
        ok += g == exp
        print("%s%-6s exp=%-6s %s" % (flag, g, exp, t[:70]))
    print("%d/%d" % (ok, len(tests)))
