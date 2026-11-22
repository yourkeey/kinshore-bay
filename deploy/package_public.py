"""Create a public demo archive from the allowlisted runtime files."""
import argparse
import json
from pathlib import Path
import re
from zipfile import ZIP_DEFLATED, ZipFile

ROOT = Path(__file__).resolve().parents[1]
SITE_FILES = (
    "index.html", "miniapp.html", "style.css", "site.js", "miniapp.js", "club-guide.js", "apartment-details.js",
)
RUNTIME_FILES = (
    ".dockerignore", "crm/manage.py", "crm/requirements.txt", "content/en.json",
    "deploy/Dockerfile", "deploy/public.compose.yaml", "deploy/public.proxy.compose.yaml",
    "deploy/Caddyfile", "deploy/PUBLIC-DEMO.md", "deploy/public.env.example",
)


def release_paths():
    pages = [ROOT / "site" / name for name in SITE_FILES]
    sources = [page.read_text(encoding="utf-8") for page in pages]
    entry_points = {name for source in sources[:2] for name in re.findall(r'\b(?:src|href)="\./([\w.-]+\.(?:css|js))"', source)}
    if missing := entry_points.difference(SITE_FILES):
        raise ValueError(f"Page dependencies missing from the release: {', '.join(sorted(missing))}")
    assets = {name for source in sources for name in re.findall(r"assets/([\w.-]+\.(?:webp|svg))", source)}
    catalog = json.loads((ROOT / "content/en.json").read_text(encoding="utf-8"))
    assets.update(room["image"] for room in catalog["apartments"])
    if any(not re.fullmatch(r"[\w.-]+\.(?:webp|svg)", asset) for asset in assets):
        raise ValueError("Catalog images must be local, allowlisted asset types.")
    source_files = [path for folder in ("crm/config", "crm/reception") for path in (ROOT / folder).rglob("*.py")]
    templates = (ROOT / "crm/reception/templates").rglob("*.html")
    paths = {*pages, *source_files, *templates, *(ROOT / name for name in RUNTIME_FILES),
             *(ROOT / "site/assets" / name for name in assets)}
    for path in paths:
        if not path.is_file() or path.resolve() != path:
            raise ValueError(f"Missing or redirected release file: {path.relative_to(ROOT)}")
    return sorted(path.relative_to(ROOT) for path in paths)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Destination ZIP archive")
    output = parser.parse_args().output
    paths = release_paths()
    with ZipFile(output, "x", compression=ZIP_DEFLATED) as archive:
        for path in paths:
            archive.write(ROOT / path, path.as_posix())
    print(f"Packaged {len(paths)} allowlisted files in {output}.")
