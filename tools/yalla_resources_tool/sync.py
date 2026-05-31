from __future__ import annotations

import argparse
import shutil

from .emitters import generate
from .io import copy_file, replace_directory, sync_directory_contents
from .paths import COMPOSE_LOCALE_DIRS, ROOT
from .validation import validate


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
        # Changed target from sdk module to resources module
        android_res = args.android / "resources/src/main/res"
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
        print(f"Synced Android resources to {android_res}")

    if not args.no_ios:
        ios_resources = args.ios / "Sources/Resources/Resources"
        copy_file(
            generated / "ios/Resources/YallaResources.swift",
            args.ios / "Sources/Resources/YallaResources.swift",
        )
        copy_file(
            generated / "ios/Resources/Resources/Localizable.xcstrings",
            ios_resources / "Localizable.xcstrings",
        )
        replace_directory(
            generated / "ios/Resources/Resources/YallaImages.xcassets",
            ios_resources / "YallaImages.xcassets",
        )
        replace_directory(
            generated / "ios/Resources/Resources/YallaIcons.xcassets",
            ios_resources / "YallaIcons.xcassets",
        )
        for directory, pattern, prune in [
            ("Fonts", "*.ttf", False),
            ("Files", "*.json", False),
        ]:
            sync_directory_contents(
                generated / "ios/Resources/Resources" / directory,
                ios_resources / directory,
                pattern,
                prune=prune,
            )
        print(f"Synced iOS strings to {ios_resources}")
        print(f"Synced iOS assets to {ios_resources}")

    return 0
