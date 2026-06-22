from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .android_vector import ensure_android_vector_runner
from .formatters import android_text, compose_text, ios_format, xml_header
from .io import copy_directory_contents, load_catalog, write
from .ios_assets import generate_ios_image_asset_catalog, generate_ios_icon_asset_catalog
from .paths import (
    ANDROID_LOCALE_DIRS,
    COMPOSE_LOCALE_DIRS,
    FILE_DIR,
    FONT_DIR,
    ICON_DIR,
    IMAGE_DIR,
    IOS_LOCALE_IDS,
    ROOT,
)


def _is_translatable(entry: dict) -> bool:
    return entry.get("translatable", True)


def _emits_locale(entry: dict, locale: str) -> bool:
    """The single source of truth for which (string, locale) pairs are emitted.

    Every platform shares this rule: a string is emitted in its ``default``
    locale always, and in any other locale only when the string is marked
    translatable. Untranslatable strings (e.g. ``app_name``) therefore appear
    only once -- in the default bucket -- on Compose, Android, and iOS alike.
    """
    if locale not in entry["values"]:
        return False
    return locale == "default" or _is_translatable(entry)


def _generate_xml_strings(
    out: Path,
    catalog: dict,
    base: Path,
    locale_dirs: dict,
    text: Callable[[str], str],
) -> None:
    """Emit Android-style ``<resources>`` string tables, one per locale dir.

    Compose and Android share an identical file shape and traversal; they differ
    only in the output root, the locale->directory map, and the per-value text
    escaper (``compose_text`` / ``android_text``). Parameterizing those three
    keeps the placeholder/escaping/skip logic in exactly one place.
    """
    for locale, directory in locale_dirs.items():
        lines = [xml_header()]
        for key, entry in catalog["strings"].items():
            if not _emits_locale(entry, locale):
                continue
            attr = ' translatable="false"' if locale == "default" and not _is_translatable(entry) else ""
            lines.append(f'    <string name="{key}"{attr}>{text(entry["values"][locale])}</string>\n')
        lines.append("</resources>\n")
        write(base / directory / "strings.xml", "".join(lines))


def generate_compose(out: Path, catalog: dict) -> None:
    _generate_xml_strings(out, catalog, out / "compose/composeResources", COMPOSE_LOCALE_DIRS, compose_text)


def generate_android(out: Path, catalog: dict) -> None:
    _generate_xml_strings(out, catalog, out / "android/res", ANDROID_LOCALE_DIRS, android_text)


def generate_ios(out: Path, catalog: dict) -> None:
    strings = {}
    for key, entry in catalog["strings"].items():
        item = {
            "extractionState": "manual",
            "localizations": {},
        }
        if not _is_translatable(entry):
            item["shouldTranslate"] = False

        for locale, value in entry["values"].items():
            if not _emits_locale(entry, locale):
                continue
            ios_locale = IOS_LOCALE_IDS[locale]
            # ``default`` and ``uz-Latn`` collapse to the same iOS id; the first
            # one in catalog order (``default``) wins, matching legacy output.
            if ios_locale in item["localizations"]:
                continue
            item["localizations"][ios_locale] = {
                "stringUnit": {
                    "state": "translated",
                    "value": ios_format(value),
                }
            }
        strings[key] = item

    payload = {
        "sourceLanguage": catalog["sourceLocale"],
        "strings": strings,
        "version": "1.0",
    }
    write(
        out / "ios/Resources/Resources/Localizable.xcstrings",
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )
    generate_ios_accessor(out)


def generate_ios_accessor(out: Path) -> None:
    write(
        out / "ios/Resources/YallaResources.swift",
        """import Foundation
import SwiftUI
#if canImport(UIKit)
import UIKit
#elseif canImport(AppKit)
import AppKit
#endif

/// Native iOS resource accessors generated from the canonical Yalla resources.
public enum YallaResources {
    public static let bundle = Bundle.module

    public static func localizedString(
        _ key: String,
        tableName: String? = nil,
        value: String = "",
        comment: String = ""
    ) -> String {
        NSLocalizedString(
            key,
            tableName: tableName,
            bundle: bundle,
            value: value,
            comment: comment
        )
    }

    public static func imageAssetName(_ name: String) -> String {
        stripExtension(name, extension: "png")
    }

    public static func iconAssetName(_ name: String) -> String {
        stripExtension(name, extension: "svg")
    }

    #if canImport(UIKit)
    public static func platformImage(
        _ name: String,
        compatibleWith traitCollection: UITraitCollection? = nil
    ) -> UIImage? {
        UIImage(
            named: imageAssetName(name),
            in: bundle,
            compatibleWith: traitCollection
        )
    }

    public static func platformIcon(
        _ name: String,
        compatibleWith traitCollection: UITraitCollection? = nil
    ) -> UIImage? {
        UIImage(
            named: iconAssetName(name),
            in: bundle,
            compatibleWith: traitCollection
        )
    }
    #elseif canImport(AppKit)
    public static func platformImage(_ name: String) -> NSImage? {
        bundle.image(forResource: NSImage.Name(imageAssetName(name)))
    }

    public static func platformIcon(_ name: String) -> NSImage? {
        bundle.image(forResource: NSImage.Name(iconAssetName(name)))
    }
    #endif

    @available(iOS 13.0, macOS 10.15, *)
    public static func swiftUIImage(_ name: String) -> Image {
        Image(imageAssetName(name), bundle: bundle)
    }

    @available(iOS 13.0, macOS 10.15, *)
    public static func swiftUIIcon(_ name: String) -> Image {
        Image(iconAssetName(name), bundle: bundle)
    }

    public static func fontURL(_ name: String) -> URL? {
        resourceURL(name, withExtension: "ttf", subdirectory: "Fonts")
    }

    public static func fileURL(_ name: String, withExtension fileExtension: String) -> URL? {
        resourceURL(name, withExtension: fileExtension, subdirectory: "Files")
    }

    private static func resourceURL(
        _ name: String,
        withExtension fileExtension: String,
        subdirectory: String
    ) -> URL? {
        let normalizedName = stripExtension(name, extension: fileExtension)
        return bundle.url(
            forResource: normalizedName,
            withExtension: fileExtension,
            subdirectory: subdirectory
        ) ?? bundle.url(
            forResource: normalizedName,
            withExtension: fileExtension
        )
    }

    private static func stripExtension(_ name: String, extension fileExtension: String) -> String {
        let suffix = ".\\(fileExtension)"
        return name.hasSuffix(suffix) ? String(name.dropLast(suffix.count)) : name
    }
}
""",
    )


def generate_icons(out: Path) -> None:
    copy_directory_contents(
        ICON_DIR,
        out / "compose/valkyrieResources",
        "*.svg",
    )
    generate_ios_icon_asset_catalog(out)


def generate_asset_files(out: Path) -> None:
    copy_directory_contents(
        IMAGE_DIR,
        out / "compose/composeResources/drawable",
        "*.png",
    )
    copy_directory_contents(
        FONT_DIR,
        out / "compose/composeResources/font",
        "*.ttf",
    )
    copy_directory_contents(
        FILE_DIR,
        out / "compose/composeResources/files",
        "*.json",
    )

    copy_directory_contents(
        IMAGE_DIR,
        out / "android/res/drawable-nodpi",
        "*.png",
    )
    copy_directory_contents(
        FONT_DIR,
        out / "android/res/font",
        "*.ttf",
    )
    copy_directory_contents(
        FILE_DIR,
        out / "android/res/raw",
        "*.json",
    )

    generate_ios_image_asset_catalog(out)
    copy_directory_contents(
        FONT_DIR,
        out / "ios/Resources/Resources/Fonts",
        "*.ttf",
    )
    copy_directory_contents(
        FILE_DIR,
        out / "ios/Resources/Resources/Files",
        "*.json",
    )


def add_generated_comment(path: Path) -> None:
    content = path.read_text()
    path.write_text(
        "<!-- Generated from RoyalTaxi/yalla-resources. Do not edit by hand. -->\n"
        + content
    )


def generate_android_icons(out: Path) -> None:
    runner_dir, classpath = ensure_android_vector_runner()
    drawable_dir = out / "android/res/drawable"
    if drawable_dir.exists():
        shutil.rmtree(drawable_dir)
    drawable_dir.mkdir(parents=True, exist_ok=True)

    warnings = []
    java_classpath = os.pathsep.join([str(runner_dir), classpath])
    for source in sorted(ICON_DIR.glob("*.svg")):
        destination = drawable_dir / f"{source.stem}.xml"
        result = subprocess.run(
            [
                "java",
                "-cp",
                java_classpath,
                "YallaSvgToVector",
                str(source),
                str(destination),
            ],
            check=False,
            capture_output=True,
            text=True,
            cwd=ROOT,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(f"{source.relative_to(ROOT)}: Android vector conversion failed: {message}")
        if not destination.exists() or destination.stat().st_size == 0:
            raise RuntimeError(f"{source.relative_to(ROOT)}: Android vector conversion produced no output")
        add_generated_comment(destination)
        if result.stderr.strip() or result.stdout.strip():
            warnings.append(source.name)

    if warnings:
        print(
            "WARN: Android vector conversion reported SVG feature limitations for "
            f"{len(warnings)} icon(s): {', '.join(warnings)}",
            file=sys.stderr,
        )


def generate(out: Path) -> int:
    catalog = load_catalog()
    if out.exists():
        shutil.rmtree(out)
    generate_compose(out, catalog)
    generate_android(out, catalog)
    generate_ios(out, catalog)
    generate_icons(out)
    generate_android_icons(out)
    generate_asset_files(out)
    print(f"Generated resources into {out}")
    return 0
