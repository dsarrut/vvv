"""Generic single-worker-per-key background job runner with stale-job cancellation.

Generalizes the pattern the registration live-preview worker already used (one
persistent thread draining a queue, keeping only the most recently submitted
request, plus a version counter to discard stale results) so other background
operations that mutate shared ITK/numpy state (resample, bake) don't each
reinvent their own thread + job-counter + discard dance.
"""

import queue
import threading


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
            job = Job(self, self._version)
        self._queue.put((job, fn))
        return job

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
                item = nxt
            job, fn = item
            if not job.is_current():
                continue
            try:
                fn(job)
            except Exception as exc:
                print(f"JobRunner: background job raised: {exc}")

    def shutdown(self) -> None:
        self._queue.put(None)
