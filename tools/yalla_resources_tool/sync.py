from __future__ import annotations

import argparse
import shutil

from .emitters import generate
from .io import copy_file, replace_directory, sync_directory_contents
from .paths import COMPOSE_LOCALE_DIRS, ROOT
from .validation import validate


def clean_generated_android_strings(res_dir):
    if not res_dir.exists():
        return
    for path in res_dir.glob("values*/yalla_strings.xml"):
        path.unlink()


def clean_generated_android_icons(res_dir):
    drawable_dir = res_dir / "drawable"
    if not drawable_dir.exists():
        return
    for pattern in ["yalla_ic_*.xml", "ic_*.xml"]:
        for path in drawable_dir.glob(pattern):
            path.unlink()


def clean_generated_android_assets(res_dir):
    legacy_drawable_dir = res_dir / "drawable"
    if legacy_drawable_dir.exists():
        for path in legacy_drawable_dir.glob("img_*.png"):
            path.unlink()


def clean_generated_ios_legacy_assets(resources_dir):
    for directory in ("Drawables", "Images"):
        legacy_dir = resources_dir / directory
        if legacy_dir.exists():
            shutil.rmtree(legacy_dir)


def sync(args: argparse.Namespace) -> int:
    validation = validate(strict=False)
    if validation != 0:
        return validation

    generated = ROOT / "build/generated/sync"
    result = generate(generated)
    if result != 0:
        return result

    if not args.no_cmp:
        cmp_resources = args.cmp / "resources/src/commonMain/composeResources"
        cmp_icons = args.cmp / "resources/src/commonMain/valkyrieResources"
        for locale_dir in COMPOSE_LOCALE_DIRS.values():
            copy_file(
                generated / "compose/composeResources" / locale_dir / "strings.xml",
                cmp_resources / locale_dir / "strings.xml",
            )
        sync_directory_contents(
            generated / "compose/valkyrieResources",
            cmp_icons,
            "*.svg",
            prune=True,
        )
        for directory, pattern, prune in [
            ("drawable", "img_*.png", True),
            ("font", "*.ttf", False),
            ("files", "*.json", False),
        ]:
            sync_directory_contents(
                generated / "compose/composeResources" / directory,
                cmp_resources / directory,
                pattern,
                prune=prune,
            )
        print(f"Synced Compose strings to {cmp_resources}")
        print(f"Synced Compose icons to {cmp_icons}")
        print(f"Synced Compose assets to {cmp_resources}")

    if not args.no_android:
        android_res = args.android / "sdk/src/main/res"
        clean_generated_android_strings(android_res)
        clean_generated_android_icons(android_res)
        clean_generated_android_assets(android_res)
        for source in (generated / "android/res").glob("values*/strings.xml"):
            copy_file(source, android_res / source.parent.name / source.name)
        sync_directory_contents(
            generated / "android/res/drawable",
            android_res / "drawable",
            "ic_*.xml",
            prune=True,
        )
        for directory, pattern, prune in [
            ("drawable-nodpi", "img_*.png", True),
            ("font", "*.ttf", False),
            ("raw", "*.json", False),
        ]:
            sync_directory_contents(
                generated / "android/res" / directory,
                android_res / directory,
                pattern,
                prune=prune,
            )
        print(f"Synced Android strings to {android_res}")
        print(f"Synced Android icons to {android_res / 'drawable'}")
        print(f"Synced Android assets to {android_res}")

    if not args.no_ios:
        ios_resources = args.ios / "Sources/YallaResourcesIOS/Resources"
        ios_icons = ios_resources / "Icons"
        clean_generated_ios_legacy_assets(ios_resources)
        copy_file(
            generated / "ios/YallaResourcesIOS/YallaResourcesIOS.swift",
            args.ios / "Sources/YallaResourcesIOS/YallaResourcesIOS.swift",
        )
        copy_file(
            generated / "ios/YallaResourcesIOS/Resources/Localizable.xcstrings",
            ios_resources / "Localizable.xcstrings",
        )
        replace_directory(
            generated / "ios/YallaResourcesIOS/Resources/YallaImages.xcassets",
            ios_resources / "YallaImages.xcassets",
        )
        sync_directory_contents(
            generated / "ios/YallaResourcesIOS/Resources/Icons",
            ios_icons,
            "*.svg",
            prune=True,
        )
        for directory, pattern, prune in [
            ("Fonts", "*.ttf", False),
            ("Files", "*.json", False),
        ]:
            sync_directory_contents(
                generated / "ios/YallaResourcesIOS/Resources" / directory,
                ios_resources / directory,
                pattern,
                prune=prune,
            )
        print(f"Synced iOS strings to {ios_resources}")
        print(f"Synced iOS icons to {ios_icons}")
        print(f"Synced iOS assets to {ios_resources}")

    return 0

