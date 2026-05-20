from __future__ import annotations

import argparse
import os
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from html import escape
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import yaml
from jinja2 import Environment, FileSystemLoader, select_autoescape


ROOT_DIR = Path(__file__).resolve().parent
INPUT_DIR = ROOT_DIR / "input"
IMAGES_DIR = ROOT_DIR / "images"
OUTPUT_DIR = ROOT_DIR / "output"
TEMPLATES_DIR = ROOT_DIR / "templates"
TEMPLATE_NAME = "compare_template.html"
TEMPLATE_PATH = TEMPLATES_DIR / TEMPLATE_NAME

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".svg"}
PLACEHOLDER_STEM = "default-placeholder"


@dataclass
class ImageItem:
    src: Optional[str]
    caption: str
    is_placeholder: bool = False


@dataclass
class ModuleItem:
    index: int
    code: str
    name: str
    content_html: str
    images: List[ImageItem]


@dataclass
class DocumentData:
    title: str
    file_name: str
    yaml_stem: str
    metadata_html: str
    modules: List[ModuleItem]


@dataclass
class Counters:
    generated: int = 0
    skipped: int = 0
    failed: int = 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch convert layout YAML files into side-by-side HTML pages."
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate matched YAML files even when output is up to date.",
    )
    parser.add_argument(
        "--file",
        dest="file_name",
        help="Only process one YAML file. Accepts a file name, stem, .yaml, or .yml.",
    )
    parser.add_argument(
        "--new-only",
        action="store_true",
        help="Only generate HTML files that do not already exist.",
    )
    return parser.parse_args()


def find_yaml_files(file_name: Optional[str]) -> Tuple[List[Path], bool]:
    if not INPUT_DIR.exists():
        print(f"ERROR: input directory does not exist: {INPUT_DIR}")
        return [], False

    if file_name:
        yaml_path = resolve_yaml_file(file_name)
        if yaml_path is None:
            print(f"ERROR: YAML file not found in input/: {file_name}")
            return [], False
        return [yaml_path], True

    files = sorted(
        [path for path in INPUT_DIR.iterdir() if path.is_file() and path.suffix.lower() in {".yaml", ".yml"}],
        key=lambda path: path.name.lower(),
    )
    if not files:
        print(f"ERROR: no YAML files found in input/: {INPUT_DIR}")
        return [], False
    return files, True


def resolve_yaml_file(file_name: str) -> Optional[Path]:
    raw = Path(file_name).name
    candidate = INPUT_DIR / raw
    if candidate.suffix.lower() in {".yaml", ".yml"}:
        return candidate if candidate.exists() and candidate.is_file() else None

    for suffix in (".yaml", ".yml"):
        candidate = INPUT_DIR / f"{raw}{suffix}"
        if candidate.exists() and candidate.is_file():
            return candidate
    return None


def find_default_placeholder() -> Optional[Path]:
    if not IMAGES_DIR.exists():
        return None

    placeholders = [
        path
        for path in IMAGES_DIR.iterdir()
        if path.is_file()
        and path.stem.lower() == PLACEHOLDER_STEM
        and path.suffix.lower() in IMAGE_EXTENSIONS
    ]
    placeholders.sort(key=lambda path: path.name.lower())
    for path in placeholders:
        if is_readable_image(path):
            return path
    return None


def should_generate(
    yaml_path: Path,
    output_path: Path,
    placeholder_path: Optional[Path],
    force: bool,
    new_only: bool,
) -> bool:
    if force:
        print(f"FORCE: regenerating {yaml_path.name}")
        return True

    if new_only:
        if output_path.exists():
            print(f"SKIP: {yaml_path.name} already has output")
            return False
        return True

    if not output_path.exists():
        return True

    output_mtime = output_path.stat().st_mtime
    watched_paths = [yaml_path, TEMPLATE_PATH]
    if placeholder_path is not None:
        watched_paths.append(placeholder_path)

    for watched_path in watched_paths:
        if watched_path.exists() and watched_path.stat().st_mtime > output_mtime:
            return True

    image_dir = IMAGES_DIR / yaml_path.stem
    if image_dir.exists():
        for image_path in iter_image_files(image_dir):
            try:
                if image_path.stat().st_mtime > output_mtime:
                    return True
            except OSError:
                continue

    print(f"SKIP: {yaml_path.name} is up to date")
    return False


def iter_image_files(directory: Path) -> Iterable[Path]:
    if not directory.exists():
        return []
    return (
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def image_sort_key(path: Path) -> Tuple[int, int, str]:
    match = re.search(r"(\d+)(?!.*\d)", path.stem)
    if match:
        return 0, int(match.group(1)), path.name.lower()
    return 1, 0, path.name.lower()


def load_yaml(path: Path) -> Any:
    with path.open("r", encoding="utf-8-sig") as handle:
        return yaml.safe_load(handle)


def split_document(data: Any, fallback_title: str) -> Tuple[str, Dict[str, Any], List[Tuple[str, Any]]]:
    if isinstance(data, dict) and len(data) == 1:
        root_name, root_value = next(iter(data.items()))
        title = str(root_name)
        if isinstance(root_value, dict):
            modules = [(str(key), value) for key, value in root_value.items() if isinstance(value, dict)]
            metadata = {str(key): value for key, value in root_value.items() if not isinstance(value, dict)}
            if modules:
                return title, metadata, modules
            return title, {}, [(str(key), value) for key, value in root_value.items()]
        return title, {}, [(title, root_value)]

    if isinstance(data, dict):
        return fallback_title, {}, [(str(key), value) for key, value in data.items()]

    return fallback_title, {}, [("内容", data)]


def render_yaml_node(value: Any) -> str:
    if isinstance(value, dict):
        parts = ['<dl class="yaml-dict">']
        for key, item in value.items():
            parts.append(f"<dt>{escape(str(key))}</dt>")
            parts.append(f"<dd>{render_yaml_node(item)}</dd>")
        parts.append("</dl>")
        return "".join(parts)

    if isinstance(value, list):
        if not value:
            return '<span class="yaml-empty">-</span>'
        parts = ['<ul class="yaml-list">']
        for item in value:
            parts.append(f"<li>{render_yaml_node(item)}</li>")
        parts.append("</ul>")
        return "".join(parts)

    if value is None:
        return '<span class="yaml-empty">-</span>'

    if isinstance(value, bool):
        return f'<span class="yaml-value yaml-bool">{str(value).lower()}</span>'

    return f'<span class="yaml-value">{escape(str(value))}</span>'


def is_readable_image(path: Path) -> bool:
    try:
        if not path.exists() or not path.is_file() or path.stat().st_size <= 0:
            return False
        suffix = path.suffix.lower()
        if suffix == ".svg":
            ET.parse(path)
            return True

        with path.open("rb") as handle:
            header = handle.read(16)

        if suffix == ".png":
            return header.startswith(b"\x89PNG\r\n\x1a\n")
        if suffix in {".jpg", ".jpeg"}:
            return header.startswith(b"\xff\xd8")
        if suffix == ".webp":
            return header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    except (OSError, ET.ParseError):
        return False
    return False


def relative_url(from_file: Path, target: Path) -> str:
    relative = Path(os.path.relpath(target, start=from_file.parent))
    return relative.as_posix()


def get_module_images(
    yaml_stem: str,
    module_index: int,
    output_path: Path,
    placeholder_path: Optional[Path],
) -> List[ImageItem]:
    chapter_dir = IMAGES_DIR / yaml_stem / f"ch{module_index}"
    found_images: List[Path] = []

    if chapter_dir.exists() and chapter_dir.is_dir():
        candidates = [
            path
            for path in chapter_dir.iterdir()
            if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
        ]
        for path in sorted(candidates, key=image_sort_key):
            if is_readable_image(path):
                found_images.append(path)
            else:
                print(f"WARN: unreadable image skipped: {path}")

    if found_images:
        return [
            ImageItem(
                src=relative_url(output_path, image_path),
                caption=f"图 {index}",
                is_placeholder=False,
            )
            for index, image_path in enumerate(found_images, start=1)
        ]

    if placeholder_path is not None:
        return [
            ImageItem(
                src=relative_url(output_path, placeholder_path),
                caption="暂无配图",
                is_placeholder=True,
            )
        ]

    return [ImageItem(src=None, caption="暂无配图", is_placeholder=True)]


def build_document(yaml_path: Path, output_path: Path, placeholder_path: Optional[Path]) -> DocumentData:
    data = load_yaml(yaml_path)
    title, metadata, module_pairs = split_document(data, yaml_path.stem)
    modules: List[ModuleItem] = []

    for index, (name, content) in enumerate(module_pairs, start=1):
        modules.append(
            ModuleItem(
                index=index,
                code=f"ch{index}",
                name=name,
                content_html=render_yaml_node(content),
                images=get_module_images(yaml_path.stem, index, output_path, placeholder_path),
            )
        )

    metadata_html = render_yaml_node(metadata) if metadata else ""
    return DocumentData(
        title=title,
        file_name=yaml_path.name,
        yaml_stem=yaml_path.stem,
        metadata_html=metadata_html,
        modules=modules,
    )


def render_html(document: DocumentData) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=select_autoescape(["html", "xml"]),
    )
    template = env.get_template(TEMPLATE_NAME)
    return template.render(document=document)


def process_yaml(yaml_path: Path, placeholder_path: Optional[Path]) -> bool:
    output_path = OUTPUT_DIR / f"{yaml_path.stem}.html"
    document = build_document(yaml_path, output_path, placeholder_path)
    html = render_html(document)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html, encoding="utf-8")
    print(f"GENERATED: {yaml_path.name} -> {output_path.relative_to(ROOT_DIR)}")
    return True


def validate_project() -> bool:
    if not TEMPLATE_PATH.exists():
        print(f"ERROR: template does not exist: {TEMPLATE_PATH}")
        return False
    if not TEMPLATES_DIR.exists():
        print(f"ERROR: templates directory does not exist: {TEMPLATES_DIR}")
        return False
    return True


def main() -> int:
    args = parse_args()
    counters = Counters()

    if not validate_project():
        return 1

    yaml_files, ok = find_yaml_files(args.file_name)
    if not ok:
        return 1

    placeholder_path = find_default_placeholder()
    if placeholder_path is None:
        print("WARN: default-placeholder image was not found or is unreadable; gray placeholder boxes will be used.")

    for yaml_path in yaml_files:
        output_path = OUTPUT_DIR / f"{yaml_path.stem}.html"
        try:
            if not should_generate(
                yaml_path=yaml_path,
                output_path=output_path,
                placeholder_path=placeholder_path,
                force=args.force,
                new_only=args.new_only,
            ):
                counters.skipped += 1
                continue

            process_yaml(yaml_path, placeholder_path)
            counters.generated += 1
        except Exception as exc:
            counters.failed += 1
            print(f"FAILED: {yaml_path.name}: {exc}")

    print()
    print("Done.")
    print(f"Generated: {counters.generated}")
    print(f"Skipped: {counters.skipped}")
    print(f"Failed: {counters.failed}")
    return 1 if counters.failed else 0


if __name__ == "__main__":
    sys.exit(main())
