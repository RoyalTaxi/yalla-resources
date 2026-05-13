# yalla-resources

Canonical resource source for Yalla SDKs.

This repo owns resource inputs that need to be shared across:

- `yalla-sdk` Compose Multiplatform resources
- `yalla-sdk-android` native Android resources
- `yalla-sdk-ios` native iOS resources

The platform repos should consume generated outputs. Resource changes should be
made here first, then generated into each platform's native resource format.

## Current Scope

The implemented workflow covers strings, canonical SVG icons, PNG drawables,
fonts, and JSON file resources:

```text
strings/catalog.json
    +-> Compose Multiplatform strings.xml
    +-> Android strings.xml
    +-> iOS Localizable.xcstrings

assets/icons/*.svg
    +-> Compose Multiplatform valkyrieResources/*.svg
    +-> Android VectorDrawable res/drawable/ic_*.xml
    +-> iOS bundled Resources/Icons/*.svg

assets/drawable/*.png
    +-> Compose Multiplatform composeResources/drawable/*.png
    +-> Android res/drawable-nodpi/img_*.png
    +-> iOS bundled Resources/Drawables/*.png

assets/font/*.ttf
    +-> Compose Multiplatform composeResources/font/*.ttf
    +-> Android res/font/*.ttf
    +-> iOS bundled Resources/Fonts/*.ttf

assets/files/*.json
    +-> Compose Multiplatform composeResources/files/*.json
    +-> Android res/raw/*.json
    +-> iOS bundled Resources/Files/*.json
```

All generated resource files should be updated through this repo.

## Locales

| Canonical locale | Meaning | Source mapping |
| --- | --- | --- |
| `default` | Default fallback text | CMP `values` |
| `en` | English | CMP `values-en` |
| `ru` | Russian | CMP `values-ru` |
| `uz-Latn` | Uzbek Latin | CMP `values-uz` |
| `uz-Cyrl` | Uzbek Cyrillic | CMP `values-be` workaround |

`values-be` is intentionally treated only as a Compose Multiplatform workaround.
Native generated outputs use Uzbek Cyrillic locale identifiers.

## Commands

Validate the catalog and source assets:

```bash
python3 tools/yalla_resources.py validate
```

Run the full generator check. This validates resources, generates twice into
temporary directories, verifies expected output paths/counts, parses generated
XML/JSON, and checks byte-for-byte idempotency:

```bash
python3 tools/yalla_resources.py check --strict
```

Generate sample outputs into `build/generated`:

```bash
python3 tools/yalla_resources.py generate --out build/generated
```

Android icon generation uses a pinned Android Gradle Plugin `Svg2Vector`
converter (`com.android.tools:sdk-common:32.2.1`). The script first reuses the
local Gradle cache, then downloads missing pinned jars into `build/maven`.

Sync generated outputs into sibling repos:

```bash
python3 tools/yalla_resources.py sync
```

The default sync paths assume this checkout sits next to:

- `/Users/islom/StudioProjects/yalla-sdk`
- `/Users/islom/StudioProjects/yalla-sdk-android`
- `/Users/islom/StudioProjects/yalla-sdk-ios`

Use `--no-cmp`, `--no-android`, or `--no-ios` to skip a target.

Seed this repo again from the current `yalla-sdk/resources` Compose source:

```bash
python3 tools/import_from_yalla_sdk.py /Users/islom/StudioProjects/yalla-sdk/resources
```
