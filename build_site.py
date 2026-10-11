#!/usr/bin/env python3
"""Build the course site: validate every course in courses/catalog.json and
bundle them into one index.html, plus the home-screen app files.

Usage:
    python3 build_site.py            # validate + build
    python3 build_site.py --check    # validate only
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))
from validate_course import validate, normalize  # noqa: E402

SITE_TITLE = "编程闯关"
ENGINE = ROOT / "src" / "engine.html"
CATALOG = ROOT / "courses" / "catalog.json"


def main():
    check_only = "--check" in sys.argv
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    courses, failed, ids = [], False, set()
    for entry in catalog:
        path = ROOT / "courses" / entry["file"]
        course = json.loads(path.read_text(encoding="utf-8"))
        r = validate(course)
        print(f"\n== {entry['file']} ==")
        for w in r.warnings:
            print(f"WARNING {w}")
        for e in r.errors:
            print(f"ERROR   {e}")
        if r.errors:
            failed = True
            continue
        course = normalize(course)
        if course["id"] in ids:
            print(f"ERROR   duplicate course id {course['id']!r}")
            failed = True
            continue
        ids.add(course["id"])
        course["icon"] = entry.get("icon", "📘")
        course["short"] = entry.get("short", course["title"])
        n_lessons = sum(len(u["lessons"]) for u in course["units"])
        n_ex = sum(1 for u in course["units"] for l in u["lessons"] for s in l["steps"] if s["type"] != "card")
        print(f"ok: {len(course['units'])} units · {n_lessons} lessons · {n_ex} exercises")
        courses.append(course)

    if failed:
        sys.exit("\nBuild aborted — fix the errors above.")
    if check_only:
        return

    data = json.dumps(courses, ensure_ascii=False, separators=(",", ":"))
    data = data.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    page = ENGINE.read_text(encoding="utf-8").replace("__SITE_TITLE__", SITE_TITLE).replace("__COURSES_JSON__", data, 1)
    (ROOT / "index.html").write_text(page, encoding="utf-8")

    manifest = {
        "name": SITE_TITLE, "short_name": SITE_TITLE, "lang": "zh-CN",
        "start_url": "./", "scope": "./", "display": "standalone",
        "background_color": "#ffffff", "theme_color": "#58cc02",
        "icons": [
            {"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "icon-512.png", "sizes": "512x512", "type": "image/png"},
        ],
    }
    (ROOT / "manifest.webmanifest").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nBuilt index.html with {len(courses)} course(s), {len(page.encode()) / 1024:.0f} KB")


if __name__ == "__main__":
    main()
