"""Controlled feeder-lock wait, not a whole-system performance benchmark."""
import json
import multiprocessing
import threading
import time

from async_primary import _StagedPrimaryQueue


def check(staged):
    context = multiprocessing.get_context('fork')
    pending = (_StagedPrimaryQueue(maxsize=1, ctx=context) if staged
               else context.Queue(maxsize=1))
    if staged:
        pending.prepare()
    else:
        with pending._notempty:
            pending._start_thread()
    entered, release = threading.Event(), threading.Event()
    def hold():
        with pending._notempty:
            entered.set()
            release.wait(timeout=.25)
    holder = threading.Thread(target=hold); holder.start()
    try:
        assert entered.wait(timeout=1)
        before = time.monotonic()
        pending.put_nowait('same payload')
        elapsed = time.monotonic()-before
        release.set(); holder.join(timeout=1)
        assert pending.get(timeout=1) == 'same payload'
        assert pending._sem.get_value() == 1
        return dict(candidate=staged, accepted=True, wall_ms=elapsed*1000,
                    capacity_restored=True)
    finally:
        release.set(); holder.join(timeout=1)
        pending.cancel_join_thread(); pending.close()


if __name__ == '__main__':
    rows = [check(mode) for _ in range(2) for mode in (False, True)]
    assert all(row['accepted'] for row in rows)
    print(json.dumps(dict(scope=__doc__, synthetic_fixture=True, accuracy_scored=False, rows=rows)))
