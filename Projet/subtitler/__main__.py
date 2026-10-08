"""Lance le serveur : ``python -m subtitler``."""

import logging
import os

import uvicorn

from subtitler.api import create_app


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    uvicorn.run(
        create_app(),
        host=os.environ.get("SUBTITLER_HOST", "127.0.0.1"),
        port=int(os.environ.get("SUBTITLER_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
