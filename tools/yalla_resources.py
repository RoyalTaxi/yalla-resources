#!/usr/bin/env python3
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "strings/catalog.json"
DEFAULT_WORKSPACE = ROOT.parent
ICON_DIR = ROOT / "assets/icons"
DRAWABLE_DIR = ROOT / "assets/drawable"
FONT_DIR = ROOT / "assets/font"
FILE_DIR = ROOT / "assets/files"
ANDROID_VECTOR_TOOL_DIR = ROOT / "build/android-vector-tool"
MAVEN_CACHE_DIR = ROOT / "build/maven"

ANDROID_TOOLS_VERSION = "32.2.1"
GUAVA_VERSION = "33.3.1-jre"
KOTLIN_STDLIB_VERSION = "2.2.10"
JETBRAINS_ANNOTATIONS_VERSION = "26.0.2-1"

GOOGLE_MAVEN = "https://dl.google.com/dl/android/maven2"
MAVEN_CENTRAL = "https://repo.maven.apache.org/maven2"

PLACEHOLDER = re.compile(r"\{(\d+)\}")
ICON_NAME = re.compile(r"^ic_[a-z0-9]+(?:_[a-z0-9]+)*\.svg$")
DRAWABLE_NAME = re.compile(r"^img_[a-z0-9]+(?:_[a-z0-9]+)*\.png$")
FONT_NAME = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*\.ttf$")
FILE_NAME = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*\.json$")

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


def maven_relative_path(group: str, artifact: str, version: str) -> Path:
    return Path(group.replace(".", "/")) / artifact / version / f"{artifact}-{version}.jar"


def maven_repository(group: str) -> str:
    if group.startswith("com.android."):
        return GOOGLE_MAVEN
    return MAVEN_CENTRAL


def find_module_jar(group: str, artifact: str, version: str) -> Path:
    module_dir = Path.home() / ".gradle/caches/modules-2/files-2.1" / group / artifact
    if not module_dir.exists():
        raise RuntimeError(f"Gradle cache is missing {group}:{artifact}")

    for jar in sorted((module_dir / version).glob(f"*/{artifact}-{version}.jar")):
        return jar

    raise RuntimeError(f"Gradle cache is missing {group}:{artifact}:{version} jar")


def download_module_jar(group: str, artifact: str, version: str) -> Path:
    relative = maven_relative_path(group, artifact, version)
    destination = MAVEN_CACHE_DIR / relative
    if destination.exists():
        return destination

    destination.parent.mkdir(parents=True, exist_ok=True)
    url = f"{maven_repository(group)}/{relative.as_posix()}"
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            with destination.open("wb") as output:
                shutil.copyfileobj(response, output)
    except (urllib.error.URLError, TimeoutError) as error:
        raise RuntimeError(
            f"Unable to fetch {group}:{artifact}:{version} from {url}. "
            "Run an Android build once to populate the Gradle cache, or retry with network access."
        ) from error

    return destination


def resolve_module_jar(group: str, artifact: str, version: str) -> Path:
    try:
        return find_module_jar(group, artifact, version)
    except RuntimeError:
        return download_module_jar(group, artifact, version)


def android_vector_classpath() -> tuple[list[Path], str]:
    sdk_common = resolve_module_jar("com.android.tools", "sdk-common", ANDROID_TOOLS_VERSION)
    common = resolve_module_jar("com.android.tools", "common", ANDROID_TOOLS_VERSION)
    annotations = resolve_module_jar("com.android.tools", "annotations", ANDROID_TOOLS_VERSION)
    guava = resolve_module_jar("com.google.guava", "guava", GUAVA_VERSION)
    kotlin_stdlib = resolve_module_jar("org.jetbrains.kotlin", "kotlin-stdlib", KOTLIN_STDLIB_VERSION)
    jetbrains_annotations = resolve_module_jar(
        "org.jetbrains",
        "annotations",
        JETBRAINS_ANNOTATIONS_VERSION,
    )
    return (
        [sdk_common, common, annotations, guava, kotlin_stdlib, jetbrains_annotations],
        ANDROID_TOOLS_VERSION,
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
    drawable_errors, drawable_warnings = validate_binary_assets(
        DRAWABLE_DIR,
        DRAWABLE_NAME,
        ".png",
        "drawable",
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
        drawable_errors + font_errors + file_errors,
        drawable_warnings + font_warnings + file_warnings,
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
            lines.append(f'    <string name="{key}"{attr}>{android_text(values[locale])}</string>\n')
        lines.append("</resources>\n")
        write(base / directory / "strings.xml", "".join(lines))


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


def generate_asset_files(out: Path) -> None:
    copy_directory_contents(
        DRAWABLE_DIR,
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
        DRAWABLE_DIR,
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

    copy_directory_contents(
        DRAWABLE_DIR,
        out / "ios/YallaResourcesIOS/Resources/Drawables",
        "*.png",
    )
    copy_directory_contents(
        FONT_DIR,
        out / "ios/YallaResourcesIOS/Resources/Fonts",
        "*.ttf",
    )
    copy_directory_contents(
        FILE_DIR,
        out / "ios/YallaResourcesIOS/Resources/Files",
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


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tree_snapshot(root: Path) -> dict:
    return {
        str(path.relative_to(root)): file_hash(path)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def verify_generated_output(out: Path) -> list:
    errors = []

    expected_icon_count = len(list(ICON_DIR.glob("*.svg")))
    expected_drawable_count = len(list(DRAWABLE_DIR.glob("*.png")))
    expected_font_count = len(list(FONT_DIR.glob("*.ttf")))
    expected_file_count = len(list(FILE_DIR.glob("*.json")))

    expected_counts = {
        "compose icons": (out / "compose/valkyrieResources", "*.svg", expected_icon_count),
        "android icons": (out / "android/res/drawable", "ic_*.xml", expected_icon_count),
        "ios icons": (out / "ios/YallaResourcesIOS/Resources/Icons", "*.svg", expected_icon_count),
        "compose drawables": (out / "compose/composeResources/drawable", "img_*.png", expected_drawable_count),
        "android drawables": (out / "android/res/drawable-nodpi", "img_*.png", expected_drawable_count),
        "ios drawables": (out / "ios/YallaResourcesIOS/Resources/Drawables", "img_*.png", expected_drawable_count),
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
    for pattern in ["yalla_ic_*.xml", "ic_*.xml"]:
        for path in drawable_dir.glob(pattern):
            path.unlink()


def clean_generated_android_assets(res_dir: Path) -> None:
    legacy_drawable_dir = res_dir / "drawable"
    if legacy_drawable_dir.exists():
        for path in legacy_drawable_dir.glob("img_*.png"):
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
        copy_file(
            generated / "ios/YallaResourcesIOS/Resources/Localizable.xcstrings",
            ios_resources / "Localizable.xcstrings",
        )
        sync_directory_contents(
            generated / "ios/YallaResourcesIOS/Resources/Icons",
            ios_icons,
            "*.svg",
            prune=True,
        )
        for directory, pattern, prune in [
            ("Drawables", "img_*.png", True),
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


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--strict", action="store_true")

    check_parser = subparsers.add_parser("check")
    check_parser.add_argument("--strict", action="store_true")

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
    if args.command == "check":
        return check(args.strict)
    if args.command == "generate":
        return generate(args.out)
    if args.command == "sync":
        return sync(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
