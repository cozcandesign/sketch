"""OpenAPI şemasını stdout'a yazar: `make gen-types` bunu `openapi-typescript`'e verir.

Sunucu çalıştırmadan, varsayılan ayarlarla uygulama nesnesi kurulur (lifespan çalışmaz).
"""

import json
import sys

from marketpulse.api.app import create_app
from marketpulse.config import Settings


def main() -> None:
    app = create_app(Settings(_env_file=None), migrate_on_start=False)
    json.dump(app.openapi(), sys.stdout, indent=2, ensure_ascii=False)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
