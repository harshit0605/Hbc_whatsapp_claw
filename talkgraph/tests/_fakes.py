"""Shared fake Neo4j async driver for hermetic graph tests.

Lets store tests assert on the parameters passed to Cypher without needing a
real database. Each test sets `fake.next_result` to control what the next
session.run() returns; queries are recorded in `fake.calls`.
"""

from talkgraph.graph.store import Neo4jGraphStore


class FakeRecord:
    def __init__(self, data):
        self._data = data

    def data(self):
        return self._data


class FakeResult:
    def __init__(self, record=None, rows=None):
        self._record = record
        self._rows = list(rows or [])

    async def single(self):
        return self._record

    def __aiter__(self):
        self._it = iter(self._rows)
        return self

    async def __anext__(self):
        try:
            return next(self._it)
        except StopIteration:
            raise StopAsyncIteration


class FakeSession:
    def __init__(self, driver):
        self._driver = driver

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def run(self, query, params=None):
        self._driver.calls.append((query, params))
        # Each run() can return a different result if the test sets a queue.
        if self._driver.result_queue:
            return self._driver.result_queue.pop(0)
        return self._driver.next_result


class FakeDriver:
    def __init__(self):
        self.calls: list = []
        self.next_result: FakeResult = FakeResult()
        # Optional ordered queue for methods that fire multiple Cypher calls.
        self.result_queue: list = []

    def session(self):
        return FakeSession(self)

    async def close(self):
        return None


def store_with_fake() -> tuple[Neo4jGraphStore, FakeDriver]:
    """Build a Neo4jGraphStore wired to a fake driver, bypassing the real ctor."""
    store = Neo4jGraphStore.__new__(Neo4jGraphStore)
    fake = FakeDriver()
    store._driver = fake
    return store, fake
