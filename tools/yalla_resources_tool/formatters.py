from __future__ import annotations

from xml.sax.saxutils import escape as xml_escape

from .paths import PLACEHOLDER


def placeholders(value: str) -> list[str]:
    return sorted(set(PLACEHOLDER.findall(value)), key=int)


def _positional_format(value: str, conversion: str) -> str:
    """Rewrite canonical ``{N}`` placeholders into 1-indexed positional format
    args (``%(N+1)$<conversion>``), escaping literal percent signs first so they
    survive the runtime formatter."""
    escaped = value.replace("%", "%%")
    return PLACEHOLDER.sub(lambda match: f"%{int(match.group(1)) + 1}${conversion}", escaped)


def android_format(value: str) -> str:
    return _positional_format(value, "s")


def compose_format(value: str) -> str:
    # Compose Resources substitutes args with the same java.util.Formatter-style
    # positional tokens Android uses (SimpleStringFormatRegex = %(\\d+)\\$[ds]);
    # args are toString()-ed first, so the ``$s`` conversion is always correct.
    return android_format(value)


def ios_format(value: str) -> str:
    return _positional_format(value, "@")


def xml_text(value: str) -> str:
    return xml_escape(value, {'"': "&quot;"})


def android_text(value: str) -> str:
    escaped = xml_text(android_format(value))
    return escaped.replace("'", "\\'")


def compose_text(value: str) -> str:
    # Compose strings.xml shares Android's escaping rules (apostrophes escaped,
    # XML entities encoded), so a Compose value is emitted identically.
    escaped = xml_text(compose_format(value))
    return escaped.replace("'", "\\'")


def xml_header() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<!-- Generated from RoyalTaxi/yalla-resources. Do not edit by hand. -->\n"
        "<resources>\n"
    )
