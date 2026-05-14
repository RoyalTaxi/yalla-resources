from __future__ import annotations

import json
import shutil
from pathlib import Path

from .io import write
from .paths import IMAGE_DIR


def asset_catalog_info() -> dict:
    return {
        "info": {
            "author": "xcode",
            "version": 1,
        },
    }


def image_entry(filename: str, luminosity: str | None = None) -> dict:
    entry = {
        "idiom": "universal",
        "filename": filename,
        "scale": "1x",
    }
    if luminosity:
        entry["appearances"] = [
            {
                "appearance": "luminosity",
                "value": luminosity,
            }
        ]
    return entry


def write_asset_contents(path: Path, images: list[dict]) -> None:
    payload = asset_catalog_info()
    payload["images"] = images
    write(path / "Contents.json", json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def copy_image_to_imageset(source: Path, imageset: Path) -> None:
    imageset.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, imageset / source.name)


def themed_image_pairs() -> dict[str, tuple[Path, Path]]:
    light_images = {
        path.stem.removeprefix("img_light_"): path
        for path in IMAGE_DIR.glob("img_light_*.png")
    }
    dark_images = {
        path.stem.removeprefix("img_dark_"): path
        for path in IMAGE_DIR.glob("img_dark_*.png")
    }
    return {
        suffix: (light_images[suffix], dark_images[suffix])
        for suffix in sorted(light_images.keys() & dark_images.keys())
    }


def generate_ios_image_asset_catalog(out: Path) -> None:
    catalog = out / "ios/YallaResourcesIOS/Resources/YallaImages.xcassets"
    if catalog.exists():
        shutil.rmtree(catalog)
    catalog.mkdir(parents=True, exist_ok=True)
    write(catalog / "Contents.json", json.dumps(asset_catalog_info(), ensure_ascii=False, indent=2) + "\n")

    for source in sorted(IMAGE_DIR.glob("*.png")):
        imageset = catalog / f"{source.stem}.imageset"
        copy_image_to_imageset(source, imageset)
        write_asset_contents(imageset, [image_entry(source.name)])

    for suffix, (light, dark) in themed_image_pairs().items():
        imageset = catalog / f"yalla_img_{suffix}.imageset"
        if imageset.exists():
            shutil.rmtree(imageset)
        copy_image_to_imageset(light, imageset)
        copy_image_to_imageset(dark, imageset)
        write_asset_contents(
            imageset,
            [
                image_entry(light.name),
                image_entry(dark.name, "dark"),
            ],
        )
