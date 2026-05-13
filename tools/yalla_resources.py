#!/usr/bin/env python3
import argparse
import json
import re
import shutil
import sys
from pathlib import Path
from xml.sax.saxutils import escape as xml_escape


ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = ROOT / "strings/catalog.json"

PLACEHOLDER = re.compile(r"\{(\d+)\}")

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
    return PLACEHOLDER.sub(lambda match: f"%{int(match.group(1)) + 1}$s", value)


def ios_format(value: str) -> str:
    return PLACEHOLDER.sub(lambda match: f"%{int(match.group(1)) + 1}$@", value)


def xml_text(value: str) -> str:
    return xml_escape(value, {'"': "&quot;"})


def android_text(value: str) -> str:
    escaped = xml_text(android_format(value))
    return escaped.replace("'", "\\'")


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def validate(strict: bool) -> int:
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

    for message in errors:
        print(f"ERROR: {message}", file=sys.stderr)
    for message in warnings:
        print(f"WARN: {message}", file=sys.stderr)

    if errors or (strict and warnings):
        return 1
    return 0


def xml_header() -> str:
    return '<?xml version="1.0" encoding="UTF-8"?>\n<resources>\n'


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


def generate(out: Path) -> int:
    catalog = load_catalog()
    if out.exists():
        shutil.rmtree(out)
    generate_compose(out, catalog)
    generate_android(out, catalog)
    generate_ios(out, catalog)
    print(f"Generated resources into {out}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--strict", action="store_true")

    generate_parser = subparsers.add_parser("generate")
    generate_parser.add_argument("--out", type=Path, default=ROOT / "build/generated")

    args = parser.parse_args()
    if args.command == "validate":
        return validate(args.strict)
    if args.command == "generate":
        return generate(args.out)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
