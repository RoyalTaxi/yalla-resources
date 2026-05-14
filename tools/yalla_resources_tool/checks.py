from __future__ import annotations

import json
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from .emitters import generate
from .io import tree_snapshot
from .ios_assets import themed_image_pairs
from .paths import (
    ANDROID_LOCALE_DIRS,
    COMPOSE_LOCALE_DIRS,
    FILE_DIR,
    FONT_DIR,
    ICON_DIR,
    IMAGE_DIR,
)
from .validation import validate


def verify_generated_output(out: Path) -> list[str]:
    errors = []

    expected_icon_count = len(list(ICON_DIR.glob("*.svg")))
    expected_image_count = len(list(IMAGE_DIR.glob("*.png")))
    expected_ios_imageset_count = expected_image_count + len(themed_image_pairs())
    expected_font_count = len(list(FONT_DIR.glob("*.ttf")))
    expected_file_count = len(list(FILE_DIR.glob("*.json")))

    expected_counts = {
        "compose icons": (out / "compose/valkyrieResources", "*.svg", expected_icon_count),
        "android icons": (out / "android/res/drawable", "ic_*.xml", expected_icon_count),
        "ios icons": (out / "ios/YallaResourcesIOS/Resources/Icons", "*.svg", expected_icon_count),
        "compose images": (out / "compose/composeResources/drawable", "img_*.png", expected_image_count),
        "android images": (out / "android/res/drawable-nodpi", "img_*.png", expected_image_count),
        "ios image sets": (out / "ios/YallaResourcesIOS/Resources/YallaImages.xcassets", "*.imageset", expected_ios_imageset_count),
        "compose fonts": (out / "compose/composeResources/font", "*.ttf", expected_font_count),
        "android fonts": (out / "android/res/font", "*.ttf", expected_font_count),
        "ios fonts": (out / "ios/YallaResourcesIOS/Resources/Fonts", "*.ttf", expected_font_count),
        "compose files": (out / "compose/composeResources/files", "*.json", expected_file_count),
        "android raw files": (out / "android/res/raw", "*.json", expected_file_count),
        "ios files": (out / "ios/YallaResourcesIOS/Resources/Files", "*.json", expected_file_count),
    }

    for label, (directory, pattern, expected) in expected_counts.items():
        actual = len(list(directory.glob(pattern)))
        if actual != expected:
            errors.append(f"{label}: expected {expected}, got {actual}")

    for locale_dir in COMPOSE_LOCALE_DIRS.values():
        path = out / "compose/composeResources" / locale_dir / "strings.xml"
        if not path.exists():
            errors.append(f"missing Compose strings: {path.relative_to(out)}")
        else:
            ET.parse(path)

    for locale_dir in ANDROID_LOCALE_DIRS.values():
        path = out / "android/res" / locale_dir / "strings.xml"
        if not path.exists():
            errors.append(f"missing Android strings: {path.relative_to(out)}")
        else:
            ET.parse(path)

    android_latn_dir = out / "android/res/values-b+uz+Latn"
    if android_latn_dir.exists():
        errors.append("Android output must not generate values-b+uz+Latn")

    localizable = out / "ios/YallaResourcesIOS/Resources/Localizable.xcstrings"
    if not localizable.exists():
        errors.append("missing iOS Localizable.xcstrings")
    else:
        payload = json.loads(localizable.read_text())
        if payload.get("sourceLanguage") != "uz-Latn":
            errors.append("iOS Localizable.xcstrings sourceLanguage must be uz-Latn")

    ios_accessor = out / "ios/YallaResourcesIOS/YallaResourcesIOS.swift"
    if not ios_accessor.exists():
        errors.append("missing iOS resource accessor")

    ios_asset_catalog = out / "ios/YallaResourcesIOS/Resources/YallaImages.xcassets"
    if (ios_asset_catalog / "Contents.json").exists():
        json.loads((ios_asset_catalog / "Contents.json").read_text())
    else:
        errors.append("missing iOS image asset catalog Contents.json")
    for imageset in sorted(ios_asset_catalog.glob("*.imageset")):
        contents = imageset / "Contents.json"
        if not contents.exists():
            errors.append(f"missing iOS imageset Contents.json: {imageset.name}")
        else:
            json.loads(contents.read_text())

    for path in sorted((out / "android/res/drawable").glob("*.xml")):
        ET.parse(path)
        if path.name.startswith("yalla_"):
            errors.append(f"legacy Android icon prefix generated: {path.name}")

    return errors


def check(strict: bool) -> int:
    validation = validate(strict=strict)
    if validation != 0:
        return validation

    with tempfile.TemporaryDirectory() as first_tmp, tempfile.TemporaryDirectory() as second_tmp:
        first = Path(first_tmp) / "generated"
        second = Path(second_tmp) / "generated"
        generate(first)
        generate(second)

        errors = verify_generated_output(first)
        first_snapshot = tree_snapshot(first)
        second_snapshot = tree_snapshot(second)
        if first_snapshot != second_snapshot:
            first_paths = set(first_snapshot)
            second_paths = set(second_snapshot)
            missing = sorted(first_paths - second_paths)
            extra = sorted(second_paths - first_paths)
            changed = sorted(
                path for path in first_paths & second_paths
                if first_snapshot[path] != second_snapshot[path]
            )
            if missing:
                errors.append(f"idempotency: missing files on second run: {missing[:10]}")
            if extra:
                errors.append(f"idempotency: extra files on second run: {extra[:10]}")
            if changed:
                errors.append(f"idempotency: changed files on second run: {changed[:10]}")

    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)

    if errors:
        return 1

    print("Resource generator check passed")
    return 0

