"""Generic single-worker-per-key background job runner with stale-job cancellation.

Generalizes the pattern the registration live-preview worker already used (one
persistent thread draining a queue, keeping only the most recently submitted
request, plus a version counter to discard stale results) so other background
operations that mutate shared ITK/numpy state (resample, bake) don't each
reinvent their own thread + job-counter + discard dance.
"""

import queue
import threading
import logging

logger = logging.getLogger(__name__)


class Job:
    """Handle to a submitted unit of work.

    Pass to the background function so it can call `is_current()` at any point
    (including more than once, mid-run) to detect that a newer job has since
    been submitted or the caller explicitly invalidated it, and it should
    discard its result instead of writing it to shared state.
    """

    def __init__(self, runner: "JobRunner", version: int):
        self._runner = runner
        self.version = version

    def is_current(self) -> bool:
        with self._runner._lock:
            return self._runner._version == self.version


class JobRunner:
    """Runs submitted callables one at a time on a single persistent worker thread.

    If several jobs are submitted before the worker gets to them, only the
    latest survives — earlier queued (not-yet-started) jobs are silently
    dropped. A job already running when a newer one is submitted keeps running
    (it isn't preempted), but its `Job.is_current()` becomes False so it can
    notice and discard its result instead of corrupting shared state.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._version = 0
        self._pending = 0  # submitted jobs not yet finished or dropped
        self._queue: "queue.Queue" = queue.Queue()
        threading.Thread(target=self._loop, daemon=True).start()

    def submit(self, fn) -> Job:
        """Schedule fn(job) on the worker thread and return its Job handle.

        fn should check `job.is_current()` before committing results to
        shared state, since a newer submit()/invalidate() can supersede it
        mid-run.
        """
        with self._lock:
            self._version += 1
            self._pending += 1
            job = Job(self, self._version)
        self._queue.put((job, fn))
        return job

    def is_idle(self) -> bool:
        """True when no submitted job is waiting or running."""
        with self._lock:
            return self._pending == 0

    def _done(self, n=1):
        with self._lock:
            self._pending -= n

    def invalidate(self) -> None:
        """Bump the version so any in-flight job's `is_current()` becomes False,
        without submitting new work. Used when external state changes make an
        already-running job's eventual result stale before a replacement job
        exists yet (e.g. the user drags a slider while a resample is running).
        """
        with self._lock:
            self._version += 1

    def _loop(self):
        while True:
            item = self._queue.get()
            if item is None:
                return
            # Drain: only the most recently queued job survives if several
            # piled up while the worker was busy.
            while True:
                try:
                    nxt = self._queue.get_nowait()
                except queue.Empty:
                    break
                if nxt is None:
                    return
                self._done()  # the previous item is dropped
                item = nxt
            job, fn = item
            try:
                if job.is_current():
                    fn(job)
            except Exception as exc:
                logger.exception(f"JobRunner: background job raised: {exc}")
            finally:
                self._done()

    def shutdown(self) -> None:
        self._queue.put(None)


# Threads that must finish before the app exits (file saves): a daemon thread
# is killed mid-write at exit, which leaves a truncated file on disk.
_must_finish: "list[threading.Thread]" = []
_must_finish_lock = threading.Lock()


def start_must_finish(target, name=None) -> threading.Thread:
    """Run target in a background thread that the shutdown waits for
    (wait_for_must_finish): for work that must not be cut, like a file save."""
    t = threading.Thread(target=target, daemon=True, name=name)
    with _must_finish_lock:
        _must_finish[:] = [x for x in _must_finish if x.is_alive()]
        _must_finish.append(t)
    t.start()
    return t


def wait_for_must_finish(timeout=120.0) -> int:
    """Wait (up to timeout seconds in all) for the must-finish threads; returns
    how many are still running."""
    import time

    with _must_finish_lock:
        threads = [t for t in _must_finish if t.is_alive()]
    if threads:
        logger.warning(f"Waiting for {len(threads)} save(s) to finish ...")
    end = time.monotonic() + timeout
    for t in threads:
        t.join(max(0.0, end - time.monotonic()))
    left = sum(t.is_alive() for t in threads)
    if left:
        logger.error(f"{left} save(s) still running after {timeout:.0f} s: the file(s) may be incomplete")
    return left
