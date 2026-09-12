"""Bounded parallel section retrieval with success-only, single-flight caching."""
from collections import OrderedDict
from concurrent.futures import Future, ThreadPoolExecutor
from copy import deepcopy
from threading import Lock, Semaphore, local
import time

from src.building_hub import BuildingHubError
from src.lookup import LOOKUP_ENDPOINTS, TITLE_ENDPOINT, LookupDataError, lookup_register


class RegisterSectionCache:
    """One instance per credential and relay identity; never stores credentials.

    A failed section never replaces a successful one or becomes an empty list.
    Row and entry limits bound large collective-building responses in memory.
    """
    def __init__(self, *, ttl=86400, empty_ttl=300, max_entries=768,
                 max_rows=50000, interval=0.25, clock=time.monotonic):
        self.ttl, self.empty_ttl = ttl, empty_ttl
        self.max_entries, self.max_rows = max_entries, max_rows
        self.interval, self.clock = interval, clock
        self._lock, self._gate = Lock(), Lock()
        self._slots = Semaphore(3)
        self._entries, self._pending = OrderedDict(), {}
        self._row_count, self._next_start = 0, 0.0

    def get(self, endpoint, land_key, request):
        key = (endpoint, land_key)
        with self._lock:
            entry = self._entries.get(key)
            if entry is not None:
                expires, rows = entry
                if self.clock() < expires:
                    self._entries.move_to_end(key)
                    return deepcopy(rows)
                self._entries.pop(key)
                self._row_count -= len(rows)
            future = self._pending.get(key)
            owner = future is None
            if owner:
                future = self._pending[key] = Future()
        if not owner:
            return deepcopy(future.result())
        try:
            with self._slots:
                with self._gate:
                    delay = self._next_start - time.monotonic()
                    if delay > 0:
                        time.sleep(delay)
                    self._next_start = time.monotonic() + self.interval
                rows = request()
            if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
                raise LookupDataError("건축HUB 항목 응답 형식을 확인하지 못했습니다.")
            saved = deepcopy(rows)
            # Do not let an empty title hide a building for a whole cache day.
            ttl = self.ttl if rows else (0 if endpoint == TITLE_ENDPOINT else self.empty_ttl)
            with self._lock:
                if ttl > 0 and len(saved) <= self.max_rows:
                    self._entries[key] = (self.clock() + ttl, saved)
                    self._row_count += len(saved)
                    while len(self._entries) > self.max_entries or self._row_count > self.max_rows:
                        _, (_, evicted) = self._entries.popitem(last=False)
                        self._row_count -= len(evicted)
                self._pending.pop(key, None)
                future.set_result(saved)
            return rows
        except BaseException as error:
            with self._lock:
                self._pending.pop(key, None)
                future.set_exception(error)
            raise


class _FetchedSections:
    def __init__(self, sections):
        self.sections = sections

    def fetch_all(self, endpoint, land_key, **kwargs):
        result = self.sections[endpoint]
        if isinstance(result, BuildingHubError):
            raise result
        return result


def load_register_parallel(land_key, client_factory, cache):
    """Resolve the mandatory title first, then retrieve five details on 3 workers.

    Each worker owns its client/session; immutable mapping remains in lookup.py.
    All prefetched sections are inspected even if an earlier section failed.
    """
    workers = local()
    clients, clients_lock = [], Lock()

    def fetch(endpoint):
        def request():
            if not hasattr(workers, "client"):
                workers.client = client_factory()
                with clients_lock:
                    clients.append(workers.client)
            return workers.client.fetch_all(endpoint, land_key, num_of_rows=100)
        return cache.get(endpoint, land_key, request)

    try:
        sections = {TITLE_ENDPOINT: fetch(TITLE_ENDPOINT)}
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="register-detail") as pool:
            pending = {endpoint: pool.submit(fetch, endpoint) for endpoint in LOOKUP_ENDPOINTS[1:]}
            for endpoint, future in pending.items():
                try:
                    sections[endpoint] = future.result()
                except BuildingHubError as error:
                    sections[endpoint] = error
        return lookup_register(_FetchedSections(sections), land_key, skip_on_network_failure=False)
    finally:
        for client in clients:
            client.close()
