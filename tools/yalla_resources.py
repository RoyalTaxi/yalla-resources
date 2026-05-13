#!/usr/bin/env python3
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "strings/catalog.json"
DEFAULT_WORKSPACE = ROOT.parent
ICON_DIR = ROOT / "assets/icons"
ANDROID_VECTOR_TOOL_DIR = ROOT / "build/android-vector-tool"

PLACEHOLDER = re.compile(r"\{(\d+)\}")
ICON_NAME = re.compile(r"^ic_[a-z0-9]+(?:_[a-z0-9]+)*\.svg$")

ANDROID_VECTOR_RUNNER = """\
import com.android.ide.common.vectordrawable.Svg2Vector;
import java.io.FileOutputStream;
import java.nio.file.Path;

public final class YallaSvgToVector {
    public static void main(String[] args) throws Exception {
        if (args.length != 2) {
            throw new IllegalArgumentException("Usage: YallaSvgToVector <input.svg> <output.xml>");
        }

        try (FileOutputStream out = new FileOutputStream(args[1])) {
            String messages = Svg2Vector.parseSvgToXml(Path.of(args[0]), out);
            if (!messages.isEmpty()) {
                System.err.print(messages);
            }
        }
    }
}
"""

COMPOSE_LOCALE_DIRS = {
    "default": "values",
    "en": "values-en",
    "ru": "values-ru",
    "uz-Latn": "values-uz",
    "uz-Cyrl": "values-be",
}

ANDROID_LOCALE_DIRS = {
    "default": "values",
    "en": "values-en",
    "ru": "values-ru",
    "uz-Latn": "values-b+uz+Latn",
    "uz-Cyrl": "values-b+uz+Cyrl",
}

IOS_LOCALE_IDS = {
    "default": "uz-Latn",
    "en": "en",
    "ru": "ru",
    "uz-Latn": "uz-Latn",
    "uz-Cyrl": "uz-Cyrl",
}


def load_catalog() -> dict:
    return json.loads(CATALOG_PATH.read_text())


def placeholders(value: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(value)), key=int)


def android_format(value: str) -> str:
    escaped = value.replace("%", "%%")
    return PLACEHOLDER.sub(lambda match: f"%{int(match.group(1)) + 1}$s", escaped)


def ios_format(value: str) -> str:
    escaped = value.replace("%", "%%")
    return PLACEHOLDER.sub(lambda match: f"%{int(match.group(1)) + 1}$@", escaped)


def xml_text(value: str) -> str:
    return xml_escape(value, {'"': "&quot;"})


def android_text(value: str) -> str:
    escaped = xml_text(android_format(value))
    return escaped.replace("'", "\\'")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def version_key(version: str) -> tuple[str, ...]:
    parts = re.split(r"[.-]", version)
    return tuple(part.zfill(8) if part.isdigit() else part for part in parts)


def find_module_jar(group: str, artifact: str, version=None) -> tuple[Path, str]:
    module_dir = Path.home() / ".gradle/caches/modules-2/files-2.1" / group / artifact
    if not module_dir.exists():
        raise RuntimeError(f"Gradle cache is missing {group}:{artifact}")

    versions = [version] if version else sorted(
        [path.name for path in module_dir.iterdir() if path.is_dir()],
        key=version_key,
        reverse=True,
    )

    for candidate_version in versions:
        for jar in sorted((module_dir / candidate_version).glob(f"*/{artifact}-{candidate_version}.jar")):
            return jar, candidate_version

    requested = f":{version}" if version else ""
    raise RuntimeError(f"Gradle cache is missing {group}:{artifact}{requested} jar")


def android_vector_classpath() -> tuple[list[Path], str]:
    sdk_common, sdk_version = find_module_jar("com.android.tools", "sdk-common")
    common, _ = find_module_jar("com.android.tools", "common", sdk_version)
    annotations, _ = find_module_jar("com.android.tools", "annotations", sdk_version)
    guava, _ = find_module_jar("com.google.guava", "guava")
    kotlin_stdlib, _ = find_module_jar("org.jetbrains.kotlin", "kotlin-stdlib")
    jetbrains_annotations, _ = find_module_jar("org.jetbrains", "annotations")
    return (
        [sdk_common, common, annotations, guava, kotlin_stdlib, jetbrains_annotations],
        sdk_version,
    )


def ensure_android_vector_runner() -> tuple[Path, str]:
    if not shutil.which("java") or not shutil.which("javac"):
        raise RuntimeError("Android vector generation requires java and javac on PATH")

    jars, _ = android_vector_classpath()
    classpath = os.pathsep.join(str(path) for path in jars)
    source = ANDROID_VECTOR_TOOL_DIR / "YallaSvgToVector.java"
    class_file = ANDROID_VECTOR_TOOL_DIR / "YallaSvgToVector.class"

    write(source, ANDROID_VECTOR_RUNNER)
    if not class_file.exists() or source.stat().st_mtime > class_file.stat().st_mtime:
        subprocess.run(
            ["javac", "-cp", classpath, str(source)],
            check=True,
            cwd=ROOT,
        )

    return ANDROID_VECTOR_TOOL_DIR, classpath


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

        generated_name = f"yalla_{path.stem}"
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


def validate(strict: bool) -> int:
    string_errors, string_warnings = validate_strings()
    icon_errors, icon_warnings = validate_icons()
    errors = string_errors + icon_errors
    warnings = string_warnings + icon_warnings

    for message in errors:
        print(f"ERROR: {message}", file=sys.stderr)
    for message in warnings:
        print(f"WARN: {message}", file=sys.stderr)

    if errors or (strict and warnings):
        return 1
    return 0


def xml_header() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- Generated from RoyalTaxi/yalla-resources. Do not edit by hand. -->\n"
        "<resources>\n"
    )


def generate_compose(out: Path, catalog: dict) -> None:
    base = out / "compose/composeResources"
    for locale, directory in COMPOSE_LOCALE_DIRS.items():
        lines = [xml_header()]
        for key, entry in catalog["strings"].items():
            values = entry["values"]
            if locale not in values:
                continue
            if locale != "default" and not entry.get("translatable", True):
                continue
            attr = ' translatable="false"' if locale == "default" and not entry.get("translatable", True) else ""
            lines.append(f'    <string name="{key}"{attr}>{xml_text(values[locale])}</string>\n')
        lines.append("</resources>\n")
        write(base / directory / "strings.xml", "".join(lines))


def generate_android(out: Path, catalog: dict) -> None:
    base = out / "android/res"
    for locale, directory in ANDROID_LOCALE_DIRS.items():
        lines = [xml_header()]
        for key, entry in catalog["strings"].items():
            values = entry["values"]
            if locale not in values:
                continue
            if locale != "default" and not entry.get("translatable", True):
                continue
            attr = ' translatable="false"' if locale == "default" and not entry.get("translatable", True) else ""
            lines.append(f'    <string name="yalla_{key}"{attr}>{android_text(values[locale])}</string>\n')
        lines.append("</resources>\n")
        write(base / directory / "yalla_strings.xml", "".join(lines))


def generate_ios(out: Path, catalog: dict) -> None:
    strings = {}
    for key, entry in catalog["strings"].items():
        item = {
            "extractionState": "manual",
            "localizations": {},
        }
        if not entry.get("translatable", True):
            item["shouldTranslate"] = False

        for locale, value in entry["values"].items():
            ios_locale = IOS_LOCALE_IDS[locale]
            if ios_locale in item["localizations"]:
                continue
            if locale != "default" and not entry.get("translatable", True):
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
        out / "ios/YallaResourcesIOS/Resources/Localizable.xcstrings",
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    )


def copy_directory_contents(source: Path, destination: Path, pattern: str = "*") -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.mkdir(parents=True, exist_ok=True)
    for path in sorted(source.glob(pattern)):
        if path.is_file():
            shutil.copy2(path, destination / path.name)


def generate_icons(out: Path) -> None:
    copy_directory_contents(
        ICON_DIR,
        out / "compose/valkyrieResources",
        "*.svg",
    )
    copy_directory_contents(
        ICON_DIR,
        out / "ios/YallaResourcesIOS/Resources/Icons",
        "*.svg",
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
        destination = drawable_dir / f"yalla_{source.stem}.xml"
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
    print(f"Generated resources into {out}")
    return 0


def copy_file(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def clean_generated_android_strings(res_dir: Path) -> None:
    if not res_dir.exists():
        return
    for path in res_dir.glob("values*/yalla_strings.xml"):
        path.unlink()


def clean_generated_android_icons(res_dir: Path) -> None:
    drawable_dir = res_dir / "drawable"
    if not drawable_dir.exists():
        return
    for path in drawable_dir.glob("yalla_ic_*.xml"):
        path.unlink()


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
        copy_directory_contents(
            generated / "compose/valkyrieResources",
            cmp_icons,
            "*.svg",
        )
        print(f"Synced Compose strings to {cmp_resources}")
        print(f"Synced Compose icons to {cmp_icons}")

    if not args.no_android:
        android_res = args.android / "sdk/src/main/res"
        clean_generated_android_strings(android_res)
        clean_generated_android_icons(android_res)
        for source in (generated / "android/res").glob("values*/yalla_strings.xml"):
            copy_file(source, android_res / source.parent.name / source.name)
        for source in (generated / "android/res/drawable").glob("yalla_ic_*.xml"):
            copy_file(source, android_res / "drawable" / source.name)
        print(f"Synced Android strings to {android_res}")
        print(f"Synced Android icons to {android_res / 'drawable'}")

    if not args.no_ios:
        ios_resources = args.ios / "Sources/YallaResourcesIOS/Resources"
        ios_icons = ios_resources / "Icons"
        copy_file(
            generated / "ios/YallaResourcesIOS/Resources/Localizable.xcstrings",
            ios_resources / "Localizable.xcstrings",
        )
        copy_directory_contents(
            generated / "ios/YallaResourcesIOS/Resources/Icons",
            ios_icons,
            "*.svg",
        )
        print(f"Synced iOS strings to {ios_resources}")
        print(f"Synced iOS icons to {ios_icons}")

    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--strict", action="store_true")

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--out", type=Path, default=ROOT / "build/generated")

    sync_parser = subparsers.add_parser("sync")
    sync_parser.add_argument(
        "--cmp",
        type=Path,
        default=DEFAULT_WORKSPACE / "yalla-sdk",
        help="Path to the yalla-sdk repo. Use --no-cmp to skip.",
    )
    sync_parser.add_argument(
        "--android",
        type=Path,
        default=DEFAULT_WORKSPACE / "yalla-sdk-android",
        help="Path to the yalla-sdk-android repo. Use --no-android to skip.",
    )
    sync_parser.add_argument(
        "--ios",
        type=Path,
        default=DEFAULT_WORKSPACE / "yalla-sdk-ios",
        help="Path to the yalla-sdk-ios repo. Use --no-ios to skip.",
    )
    sync_parser.add_argument("--no-cmp", action="store_true")
    sync_parser.add_argument("--no-android", action="store_true")
    sync_parser.add_argument("--no-ios", action="store_true")

    args = parser.parse_args()
    if args.command == "validate":
        return validate(args.strict)
    if args.command == "generate":
        return generate(args.out)
    if args.command == "sync":
        return sync(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
