"""Lab-only process-local IOCP accept repair. No stdlib/source edits."""
import ast
import asyncio
import hashlib
import inspect
import logging
import socket
import struct
import textwrap
import time
import _overlapped
from asyncio.windows_events import IocpProactor
from asyncio.proactor_events import BaseProactorEventLoop

EXPECTED = (
    'e195a4c41caabcb87a397f57e13a6fa6672b627ad8160de6d496a59c150ca5ae',
    'b30e234b98d54786174b7bc2c5eb19078b4ca1e933c0472548067517492a8e9d',
)

def fingerprint(function):
    tree = ast.parse(textwrap.dedent(inspect.getsource(function)))
    return hashlib.sha256(ast.unparse(tree.body[0]).encode()).hexdigest()

def verify_source():
    actual = (fingerprint(IocpProactor.accept),
              fingerprint(BaseProactorEventLoop._start_serving))
    if actual != EXPECTED:
        raise RuntimeError('Unknown IOCP implementation: ' + repr(actual))
    return actual


class LabProactor(IocpProactor):
    def __init__(self):
        super().__init__()
        self.counts = dict(created=0, closed=0, delivered=0, retries=0,
                           cancelled=0, fairness_yields=0, errors=0)
        self.owned = set()
        self.outers = set()
        self.inners = set()

    def _close_owned(self, conn):
        if conn in self.owned:
            conn.close()
            self.owned.remove(conn)
            self.counts['closed'] += 1

    def _post(self, listener):
        self._register_with_iocp(listener)
        conn = self._get_accept_socket(listener.family)
        self.owned.add(conn)
        self.counts['created'] += 1
        try:
            ov = _overlapped.Overlapped(0)
            ov.AcceptEx(listener.fileno(), conn.fileno())
            def completed(transferred, key, operation):
                operation.getresult()
                conn.setsockopt(socket.SOL_SOCKET, _overlapped.SO_UPDATE_ACCEPT_CONTEXT,
                                struct.pack('@P', listener.fileno()))
                conn.settimeout(listener.gettimeout())
                return conn, conn.getpeername()
            future = self._register(ov, listener, completed)
        except BaseException:
            # If posting succeeded but registration failed, retain the native
            # Overlapped until cancellation completion before releasing it.
            if 'ov' in locals() and ov.pending:
                try:
                    ov.cancel()
                    ov.getresult(True)
                except OSError:
                    pass
            self._close_owned(conn)
            raise
        self.inners.add(future)
        def clean_failure(f):
            self.inners.discard(f)
            if f.cancelled() or f.exception() is not None:
                self._close_owned(conn)
        future.add_done_callback(clean_failure)
        return future

    def accept(self, listener):
        loop = self._loop
        outer = loop.create_future()
        current = [None]
        scheduled = [None]
        burst = [0, time.monotonic()]

        def post():
            scheduled[0] = None
            if outer.done() or listener.fileno() == -1 or loop.is_closed():
                if not outer.done(): outer.cancel()
                return
            try:
                inner = self._post(listener)
                current[0] = inner
                inner.add_done_callback(settle)
            except BaseException as exc:
                if not outer.done(): outer.set_exception(exc)
                if not isinstance(exc, Exception): raise

        def settle(inner):
            try:
                if inner.cancelled():
                    if not outer.done(): outer.cancel()
                    return
                exc = inner.exception()
                if outer.done():
                    if exc is None: self._close_owned(inner.result()[0])
                    return
                if exc is None:
                    conn, addr = inner.result()
                    self.owned.remove(conn)
                    self.counts['delivered'] += 1
                    outer.set_result((conn, addr))
                    return
                if (isinstance(exc, OSError) and getattr(exc, 'winerror', None) == 64
                        and listener.fileno() != -1 and not loop.is_closed()):
                    self.counts['retries'] += 1
                    burst[0] += 1
                    if self.counts['retries'] == 1:
                        logging.warning('LAB_IOCP_REARM winerror=64 listener=%s', listener.fileno())
                    # Always leave the completion callback before re-posting.
                    # A hot burst gets a fixed 1ms yield every 64 failures,
                    # never the old growing 0.5s delay per failed connection.
                    if burst[0] % 64 == 0 and time.monotonic() - burst[1] < .01:
                        self.counts['fairness_yields'] += 1
                        scheduled[0] = loop.call_later(.001, post)
                    else:
                        scheduled[0] = loop.call_soon(post)
                    if burst[0] % 64 == 0: burst[1] = time.monotonic()
                    return
                self.counts['errors'] += 1
                outer.set_exception(exc)
            except BaseException as exc:
                if not inner.cancelled() and inner.exception() is None:
                    self._close_owned(inner.result()[0])
                if not outer.done(): outer.set_exception(exc)
                if not isinstance(exc, Exception): raise

        def finished(f):
            self.outers.discard(f)
            if f.cancelled():
                self.counts['cancelled'] += 1
                if scheduled[0] is not None: scheduled[0].cancel()
                if current[0] is not None and not current[0].done(): current[0].cancel()

        # Preserve CPython's synchronous first-post error contract.
        inner = self._post(listener)
        current[0] = inner
        self.outers.add(outer)
        inner.add_done_callback(settle)
        outer.add_done_callback(finished)
        return outer


class LabPolicy(asyncio.WindowsProactorEventLoopPolicy):
    def new_event_loop(self):
        verify_source()
        return asyncio.ProactorEventLoop(LabProactor())

def install():
    verify_source()
    asyncio.set_event_loop_policy(LabPolicy())
