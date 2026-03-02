"""Build or refresh the NR timetable SQLite index from the daily CIF zip feed."""

from __future__ import annotations

import json
import logging

from app.services.nr_timetable import NRTimetableService


logger = logging.getLogger(__name__)


def build_index() -> dict[str, object]:
    service = NRTimetableService()
    return service.prebuild_index()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    result = build_index()
    print(json.dumps(result, sort_keys=True))

    status = result.get("status")
    if status == "ok":
        logger.info("NR timetable index ready at %s", result.get("index_path"))
        return 0

    logger.error("NR timetable index build failed: %s", status)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
