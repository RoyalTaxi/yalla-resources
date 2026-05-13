# yalla-resources

Canonical resource source for Yalla SDKs.

This repo owns resource inputs that need to be shared across:

- `yalla-sdk` Compose Multiplatform resources
- `yalla-sdk-android` native Android resources
- `yalla-sdk-ios` native iOS resources

The platform repos should consume generated outputs. Resource changes should be
made here first, then generated into each platform's native resource format.

## Current Scope

The first implemented workflow is strings-only:

```text
strings/catalog.json
    +-> Compose Multiplatform strings.xml
    +-> Android strings.xml
    +-> iOS Localizable.xcstrings
```

Images, icons, fonts, and files are seeded as source assets under `assets/`.
Generators for those assets will be added after the string pipeline is stable.

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

Validate the catalog:

```bash
python3 tools/yalla_resources.py validate
```

Generate sample outputs into `build/generated`:

```bash
python3 tools/yalla_resources.py generate --out build/generated
```

Seed this repo again from the current `yalla-sdk/resources` Compose source:

```bash
python3 tools/import_from_yalla_sdk.py /Users/islom/StudioProjects/yalla-sdk/resources
```

