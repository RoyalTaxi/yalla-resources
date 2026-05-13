#!/usr/bin/env python3
import json
import shutil
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

LOCALE_DIRS = {
    "values": "default",
    "values-en": "en",
    "values-ru": "ru",
    "values-uz": "uz-Latn",
    "values-be": "uz-Cyrl",
}

LOCALE_META = {
    "default": {
        "name": "Default fallback",
        "source": "composeResources/values",
        "nativeLocale": None,
    },
    "en": {
        "name": "English",
        "source": "composeResources/values-en",
        "nativeLocale": "en",
    },
    "ru": {
        "name": "Russian",
        "source": "composeResources/values-ru",
        "nativeLocale": "ru",
    },
    "uz-Latn": {
        "name": "Uzbek Latin",
        "source": "composeResources/values-uz",
        "nativeLocale": "uz-Latn",
    },
    "uz-Cyrl": {
        "name": "Uzbek Cyrillic",
        "source": "composeResources/values-be",
        "nativeLocale": "uz-Cyrl",
        "note": "Compose Multiplatform currently stores this as values-be.",
    },
}


def read_strings(path: Path) -> dict:
    tree = ET.parse(path)
    values = {}
    for node in tree.getroot():
        if node.tag != "string":
            continue
        key = node.attrib["name"]
        values[key] = {
            "value": "".join(node.itertext()),
            "translatable": node.attrib.get("translatable") != "false",
        }
    return values


def import_strings(resources_dir: Path) -> None:
    compose_dir = resources_dir / "src/commonMain/composeResources"
    catalog = {
        "version": 1,
        "sourceLocale": "uz-Latn",
        "locales": LOCALE_META,
        "strings": {},
    }

    default_values = read_strings(compose_dir / "values/strings.xml")
    for key, entry in default_values.items():
        catalog["strings"][key] = {
            "translatable": entry["translatable"],
            "values": {
                "default": entry["value"],
            },
        }

    for directory, locale in LOCALE_DIRS.items():
        if locale == "default":
            continue
        path = compose_dir / directory / "strings.xml"
        if not path.exists():
            continue
        for key, entry in read_strings(path).items():
            if key not in catalog["strings"]:
                catalog["strings"][key] = {
                    "translatable": entry["translatable"],
                    "values": {},
                }
            catalog["strings"][key]["values"][locale] = entry["value"]

    output = ROOT / "strings/catalog.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n")


def copy_tree(source: Path, destination: Path, pattern: str = "*") -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for existing in destination.glob("*"):
        if existing.is_dir():
            shutil.rmtree(existing)
        else:
            existing.unlink()
    for item in sorted(source.glob(pattern)):
        if item.is_file():
            shutil.copy2(item, destination / item.name)


def import_assets(resources_dir: Path) -> None:
    common = resources_dir / "src/commonMain"
    compose = common / "composeResources"
    copy_tree(common / "valkyrieResources", ROOT / "assets/icons", "*.svg")
    copy_tree(compose / "drawable", ROOT / "assets/drawable")
    copy_tree(compose / "font", ROOT / "assets/font")
    copy_tree(compose / "files", ROOT / "assets/files")


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: import_from_yalla_sdk.py /path/to/yalla-sdk/resources", file=sys.stderr)
        return 2

    resources_dir = Path(sys.argv[1]).expanduser().resolve()
    if not (resources_dir / "src/commonMain/composeResources").exists():
        print(f"Invalid resources module path: {resources_dir}", file=sys.stderr)
        return 2

    import_strings(resources_dir)
    import_assets(resources_dir)
    print(f"Imported resources from {resources_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
