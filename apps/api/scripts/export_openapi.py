"""Export a deterministic OpenAPI document without running an API server."""

import json
from pathlib import Path
from typing import Any

from gtm_state_api.main import app

REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
OUTPUT_PATH = REPOSITORY_ROOT / "packages" / "contracts" / "openapi.json"


def serialize_schema(schema: dict[str, Any]) -> str:
    """Serialize OpenAPI with stable key ordering and one trailing newline."""

    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main() -> None:
    """Write the committed OpenAPI artifact."""

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(serialize_schema(app.openapi()), encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
