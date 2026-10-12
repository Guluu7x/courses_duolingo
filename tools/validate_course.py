#!/usr/bin/env python3
"""Validate a Duolingo-style course JSON and inject it into the engine template.

Usage:
    python scripts/build.py course.json -o course.html     # validate + build
    python scripts/build.py course.json --check            # validate only

Errors (exit code 1) block the build. Warnings print but still build;
read them anyway — they flag content-quality problems (answer bias,
long sentences, missing explanations).
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "assets" / "engine.html"
EX_TYPES = {"mcq", "tf", "match", "order", "numeric"}
STEP_TYPES = EX_TYPES | {"card"}
MAX_SENTENCE_WORDS = 25
MAX_CARD_WORDS = 90


def slug(s):
    s = re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    return s[:48] or "course"


def words(s):
    return len(re.findall(r"\S+", str(s or "")))


def long_sentences(text):
    plain = re.sub(r"[*`]", "", str(text or ""))
    plain = re.sub(r"(?m)^\s*[-*•]\s+", "", plain)
    parts = re.split(r"(?<=[.!?])\s+|\n+", plain)
    return [p.strip() for p in parts if words(p) > MAX_SENTENCE_WORDS]


class Report:
    def __init__(self):
        self.errors, self.warnings = [], []

    def err(self, where, msg):
        self.errors.append(f"{where}: {msg}")

    def warn(self, where, msg):
        self.warnings.append(f"{where}: {msg}")


def is_num(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def nonempty_str(x):
    return isinstance(x, str) and x.strip() != ""


def check_flag(r, where, flag):
    if flag is None:
        return
    if isinstance(flag, str):
        if not flag.strip():
            r.err(where, "'flag' is an empty string")
    elif isinstance(flag, dict):
        if not nonempty_str(flag.get("text")):
            r.err(where, "'flag' object needs a non-empty 'text'")
    else:
        r.err(where, "'flag' must be a string or {title, text}")


def check_extras(r, where, s):
    """Optional blocks any step (or ref) may carry: code, output, terms."""
    for k in ("code", "output", "codeCaption"):
        if k in s and not nonempty_str(s[k]):
            r.err(where, f"'{k}' must be a non-empty string")
    if "code" in s and isinstance(s["code"], str) and len(s["code"].splitlines()) > 18:
        r.warn(where, "code block is over 18 lines — long code reads badly on a phone; move it into a 'ref'")
    terms = s.get("terms")
    if terms is not None and (not isinstance(terms, list) or not terms
                              or not all(isinstance(x, list) and len(x) == 2 and all(nonempty_str(y) for y in x) for x in terms)):
        r.err(where, "'terms' must be a list of [中文, English] string pairs")


def check_step(r, where, s, tf_answers):
    if not isinstance(s, dict):
        r.err(where, "step must be an object")
        return
    t = s.get("type")
    if t not in STEP_TYPES:
        r.err(where, f"unknown type {t!r} (expected one of {sorted(STEP_TYPES)})")
        return
    check_flag(r, where, s.get("flag"))
    check_extras(r, where, s)
    refs = s.get("ref")
    if refs is not None:
        for i, ref in enumerate(refs if isinstance(refs, list) else [refs]):
            w = f"{where}.ref[{i}]"
            if not isinstance(ref, dict) or not nonempty_str(ref.get("title")):
                r.err(w, "'ref' must be {title, body?, code?, output?} (or a list of them) with a non-empty title")
                continue
            if not any(nonempty_str(ref.get(k)) for k in ("body", "code", "output", "equation")):
                r.err(w, "'ref' needs at least one of body / code / output")
            check_extras(r, w, ref)

    if t == "card":
        if not nonempty_str(s.get("body")):
            r.err(where, "card needs a non-empty 'body'")
        if not nonempty_str(s.get("title")):
            r.warn(where, "card has no 'title'")
        if words(s.get("body")) > MAX_CARD_WORDS:
            r.warn(where, f"card body is {words(s.get('body'))} words (aim for <= {MAX_CARD_WORDS}; split it)")
        for ls in long_sentences(s.get("body")):
            r.warn(where, f"long sentence ({words(ls)} words): \"{ls[:70]}…\"")
        if "equation" in s and not nonempty_str(s["equation"]):
            r.err(where, "'equation' must be a non-empty string")
        return

    # exercises
    if t != "tf" and not nonempty_str(s.get("prompt")):
        r.err(where, f"{t} needs a non-empty 'prompt'")
    for ls in long_sentences(s.get("prompt")):
        r.warn(where, f"long prompt sentence ({words(ls)} words)")
    if not nonempty_str(s.get("explain")):
        r.warn(where, "no 'explain' — learners see nothing after answering")

    if t == "mcq":
        opts = s.get("options")
        if not isinstance(opts, list) or not 2 <= len(opts) <= 6 or not all(nonempty_str(o) for o in opts):
            r.err(where, "mcq 'options' must be a list of 2-6 non-empty strings")
            return
        if len({o.strip().lower() for o in opts}) != len(opts):
            r.err(where, "mcq has duplicate options")
        a = s.get("answer")
        if not isinstance(a, int) or isinstance(a, bool) or not 0 <= a < len(opts):
            r.err(where, f"mcq 'answer' must be an index 0..{len(opts) - 1}")
        if len(opts) < 3:
            r.warn(where, "mcq with only 2 options — consider a tf step or add a distractor")
        for o in opts:
            if re.search(r"\b(all|none) of the above\b", o, re.I):
                r.warn(where, f"avoid '{o}' — options are shuffled")
        lens = [len(o) for o in opts]
        if isinstance(a, int) and 0 <= a < len(opts) and len(opts) >= 3:
            others = [l for i, l in enumerate(lens) if i != a]
            if lens[a] > 1.8 * max(others):
                r.warn(where, "the correct option is much longer than the distractors (a giveaway)")
        why = s.get("why")
        if why is not None and (not isinstance(why, list) or len(why) != len(opts)):
            r.err(where, "'why' must be a list the same length as 'options' (use \"\" for the correct one)")

    elif t == "tf":
        if not nonempty_str(s.get("statement")):
            r.err(where, "tf needs a non-empty 'statement'")
        if not isinstance(s.get("answer"), bool):
            r.err(where, "tf 'answer' must be true or false (JSON boolean)")
        else:
            tf_answers.append(s["answer"])

    elif t == "match":
        pairs = s.get("pairs")
        if (not isinstance(pairs, list) or not 2 <= len(pairs) <= 5
                or not all(isinstance(p, list) and len(p) == 2 and all(nonempty_str(x) for x in p) for p in pairs)):
            r.err(where, "match 'pairs' must be 2-5 [left, right] string pairs")
            return
        for side, name in ((0, "left"), (1, "right")):
            vals = [p[side].strip().lower() for p in pairs]
            if len(set(vals)) != len(vals):
                r.err(where, f"match has duplicate {name} items")

    elif t == "order":
        items = s.get("items")
        if not isinstance(items, list) or not 3 <= len(items) <= 8 or not all(nonempty_str(i) for i in items):
            r.err(where, "order 'items' must be 3-8 non-empty strings, listed in the CORRECT order")
            return
        if len({i.strip().lower() for i in items}) != len(items):
            r.err(where, "order has duplicate items")

    elif t == "numeric":
        a = s.get("answer")
        if not is_num(a):
            r.err(where, "numeric 'answer' must be a number (compute it in Python, don't round by hand)")
        tol = s.get("tolerance", 0.01)
        if not is_num(tol) or not 0 < tol < 1:
            r.err(where, "numeric 'tolerance' is RELATIVE (e.g. 0.02 = ±2%) and must be between 0 and 1")
        elif tol > 0.15:
            r.warn(where, f"tolerance {tol} (±{tol * 100:g}%) is very loose")
        if is_num(a) and a == 0:
            r.warn(where, "answer is 0 — tolerance is then treated as an absolute margin")
        if "unit" in s and not isinstance(s["unit"], str):
            r.err(where, "'unit' must be a string")


def validate(course):
    r = Report()
    if not isinstance(course, dict):
        r.err("course", "top level must be an object")
        return r
    if not nonempty_str(course.get("title")):
        r.err("course", "needs a non-empty 'title'")
    units = course.get("units")
    if not isinstance(units, list) or not units:
        r.err("course", "needs a non-empty 'units' list")
        return r
    if not 4 <= len(units) <= 8:
        r.warn("course", f"{len(units)} units — the home path is designed for 4-8")
    tutor = course.get("tutor")
    if tutor is not None and not isinstance(tutor, dict):
        r.err("course", "'tutor' must be an object {model?, context?}")
    elif not tutor or not nonempty_str(tutor.get("context")):
        r.warn("course", "no tutor.context — give the tutor a 2-4 sentence summary of the source")

    seen_ids, prompts = set(), {}
    tf_answers, total_ex = [], 0
    for ui, u in enumerate(units):
        uw = f"unit[{ui}]"
        if not isinstance(u, dict):
            r.err(uw, "must be an object")
            continue
        if not nonempty_str(u.get("title")):
            r.err(uw, "needs a 'title'")
        lessons = u.get("lessons")
        if not isinstance(lessons, list) or not lessons:
            r.err(uw, "needs a non-empty 'lessons' list")
            continue
        for li, l in enumerate(lessons):
            lw = f"{uw}.lesson[{li}]"
            if not isinstance(l, dict):
                r.err(lw, "must be an object")
                continue
            if not nonempty_str(l.get("title")):
                r.err(lw, "needs a 'title'")
            lid = l.get("id")
            if lid is not None:
                if lid in seen_ids:
                    r.err(lw, f"duplicate lesson id {lid!r}")
                seen_ids.add(lid)
            steps = l.get("steps")
            if not isinstance(steps, list) or not steps:
                r.err(lw, "needs a non-empty 'steps' list")
                continue
            n_ex = sum(1 for s in steps if isinstance(s, dict) and s.get("type") in EX_TYPES)
            total_ex += n_ex
            if n_ex == 0:
                r.warn(lw, "has no exercises")
            if len(steps) > 14:
                r.warn(lw, f"{len(steps)} steps — lessons feel best at 6-12; split it")
            if isinstance(steps[-1], dict) and steps[-1].get("type") == "card":
                r.warn(lw, "ends on a card — end on an exercise so the card gets tested")
            for si, s in enumerate(steps):
                sw = f"{lw}.step[{si}]"
                check_step(r, sw, s, tf_answers)
                if isinstance(s, dict):
                    p = (s.get("prompt") or s.get("statement") or "").strip().lower()
                    if p and s.get("type") in EX_TYPES and s.get("type") not in ("match", "order"):
                        if p in prompts:
                            r.warn(sw, f"same prompt as {prompts[p]}")
                        prompts.setdefault(p, sw)

    if len(tf_answers) >= 4:
        t = sum(tf_answers)
        if t / len(tf_answers) > 0.75 or t / len(tf_answers) < 0.25:
            r.warn("course", f"true/false answers are lopsided ({t} true, {len(tf_answers) - t} false) — mix them")
    if total_ex == 0:
        r.err("course", "no exercises anywhere")
    return r


def normalize(course):
    """Fill in ids the engine needs. Mutates and returns course."""
    course.setdefault("id", slug(course.get("title", "course")))
    for ui, u in enumerate(course["units"]):
        u.setdefault("id", f"u{ui + 1}")
        for li, l in enumerate(u["lessons"]):
            l.setdefault("id", f"{u['id']}-l{li + 1}")
    return course


def build(course, out_path):
    template = ENGINE.read_text(encoding="utf-8")
    if "__COURSE_JSON__" not in template:
        raise SystemExit(f"engine template is missing the __COURSE_JSON__ placeholder: {ENGINE}")
    data = json.dumps(course, ensure_ascii=False, separators=(",", ":"))
    # Keep the JSON inert inside <script>: no "</script>" or "<!--" sequences.
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = (template
            .replace("__COURSE_TITLE__", html.escape(course["title"]), 1)
            .replace("__COURSE_JSON__", data, 1))
    Path(out_path).write_text(page, encoding="utf-8")
    return len(page.encode("utf-8"))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("course", help="course JSON file")
    ap.add_argument("-o", "--out", help="output HTML (default: <course>.html)")
    ap.add_argument("--check", action="store_true", help="validate only")
    args = ap.parse_args()

    try:
        course = json.loads(Path(args.course).read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: {args.course} is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    r = validate(course)
    for w in r.warnings:
        print(f"WARNING {w}")
    for e in r.errors:
        print(f"ERROR   {e}")

    n_units = len(course.get("units") or []) if isinstance(course, dict) else 0
    n_lessons = sum(len(u.get("lessons") or []) for u in course.get("units") or [] if isinstance(u, dict)) if isinstance(course, dict) else 0
    n_steps = sum(len(l.get("steps") or []) for u in course.get("units") or [] if isinstance(u, dict)
                  for l in u.get("lessons") or [] if isinstance(l, dict)) if isinstance(course, dict) else 0
    print(f"\n{n_units} units · {n_lessons} lessons · {n_steps} steps · "
          f"{len(r.errors)} error(s) · {len(r.warnings)} warning(s)")

    if r.errors:
        print("Build aborted — fix the errors above.")
        sys.exit(1)
    if args.check:
        return
    out = args.out or str(Path(args.course).with_suffix(".html"))
    size = build(normalize(course), out)
    print(f"Built {out} ({size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
