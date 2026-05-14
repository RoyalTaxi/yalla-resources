from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

from .paths import PLACEHOLDER


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


def xml_header() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- Generated from RoyalTaxi/yalla-resources. Do not edit by hand. -->\n"
        "<resources>\n"
    )

