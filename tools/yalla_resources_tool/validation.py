from __future__ import annotations

import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from .formatters import placeholders
from .io import load_catalog
from .paths import (
    FILE_DIR,
    FILE_NAME,
    FONT_DIR,
    FONT_NAME,
    ICON_DIR,
    ICON_NAME,
    IMAGE_DIR,
    IMAGE_NAME,
    ROOT,
)

def validate_strings() -> tuple[list[str], list[str]]:
    catalog = load_catalog()
    locales = [locale for locale in catalog["locales"] if locale != "default"]
    errors = []
    warnings = []

    for key, entry in catalog["strings"].items():
        values = entry.get("values", {})
        if "default" not in values:
            errors.append(f"{key}: missing default value")
            continue

        default_placeholders = placeholders(values["default"])

        for locale, value in values.items():
            actual = placeholders(value)
            if actual != default_placeholders:
                errors.append(
                    f"{key}: placeholder mismatch for {locale}: "
                    f"expected {default_placeholders}, got {actual}"
                )

        if entry.get("translatable", True):
            for locale in locales:
                if locale not in values:
                    warnings.append(f"{key}: missing translation for {locale}")

    return errors, warnings

def validate_icons() -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    generated_names = set()

    if not ICON_DIR.exists():
        errors.append(f"missing icon directory: {ICON_DIR}")
        return errors, warnings

    for path in sorted(ICON_DIR.iterdir()):
        relative = path.relative_to(ROOT)
        if path.is_dir():
            warnings.append(f"ignoring icon subdirectory: {relative}")
            continue
        if path.suffix != ".svg":
            errors.append(f"{relative}: icon sources must be SVG files")
            continue
        if not ICON_NAME.match(path.name):
            errors.append(f"{relative}: icon name must be lower snake_case and start with ic_")

        generated_name = path.stem
        if generated_name in generated_names:
            errors.append(f"{relative}: duplicate generated name {generated_name}")
        generated_names.add(generated_name)

        try:
            root = ET.parse(path).getroot()
        except ET.ParseError as error:
            errors.append(f"{relative}: invalid SVG XML: {error}")
            continue
        if not root.tag.endswith("svg"):
            errors.append(f"{relative}: root element must be svg")

    if not generated_names:
        errors.append("no icons found")

    return errors, warnings

def validate_binary_assets(
    directory: Path,
    pattern: re.Pattern,
    expected_suffix: str,
    description: str,
    magic=None,
) -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    generated_names = set()

    if not directory.exists():
        errors.append(f"missing {description} directory: {directory}")
        return errors, warnings

    for path in sorted(directory.iterdir()):
        relative = path.relative_to(ROOT)
        if path.is_dir():
            warnings.append(f"ignoring {description} subdirectory: {relative}")
            continue
        if path.suffix != expected_suffix:
            errors.append(f"{relative}: {description} sources must be {expected_suffix} files")
            continue
        if not pattern.match(path.name):
            errors.append(f"{relative}: invalid {description} resource name")

        if path.stem in generated_names:
            errors.append(f"{relative}: duplicate generated name {path.stem}")
        generated_names.add(path.stem)

        if magic is not None:
            header = path.read_bytes()[:8]
            if not any(header.startswith(candidate) for candidate in magic):
                errors.append(f"{relative}: invalid {description} file header")

    if not generated_names:
        errors.append(f"no {description} resources found")

    return errors, warnings

def validate_file_assets() -> tuple[list[str], list[str]]:
    errors = []
    warnings = []
    generated_names = set()

    if not FILE_DIR.exists():
        errors.append(f"missing file resource directory: {FILE_DIR}")
        return errors, warnings

    for path in sorted(FILE_DIR.iterdir()):
        relative = path.relative_to(ROOT)
        if path.is_dir():
            warnings.append(f"ignoring file resource subdirectory: {relative}")
            continue
        if path.suffix != ".json":
            errors.append(f"{relative}: file resources must be JSON files")
            continue
        if not FILE_NAME.match(path.name):
            errors.append(f"{relative}: invalid file resource name")

        if path.stem in generated_names:
            errors.append(f"{relative}: duplicate generated name {path.stem}")
        generated_names.add(path.stem)

        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as error:
            errors.append(f"{relative}: invalid JSON: {error}")

    if not generated_names:
        errors.append("no file resources found")

    return errors, warnings

def validate_assets() -> tuple[list[str], list[str]]:
    image_errors, image_warnings = validate_binary_assets(
        IMAGE_DIR,
        IMAGE_NAME,
        ".png",
        "image",
        (b"\x89PNG\r\n\x1a\n",),
    )
    font_errors, font_warnings = validate_binary_assets(
        FONT_DIR,
        FONT_NAME,
        ".ttf",
        "font",
        (b"\x00\x01\x00\x00", b"true", b"ttcf"),
    )
    file_errors, file_warnings = validate_file_assets()
    return (
        image_errors + font_errors + file_errors,
        image_warnings + font_warnings + file_warnings,
    )

def validate(strict: bool) -> int:
    string_errors, string_warnings = validate_strings()
    icon_errors, icon_warnings = validate_icons()
    asset_errors, asset_warnings = validate_assets()
    errors = string_errors + icon_errors + asset_errors
    warnings = string_warnings + icon_warnings + asset_warnings

    for message in errors:
        print(f"ERROR: {message}", file=sys.stderr)
    for message in warnings:
        print(f"WARN: {message}", file=sys.stderr)

    if errors or (strict and warnings):
        return 1
    return 0
