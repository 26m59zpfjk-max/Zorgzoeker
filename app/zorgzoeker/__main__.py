"""Start de lokale interface: python -m zorgzoeker."""

from __future__ import annotations

import uvicorn

from zorgzoeker.config import host, poort


def main() -> None:
    # access_log uit: een zoekvraag kan herleidbare tekst bevatten en hoort niet in een log.
    uvicorn.run(
        "zorgzoeker.app:app",
        host=host(),
        port=poort(),
        access_log=False,
        log_level="warning",
    )


if __name__ == "__main__":
    main()
