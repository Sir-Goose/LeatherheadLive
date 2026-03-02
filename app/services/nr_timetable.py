from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path
from threading import RLock
import zipfile

from app.config import settings
from app.models.board import Location, ServiceDetails


logger = logging.getLogger(__name__)


@dataclass
class ServiceLookupHint:
    crs: str
    scheduled_arrival_time: str | None = None
    scheduled_departure_time: str | None = None
    origin_crs: str | None = None
    destination_crs: str | None = None
    operator_code: str | None = None
    operator_name: str | None = None
    service_type: str | None = None
    generated_at: str | None = None


@dataclass
class TimetableStop:
    tiploc: str
    location_name: str
    crs: str | None = None
    working_arrival: str | None = None
    working_departure: str | None = None
    public_arrival: str | None = None
    public_departure: str | None = None
    platform: str | None = None

    @property
    def arrival_time(self) -> str | None:
        return self.public_arrival or self.working_arrival

    @property
    def departure_time(self) -> str | None:
        return self.public_departure or self.working_departure


@dataclass
class TimetableSchedule:
    train_uid: str
    operator_code: str | None
    service_type: str
    start_date: date | None
    end_date: date | None
    days_run: str
    stp_indicator: str
    stops: list[TimetableStop] = field(default_factory=list)


@dataclass
class TimetableCandidate:
    schedule: TimetableSchedule
    match_index: int
    score: int
    minute_diff: int | None


class NRTimetableService:
    """Load and match National Rail CIF timetable schedules from daily zip feed."""

    def __init__(self, zip_path: str | None = None, enabled: bool | None = None):
        self.zip_path = zip_path or settings.nr_timetable_zip_path
        self.enabled = settings.nr_timetable_enabled if enabled is None else enabled
        self._signature: tuple[str, int, int] | None = None
        self._mca_member: str | None = None
        self._msn_member: str | None = None
        self._tiploc_to_crs: dict[str, str] = {}
        self._tiploc_to_name: dict[str, str] = {}
        self._station_cache: dict[tuple[tuple[str, int, int], str, str], list[TimetableSchedule]] = {}
        self._station_cache_order: list[tuple[tuple[str, int, int], str, str]] = []
        self._station_cache_max_entries = 8
        self._lock = RLock()

    def find_service_detail(
        self,
        service_id: str,
        requested_crs: str,
        hint: ServiceLookupHint | None = None,
    ) -> ServiceDetails | None:
        with self._lock:
            if not self.enabled:
                return None

            requested = self._normalize_crs(requested_crs)
            if not requested:
                return None

            signature = self._refresh_signature()
            if not signature:
                return None

            if hint is None:
                hint = ServiceLookupHint(crs=requested)
            elif not self._normalize_crs(hint.crs):
                hint.crs = requested

            service_date = self._resolve_service_date(hint.generated_at)
            schedules = self._load_station_schedules(signature, requested, service_date)
            if not schedules:
                return None

            best: TimetableCandidate | None = None
            for schedule in schedules:
                idx, minute_diff = self._best_match_index(schedule, requested, hint)
                if idx is None:
                    continue
                score = self._score_candidate(schedule, idx, minute_diff, hint, service_id)
                candidate = TimetableCandidate(
                    schedule=schedule,
                    match_index=idx,
                    score=score,
                    minute_diff=minute_diff,
                )
                if self._is_better_candidate(candidate, best):
                    best = candidate

            if best is None or best.score < 120:
                return None

            logger.info(
                "Matched timetable fallback for service %s at %s using UID %s (score=%s)",
                service_id,
                requested,
                best.schedule.train_uid,
                best.score,
            )
            return self._build_service_details(service_id, requested, hint, best)

    def _is_better_candidate(
        self,
        candidate: TimetableCandidate,
        current: TimetableCandidate | None,
    ) -> bool:
        if current is None:
            return True
        if candidate.score != current.score:
            return candidate.score > current.score
        if candidate.minute_diff is None:
            return False
        if current.minute_diff is None:
            return True
        return candidate.minute_diff < current.minute_diff

    def _refresh_signature(self) -> tuple[str, int, int] | None:
        path = Path(self.zip_path)
        if not path.exists() or not path.is_file():
            return None

        stat = path.stat()
        signature = (str(path.resolve()), stat.st_mtime_ns, stat.st_size)
        if signature != self._signature:
            self._signature = signature
            self._mca_member = None
            self._msn_member = None
            self._tiploc_to_crs.clear()
            self._tiploc_to_name.clear()
            self._station_cache.clear()
            self._station_cache_order.clear()
        return signature

    def _resolve_members(self, signature: tuple[str, int, int]) -> tuple[str | None, str | None]:
        if self._mca_member and self._msn_member:
            return self._mca_member, self._msn_member

        zip_path = signature[0]
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            self._mca_member = next((name for name in names if name.upper().endswith("MCA.TXT")), None)
            self._msn_member = next((name for name in names if name.upper().endswith("MSN.TXT")), None)
        return self._mca_member, self._msn_member

    def _ensure_tiploc_index(self, signature: tuple[str, int, int]) -> bool:
        if self._tiploc_to_name:
            return True

        _, msn_member = self._resolve_members(signature)
        if not msn_member:
            return False

        zip_path = signature[0]
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(msn_member, "r") as raw_file:
                for raw_line in raw_file:
                    line = raw_line.decode("latin-1").rstrip("\r\n")
                    if not line.startswith("A"):
                        continue
                    if len(line) < 52:
                        continue

                    name = line[5:35].strip()
                    tiploc = line[36:43].strip().upper()
                    if not tiploc:
                        continue

                    crs = line[49:52].strip().upper()
                    if not self._normalize_crs(crs):
                        crs = line[43:46].strip().upper()
                    normalized_crs = self._normalize_crs(crs)
                    if normalized_crs:
                        self._tiploc_to_crs[tiploc] = normalized_crs

                    self._tiploc_to_name[tiploc] = name or tiploc

        return True

    def _load_station_schedules(
        self,
        signature: tuple[str, int, int],
        station_crs: str,
        service_date: date,
    ) -> list[TimetableSchedule]:
        key = (signature, station_crs, service_date.isoformat())
        cached = self._station_cache.get(key)
        if cached is not None:
            return cached

        mca_member, _ = self._resolve_members(signature)
        if not mca_member:
            return []
        if not self._ensure_tiploc_index(signature):
            return []

        schedules: list[TimetableSchedule] = []
        current: TimetableSchedule | None = None
        current_active = False

        def finalize_schedule() -> None:
            nonlocal current, current_active
            if not current or not current_active or not current.stops:
                current = None
                current_active = False
                return
            if any((stop.crs or "").upper() == station_crs for stop in current.stops):
                schedules.append(current)
            current = None
            current_active = False

        zip_path = signature[0]
        with zipfile.ZipFile(zip_path, "r") as zf:
            with zf.open(mca_member, "r") as raw_file:
                for raw_line in raw_file:
                    line = raw_line.decode("latin-1").rstrip("\r\n")
                    if len(line) < 2:
                        continue
                    record_type = line[:2]

                    if record_type == "BS":
                        finalize_schedule()
                        current, current_active = self._parse_bs_record(line, service_date)
                        continue

                    if current is None:
                        continue

                    if record_type == "BX":
                        operator_code = line[11:13].strip().upper()
                        if operator_code:
                            current.operator_code = operator_code
                        continue

                    if not current_active:
                        continue

                    if record_type in {"LO", "LI", "LT"}:
                        stop = self._parse_stop_record(line, record_type)
                        if stop:
                            current.stops.append(stop)

        finalize_schedule()
        self._remember_station_cache(key, schedules)
        return schedules

    def _remember_station_cache(
        self,
        key: tuple[tuple[str, int, int], str, str],
        schedules: list[TimetableSchedule],
    ) -> None:
        self._station_cache[key] = schedules
        if key in self._station_cache_order:
            self._station_cache_order.remove(key)
        self._station_cache_order.append(key)
        while len(self._station_cache_order) > self._station_cache_max_entries:
            oldest = self._station_cache_order.pop(0)
            self._station_cache.pop(oldest, None)

    def _parse_bs_record(self, line: str, service_date: date) -> tuple[TimetableSchedule | None, bool]:
        if len(line) < 80:
            return None, False

        transaction_type = line[2].strip().upper() or "N"
        train_uid = line[3:9].strip().upper()
        start_date = self._parse_cif_date(line[9:15])
        end_date = self._parse_cif_date(line[15:21])
        days_run = line[21:28]
        train_status = line[29:30].strip()
        stp_indicator = line[79:80].strip().upper() or "N"
        service_type = "bus" if train_status == "5" else "train"

        schedule = TimetableSchedule(
            train_uid=train_uid,
            operator_code=None,
            service_type=service_type,
            start_date=start_date,
            end_date=end_date,
            days_run=days_run,
            stp_indicator=stp_indicator,
            stops=[],
        )

        if transaction_type == "D":
            return schedule, False
        if stp_indicator == "C":
            return schedule, False
        if not self._runs_on_date(start_date, end_date, days_run, service_date):
            return schedule, False
        return schedule, True

    def _parse_stop_record(self, line: str, record_type: str) -> TimetableStop | None:
        if len(line) < 33:
            return None

        tiploc = line[2:9].strip().upper()
        if not tiploc:
            return None

        location_name = self._tiploc_to_name.get(tiploc, tiploc.replace("_", " "))
        crs = self._tiploc_to_crs.get(tiploc)

        working_arrival: str | None = None
        working_departure: str | None = None
        public_arrival: str | None = None
        public_departure: str | None = None
        platform: str | None = None

        if record_type == "LO":
            working_departure = self._parse_cif_time(line[10:15], allow_midnight=True)
            public_departure = self._parse_cif_time(line[15:19], allow_midnight=False)
            platform = line[19:22].strip() or None
        elif record_type == "LI":
            working_arrival = self._parse_cif_time(line[10:15], allow_midnight=True)
            working_departure = self._parse_cif_time(line[15:20], allow_midnight=True)
            pass_time = self._parse_cif_time(line[20:25], allow_midnight=True)
            public_arrival = self._parse_cif_time(line[25:29], allow_midnight=False)
            public_departure = self._parse_cif_time(line[29:33], allow_midnight=False)
            platform = line[33:36].strip() or None
            if not working_arrival and not working_departure and pass_time:
                working_arrival = pass_time
                working_departure = pass_time
        elif record_type == "LT":
            working_arrival = self._parse_cif_time(line[10:15], allow_midnight=True)
            public_arrival = self._parse_cif_time(line[15:19], allow_midnight=False)
            platform = line[19:22].strip() or None
        else:
            return None

        if not any((working_arrival, working_departure, public_arrival, public_departure)):
            return None

        return TimetableStop(
            tiploc=tiploc,
            location_name=location_name,
            crs=crs,
            working_arrival=working_arrival,
            working_departure=working_departure,
            public_arrival=public_arrival,
            public_departure=public_departure,
            platform=platform,
        )

    def _best_match_index(
        self,
        schedule: TimetableSchedule,
        station_crs: str,
        hint: ServiceLookupHint,
    ) -> tuple[int | None, int | None]:
        indices = [
            idx for idx, stop in enumerate(schedule.stops)
            if (stop.crs or "").upper() == station_crs
        ]
        if not indices:
            return None, None

        target_times = [
            self._to_minutes(hint.scheduled_arrival_time),
            self._to_minutes(hint.scheduled_departure_time),
        ]
        target_times = [value for value in target_times if value is not None]
        if not target_times:
            return indices[0], None

        best_index: int | None = None
        best_diff: int | None = None
        for idx in indices:
            stop = schedule.stops[idx]
            stop_times = [
                self._to_minutes(stop.arrival_time),
                self._to_minutes(stop.departure_time),
            ]
            stop_times = [value for value in stop_times if value is not None]
            if not stop_times:
                continue

            local_best = min(
                self._clock_diff_minutes(stop_min, target_min)
                for stop_min in stop_times
                for target_min in target_times
            )
            if best_diff is None or local_best < best_diff:
                best_diff = local_best
                best_index = idx

        return best_index, best_diff

    def _score_candidate(
        self,
        schedule: TimetableSchedule,
        match_index: int,
        minute_diff: int | None,
        hint: ServiceLookupHint,
        service_id: str,
    ) -> int:
        score = 0

        uid_hint = (service_id or "").strip().upper()[:6]
        if uid_hint and schedule.train_uid == uid_hint:
            score += 100

        if minute_diff is not None:
            if minute_diff == 0:
                score += 160
            elif minute_diff <= 2:
                score += 130
            elif minute_diff <= 5:
                score += 100
            elif minute_diff <= 10:
                score += 70
            elif minute_diff <= 20:
                score += 35
            elif minute_diff <= 30:
                score += 15
            else:
                score -= min(minute_diff, 60)
        else:
            score -= 20

        origin_crs = self._schedule_origin_crs(schedule)
        destination_crs = self._schedule_destination_crs(schedule)

        if hint.origin_crs and origin_crs == self._normalize_crs(hint.origin_crs):
            score += 70
        if hint.destination_crs and destination_crs == self._normalize_crs(hint.destination_crs):
            score += 80

        if hint.operator_code and schedule.operator_code == hint.operator_code.strip().upper():
            score += 40
        if hint.service_type and schedule.service_type == hint.service_type:
            score += 20

        # Prefer matches where the selected index has both arrival and departure
        # at the filter station because the board can be arrivals/departures/passing.
        stop = schedule.stops[match_index]
        if stop.arrival_time and stop.departure_time:
            score += 10

        return score

    def _build_service_details(
        self,
        service_id: str,
        requested_crs: str,
        hint: ServiceLookupHint,
        candidate: TimetableCandidate,
    ) -> ServiceDetails:
        schedule = candidate.schedule
        current_idx = candidate.match_index
        current_stop = schedule.stops[current_idx]

        previous_points = [
            point for point in (
                self._to_calling_point(stop) for stop in schedule.stops[:current_idx]
            ) if point
        ]
        subsequent_points = [
            point for point in (
                self._to_calling_point(stop) for stop in schedule.stops[current_idx + 1:]
            ) if point
        ]

        current_arrival = current_stop.arrival_time
        current_departure = current_stop.departure_time
        generated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

        origin_location = self._to_location(schedule.stops[0], fallback_crs=hint.origin_crs or requested_crs)
        destination_location = self._to_location(schedule.stops[-1], fallback_crs=hint.destination_crs or requested_crs)

        operator_code = (hint.operator_code or schedule.operator_code or "??").strip().upper()
        operator_name = (hint.operator_name or operator_code).strip() or operator_code

        payload = {
            "generatedAt": generated_at,
            "pulledAt": generated_at,
            "serviceType": schedule.service_type,
            "locationName": current_stop.location_name,
            "crs": requested_crs,
            "operator": operator_name,
            "operatorCode": operator_code,
            "sta": current_arrival,
            "eta": "On time" if current_arrival else None,
            "std": current_departure,
            "etd": "On time" if current_departure else None,
            "platform": current_stop.platform,
            "isCancelled": False,
            "serviceID": service_id,
            "origin": [origin_location.model_dump()],
            "destination": [destination_location.model_dump()],
            "previousCallingPoints": [{"callingPoint": previous_points}] if previous_points else [],
            "subsequentCallingPoints": [{"callingPoint": subsequent_points}] if subsequent_points else [],
        }
        return ServiceDetails(**payload)

    def _to_location(self, stop: TimetableStop, fallback_crs: str) -> Location:
        crs = self._normalize_crs(stop.crs) or self._normalize_crs(fallback_crs) or "UNK"
        return Location(locationName=stop.location_name, crs=crs)

    def _to_calling_point(self, stop: TimetableStop) -> dict | None:
        arrival = stop.arrival_time
        departure = stop.departure_time
        scheduled = departure or arrival
        if not scheduled:
            return None

        crs = self._normalize_crs(stop.crs) or stop.tiploc
        point = {
            "locationName": stop.location_name,
            "crs": crs,
            "st": scheduled,
            "et": "On time",
        }
        if arrival:
            point["pta"] = arrival
            point["eta"] = "On time"
        return point

    def _schedule_origin_crs(self, schedule: TimetableSchedule) -> str | None:
        for stop in schedule.stops:
            crs = self._normalize_crs(stop.crs)
            if crs:
                return crs
        return None

    def _schedule_destination_crs(self, schedule: TimetableSchedule) -> str | None:
        for stop in reversed(schedule.stops):
            crs = self._normalize_crs(stop.crs)
            if crs:
                return crs
        return None

    def _resolve_service_date(self, timestamp: str | None) -> date:
        if timestamp:
            parsed = self._parse_iso_datetime(timestamp)
            if parsed:
                return parsed.date()
        return datetime.now(timezone.utc).date()

    @staticmethod
    def _parse_iso_datetime(value: str) -> datetime | None:
        value = value.strip()
        if not value:
            return None
        if value.endswith("Z"):
            value = f"{value[:-1]}+00:00"
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    @staticmethod
    def _parse_cif_date(raw: str) -> date | None:
        raw = raw.strip()
        if len(raw) != 6 or not raw.isdigit():
            return None
        year = int(raw[0:2])
        month = int(raw[2:4])
        day = int(raw[4:6])
        year += 2000 if year < 70 else 1900
        try:
            return date(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _runs_on_date(
        start_date: date | None,
        end_date: date | None,
        days_run: str,
        service_date: date,
    ) -> bool:
        if start_date and service_date < start_date:
            return False
        if end_date and service_date > end_date:
            return False
        if len(days_run) != 7:
            return True
        day_flag = days_run[service_date.weekday()]
        return day_flag == "1"

    @staticmethod
    def _parse_cif_time(raw: str, allow_midnight: bool = False) -> str | None:
        token = raw.strip().upper()
        if not token:
            return None
        digits = "".join(ch for ch in token if ch.isdigit())
        if len(digits) < 4:
            return None
        hhmm = digits[:4]
        if hhmm == "0000" and not allow_midnight:
            return None
        hour = int(hhmm[0:2]) % 24
        minute = int(hhmm[2:4])
        if minute > 59:
            return None
        return f"{hour:02d}:{minute:02d}"

    @staticmethod
    def _normalize_crs(value: str | None) -> str | None:
        if not value:
            return None
        crs = value.strip().upper()
        if len(crs) != 3 or not crs.isalpha():
            return None
        return crs

    @staticmethod
    def _to_minutes(value: str | None) -> int | None:
        if not value:
            return None
        token = value.strip()
        if len(token) < 5 or token[2] != ":":
            return None
        hh = token[:2]
        mm = token[3:5]
        if not (hh.isdigit() and mm.isdigit()):
            return None
        hour = int(hh)
        minute = int(mm)
        if hour > 23 or minute > 59:
            return None
        return hour * 60 + minute

    @staticmethod
    def _clock_diff_minutes(a: int, b: int) -> int:
        diff = abs(a - b)
        return min(diff, 1440 - diff)


nr_timetable_service = NRTimetableService()
