from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

from .paths import CATALOG_PATH

def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text())

def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)

def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

def copy_directory_contents(source: Path, destination: Path, pattern: str = "*") -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob(pattern)):
        if path.is_file():
            shutil.copy2(path, destination / path.name)

def sync_directory_contents(source: Path, destination: Path, pattern: str, prune: bool = False) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    if prune:
        source_names = {path.name for path in source.glob(pattern) if path.is_file()}
        for path in sorted(destination.glob(pattern)):
            if path.is_file() and path.name not in source_names:
                path.unlink()
    for path in sorted(source.glob(pattern)):
        if path.is_file():
            shutil.copy2(path, destination / path.name)

def replace_directory(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    shutil.copytree(source, destination)

def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()

def tree_snapshot(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): file_hash(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }
