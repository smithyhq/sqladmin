import json
import os
import sys
from typing import Dict

from babel.messages.catalog import Catalog
from babel.messages.mofile import write_mo
from babel.messages.pofile import write_po

DEFAULT_MAPPINGS = os.path.join("scripts", "translations.json")
OUTPUT_ROOT = os.path.join("sqladmin", "translations")
DOMAIN = "admin"


def build(mappings_path: str, output_root: str = OUTPUT_ROOT) -> None:
    """Write ``.po``/``.mo`` catalogs (and the ``.pot`` template) from a mapping.

    Args:
        mappings_path: Path to the JSON file of ``{locale: {source: translation}}``.
        output_root: Directory the ``gettext`` tree is written to.
    """
    with open(mappings_path, encoding="utf-8") as file:
        mappings: Dict[str, Dict[str, str]] = json.load(file)

    # The full source-string set is the union of every locale's keys, so a
    # partially translated locale still lists all messages.
    messages = sorted({message for entries in mappings.values() for message in entries})
    os.makedirs(output_root, exist_ok=True)

    template = Catalog(project="SQLAdmin", domain=DOMAIN)
    for message in messages:
        template.add(message, string="")
    with open(os.path.join(output_root, "admin.pot"), "wb") as file:
        write_po(file, template, omit_header=False)

    for locale, entries in mappings.items():
        catalog = Catalog(locale=locale, project="SQLAdmin", domain=DOMAIN)
        for message in messages:
            catalog.add(message, string=entries.get(message, ""))

        directory = os.path.join(output_root, locale, "LC_MESSAGES")
        os.makedirs(directory, exist_ok=True)
        with open(os.path.join(directory, "admin.po"), "wb") as file:
            write_po(file, catalog, omit_header=False, sort_output=False)
        with open(os.path.join(directory, "admin.mo"), "wb") as file:
            write_mo(file, catalog)

        translated = sum(1 for message in messages if entries.get(message))
        print(f"{locale}: {translated}/{len(messages)} translated")


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MAPPINGS
    build(path)
