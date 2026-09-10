"""Exact lot-number discovery across every current Seoul legal dong.

Only titles are fetched; detailed sections are loaded after address selection.
Failed/unvisited dongs remain explicit and are the only targets on retry.
"""
from __future__ import annotations

from collections import OrderedDict
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
import re
from threading import Lock, Semaphore
import time
from typing import Callable

from src.address import AddressParseError, LandKey, ParsedAddress, SEOUL_LEGAL_DONG_CODES, normalize_address
from src.building_hub import (
    BuildingHubAuthError, BuildingHubError, BuildingHubHTTPError,
    BuildingHubQuotaError, BuildingHubRateLimitError, BuildingHubValidationError,
)
from src.lookup import LookupDataError, TitleSummary


@dataclass(frozen=True, slots=True)
class LotNumber:
    bun: str
    ji: str
    plat_gb_cd: str = "0"

    def __post_init__(self):
        if (not re.fullmatch(r"[0-9]{4}", self.bun) or int(self.bun) == 0
                or not re.fullmatch(r"[0-9]{4}", self.ji) or self.plat_gb_cd not in {"0", "1"}):
            raise AddressParseError("본번은 1~9999, 부번은 0~9999로 입력해 주세요.")

    @property
    def label(self) -> str:
        return ("산" if self.plat_gb_cd == "1" else "") + str(int(self.bun)) + (
            f"-{int(self.ji)}" if int(self.ji) else ""
        )


def parse_lot_number(query: str) -> LotNumber | None:
    """Return None for an address containing a location, not a guessed dong."""
    normalized = normalize_address(query)
    match = re.fullmatch(r"(?:(산)\s*)?([0-9]{1,4})(?:\s*-\s*([0-9]{1,4}))?\s*(?:번지)?", normalized)
    if not match:
        if re.fullmatch(r"[0-9\s\-산번지]+", normalized):
            raise AddressParseError("지번은 332-37 또는 산1-5처럼 입력해 주세요. 본번·부번은 네 자리까지 가능합니다.")
        return None
    return LotNumber(match[2].zfill(4), (match[3] or "0").zfill(4), "1" if match[1] else "0")


def seoul_parcels(lot: LotNumber) -> tuple[ParsedAddress, ...]:
    return tuple(
        ParsedAddress(lot.label, f"서울특별시 {district} {dong} {lot.label}", district, dong,
                      LandKey(code[:5], code[5:], lot.plat_gb_cd, lot.bun, lot.ji))
        for (district, dong), code in sorted(SEOUL_LEGAL_DONG_CODES.items())
    )


@dataclass(frozen=True, slots=True)
class ParcelMatch:
    parsed: ParsedAddress
    buildings: tuple[TitleSummary, ...]


@dataclass(frozen=True, slots=True)
class ParcelFailure:
    parsed: ParsedAddress
    reason: str


@dataclass(frozen=True, slots=True)
class SeoulLotResult:
    lot: LotNumber
    matches: tuple[ParcelMatch, ...]
    checked_dongs: tuple[str, ...]
    failures: tuple[ParcelFailure, ...]
    total_dongs: int
    stopped_reason: str | None = None

    @property
    def is_complete(self) -> bool:
        return len(self.checked_dongs) == self.total_dongs

    @property
    def building_count(self) -> int:
        return sum(len(match.buildings) for match in self.matches)


class TitleCache:
    """Bounded, thread-safe success cache and request gate for one credential.

    No Streamlit calls in worker threads. Concurrent identical lookups share a
    Future; failures are never cached. Keys/URLs are never stored in results.
    """
    def __init__(self, *, ttl=86400, max_entries=10000, interval=0.25):
        self.ttl, self.max_entries, self.interval = ttl, max_entries, interval
        self._lock, self._gate = Lock(), Lock()
        self._slots = Semaphore(4)
        self._next_start = 0.0
        self._cache = OrderedDict()
        self._pending = {}

    def get(self, land: LandKey, fetch: Callable[[], tuple[TitleSummary, ...]]) -> tuple[TitleSummary, ...]:
        with self._lock:
            entry = self._cache.get(land)
            if entry and time.monotonic() - entry[0] < self.ttl:
                self._cache.move_to_end(land)
                return entry[1]
            future = self._pending.get(land)
            owner = future is None
            if owner:
                future = Future()
                self._pending[land] = future
        if not owner:
            return future.result()
        try:
            with self._slots:
                with self._gate:
                    time.sleep(max(0, self._next_start - time.monotonic()))
                    self._next_start = time.monotonic() + self.interval
                value = fetch()
            with self._lock:
                self._cache[land] = (time.monotonic(), value)
                self._cache.move_to_end(land)
                while len(self._cache) > self.max_entries:
                    self._cache.popitem(last=False)
            future.set_result(value)
            return value
        except BaseException as error:
            future.set_exception(error)
            raise
        finally:
            with self._lock:
                self._pending.pop(land, None)


def _failure_reason(error: Exception) -> tuple[str, bool]:
    if isinstance(error, BuildingHubAuthError):
        return "건축HUB 인증 또는 사용 권한을 확인해야 합니다.", True
    if isinstance(error, BuildingHubQuotaError):
        return "건축HUB의 오늘 호출 한도에 도달했습니다.", True
    if isinstance(error, BuildingHubRateLimitError) or (isinstance(error, BuildingHubHTTPError) and error.status_code == 429):
        return "건축HUB 요청이 몰려 검색을 멈췄습니다. 잠시 후 이어서 확인해 주세요.", True
    if isinstance(error, BuildingHubValidationError):
        return "건축HUB 연결 설정을 확인해야 합니다.", True
    if isinstance(error, LookupDataError):
        return "응답의 지번·대장 정보가 일치하지 않아 확인하지 못했습니다.", False
    return "건축HUB 응답 지연 또는 오류로 확인하지 못했습니다.", False


def search_seoul_lot(
    lot: LotNumber,
    fetch: Callable[[LandKey], tuple[TitleSummary, ...]],
    *, previous: SeoulLotResult | None = None,
    on_progress: Callable[[int, int, int], None] | None = None,
    max_seconds: float = 600,
) -> SeoulLotResult:
    if previous and previous.lot != lot:
        raise ValueError("Cannot merge results for different lot numbers")
    parcels = seoul_parcels(lot)
    checked = set(previous.checked_dongs) if previous else set()
    matches = {m.parsed.land_key.legal_dong_code: m for m in previous.matches} if previous else {}
    errors = {}
    queue = iter(p for p in parcels if p.land_key.legal_dong_code not in checked)
    stopped = None
    started = time.monotonic()
    consecutive_errors = 0

    def progress():
        if on_progress:
            on_progress(len(checked) + len(errors), len(parcels), sum(len(m.buildings) for m in matches.values()))

    progress()
    with ThreadPoolExecutor(max_workers=4, thread_name_prefix="seoul-lot") as executor:
        pending = {}

        def schedule():
            while len(pending) < 4 and not stopped:
                parsed = next(queue, None)
                if parsed is None:
                    break
                pending[executor.submit(fetch, parsed.land_key)] = parsed

        schedule()
        while pending:
            done, _ = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                parsed = pending.pop(future)
                code = parsed.land_key.legal_dong_code
                try:
                    buildings = future.result()
                except (BuildingHubError, LookupDataError) as error:
                    reason, fatal = _failure_reason(error)
                    errors[code] = reason
                    consecutive_errors += 1
                    if fatal or consecutive_errors >= 8:
                        stopped = reason
                else:
                    checked.add(code)
                    consecutive_errors = 0
                    if buildings:
                        matches[code] = ParcelMatch(parsed, buildings)
                progress()
            if time.monotonic() - started >= max_seconds:
                stopped = stopped or "검색 시간이 길어져 중간 결과를 표시합니다. 미확인 동을 이어서 확인해 주세요."
            schedule()

    return SeoulLotResult(
        lot=lot,
        matches=tuple(sorted(matches.values(), key=lambda m: (m.parsed.district, m.parsed.legal_dong))),
        checked_dongs=tuple(sorted(checked)),
        failures=tuple(ParcelFailure(p, errors.get(p.land_key.legal_dong_code, "아직 확인하지 않은 동입니다."))
                       for p in parcels if p.land_key.legal_dong_code not in checked),
        total_dongs=len(parcels), stopped_reason=stopped,
    )
