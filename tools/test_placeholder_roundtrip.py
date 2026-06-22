from __future__ import annotations

import html
import json
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from yalla_resources_tool.emitters import generate_android, generate_compose, generate_ios
from yalla_resources_tool.io import load_catalog
from yalla_resources_tool.paths import IOS_LOCALE_IDS, PLACEHOLDER

PARAM_KEY = "bonus_balance"
ARG = "1500"

def _positional_args_runtime(template: str, args: list[str], token: re.Pattern) -> str:
    return token.sub(lambda m: args[int(m.group(1)) - 1], template)

COMPOSE_TOKEN = re.compile(r"%(\d+)\$[ds]")
ANDROID_TOKEN = re.compile(r"%(\d+)\$[ds]")
IOS_TOKEN = re.compile(r"%(\d+)\$[@d]")

def _catalog_value(key: str) -> str:
    return load_catalog()["strings"][key]["values"]["default"]

def _expected(value: str) -> str:
    return PLACEHOLDER.sub(lambda m: ARG, value)

def _unescape_android(text: str) -> str:
    return text.replace("\\'", "'").replace('\\"', '"')

class PlaceholderRoundTripTests(unittest.TestCase):
    def setUp(self) -> None:
        self.value = _catalog_value(PARAM_KEY)
        self.assertIn("{0}", self.value, f"{PARAM_KEY} is not parameterized")
        self.expected = _expected(self.value)

    def _compose_template(self, out: Path) -> str:
        generate_compose(out, load_catalog())
        path = out / "compose/composeResources/values/strings.xml"
        node = ET.parse(path).getroot().find(f"./string[@name='{PARAM_KEY}']")
        self.assertIsNotNone(node, f"{PARAM_KEY} missing from Compose output")
        return _unescape_android(node.text)

    def _android_template(self, out: Path) -> str:
        generate_android(out, load_catalog())
        path = out / "android/res/values/strings.xml"
        node = ET.parse(path).getroot().find(f"./string[@name='{PARAM_KEY}']")
        self.assertIsNotNone(node, f"{PARAM_KEY} missing from Android output")
        return _unescape_android(node.text)

    def _ios_template(self, out: Path) -> str:
        generate_ios(out, load_catalog())
        path = out / "ios/Resources/Resources/Localizable.xcstrings"
        payload = json.loads(path.read_text())
        ios_locale = IOS_LOCALE_IDS["default"]
        unit = payload["strings"][PARAM_KEY]["localizations"][ios_locale]["stringUnit"]
        return unit["value"]

    def test_compose_round_trip_substitutes_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template = self._compose_template(Path(tmp))
        self.assertNotIn("{0}", template, "Compose left a literal {0} placeholder")
        rendered = _positional_args_runtime(template, [ARG], COMPOSE_TOKEN)
        self.assertEqual(rendered, self.expected)
        self.assertIn(ARG, rendered)

    def test_android_round_trip_substitutes_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template = self._android_template(Path(tmp))
        self.assertNotIn("{0}", template, "Android left a literal {0} placeholder")
        rendered = _positional_args_runtime(template, [ARG], ANDROID_TOKEN)
        self.assertEqual(rendered, self.expected)

    def test_ios_round_trip_substitutes_argument(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            template = self._ios_template(Path(tmp))
        self.assertNotIn("{0}", template, "iOS left a literal {0} placeholder")
        rendered = _positional_args_runtime(template, [ARG], IOS_TOKEN)
        self.assertEqual(rendered, self.expected)

    def test_no_emitter_leaks_canonical_placeholder(self) -> None:
        catalog = load_catalog()
        param_keys = [
            key for key, entry in catalog["strings"].items()
            if PLACEHOLDER.search(entry["values"]["default"])
        ]
        self.assertGreater(len(param_keys), 0)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            generate_compose(out, catalog)
            generate_android(out, catalog)
            generate_ios(out, catalog)

            compose_xml = (out / "compose/composeResources/values/strings.xml").read_text()
            android_xml = (out / "android/res/values/strings.xml").read_text()
            ios_json = (out / "ios/Resources/Resources/Localizable.xcstrings").read_text()

        for blob, label in [(compose_xml, "Compose"), (android_xml, "Android"), (ios_json, "iOS")]:
            for key in param_keys:
                self.assertNotIn(
                    "{0}", _value_for_key(blob, key, label),
                    f"{label} emitted a literal {{0}} for {key}"
                )

def _value_for_key(blob: str, key: str, label: str) -> str:
    if label == "iOS":
        loc = json.loads(blob)["strings"][key]["localizations"]
        return next(iter(loc.values()))["stringUnit"]["value"] if loc else ""
    node = ET.fromstring(blob).find(f"./string[@name='{key}']")
    return html.unescape(node.text) if node is not None and node.text else ""

if __name__ == "__main__":
    unittest.main()
