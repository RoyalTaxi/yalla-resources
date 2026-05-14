from __future__ import annotations

import os
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

from .io import write
from .paths import (
    ANDROID_TOOLS_VERSION,
    ANDROID_VECTOR_RUNNER,
    ANDROID_VECTOR_TOOL_DIR,
    GOOGLE_MAVEN,
    GUAVA_VERSION,
    JETBRAINS_ANNOTATIONS_VERSION,
    KOTLIN_STDLIB_VERSION,
    MAVEN_CACHE_DIR,
    MAVEN_CENTRAL,
    ROOT,
)


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

