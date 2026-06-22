from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CATALOG_PATH = ROOT / "strings/catalog.json"
DEFAULT_WORKSPACE = ROOT.parent

ASSET_ROOT = ROOT / "assets"
ICON_DIR = ASSET_ROOT / "icons"
IMAGE_DIR = ASSET_ROOT / "images"
FONT_DIR = ASSET_ROOT / "font"
FILE_DIR = ASSET_ROOT / "files"

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
IMAGE_NAME = re.compile(r"^img_[a-z0-9]+(?:_[a-z0-9]+)*\.png$")
FONT_NAME = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*\.ttf$")
FILE_NAME = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*\.json$")

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
