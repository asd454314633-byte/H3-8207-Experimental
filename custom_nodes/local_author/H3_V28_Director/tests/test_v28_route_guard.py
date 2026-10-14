"""The same-origin / loopback guard in v28_routes - the HTTP layer's front door.

Why this file exists (P11 TEST1, real instance on port 8197):
    `reject_request()` used to read the peer as
        request.remote.hostname or request.remote.host
    but aiohttp declares `request.remote` as `str | None` (web_request.py, the
    peer IP of the accepting socket). On a str that is an AttributeError, and
    since `register_director_routes()` wraps EVERY mutating handler in
    `guarded()` (v28_routes.py: `decorated = guarded(handler) if method in
    _MUTATING else handler`), the live server answered every POST - including the
    browser's own - with a bare `500 Internal Server Error`, no JSON body,
    and none of the Chinese refusal contract the card depends on.

    None of the 208 static tests could have caught it: no test imported
    `v28_routes` at all, and a hand-made request mock is exactly the thing that
    cannot reproduce a shape only the real socket produces. So this file does two
    unusual things on purpose:
      * it asserts the buggy expression WOULD have raised on the same fake
        (a positive control - it proves the fixture carries the real shape), and
      * it drives the guard through a REAL aiohttp test server, so `remote` comes
        off a live transport instead of from an imagination.
"""
from __future__ import annotations

import asyncio
import os
import sys
import types
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _v28_bootstrap as B                                                 # noqa: E402


HOST = "127.0.0.1:8197"
ORIGIN = "http://127.0.0.1:8197"


class FakeRequest:
    """Minimal stand-in for aiohttp.web.Request.

    `remote` is deliberately a plain str, matching aiohttp's own declaration
    (`def remote(self) -> str | None`). The whole point of the rewrite is that
    nobody gets to pretend it is an object again.
    """

    def __init__(self, *, method="GET", remote="127.0.0.1", host=HOST,
                 origin=None, referer=None, sec_fetch_site=None):
        self.method = method
        self.remote = remote
        self.headers = {"Host": host} if host else {}
        if origin is not None:
            self.headers["Origin"] = origin
        if referer is not None:
            self.headers["Referer"] = referer
        if sec_fetch_site is not None:
            self.headers["Sec-Fetch-Site"] = sec_fetch_site


class RouteGuardCase(unittest.TestCase):
    def setUp(self):
        self.env = B.fresh_env()
        ctx = self.env.__enter__()
        self.addCleanup(self.env.__exit__, None, None, None)
        self.RT = B.load("v28_routes")
        self.ctx = ctx

    # ------------------------------------------------------------------ #
    # 0. the fixture itself has to be the shape that broke production
    # ------------------------------------------------------------------ #
    def test_positive_control_old_expression_raises_on_this_fixture(self):
        req = FakeRequest()
        self.assertIsInstance(req.remote, str)
        with self.assertRaises(AttributeError):
            (req.remote.hostname or req.remote.host or "")   # the shipped bug

    def test_aiohttp_declares_remote_as_str(self):
        """Pin the assumption to the installed aiohttp, not to a comment.

        The invariant under test is that ``remote`` returns a *string or None*
        (never a list/object), which is the whole reason ``_peer_host`` tolerates
        both shapes. aiohttp 3.13+ spells the annotation ``Optional[str]`` while
        older lines used ``str | None``; both mean the same thing, so accept either
        spelling rather than pinning the exact source text.
        """
        import inspect
        from aiohttp.web_request import BaseRequest
        src = inspect.getsource(BaseRequest)
        i = src.find("def remote(")
        self.assertGreater(i, -1, "aiohttp no longer defines remote(); revisit the guard")
        signature = src[i:i + 120].splitlines()[0]
        normalised = signature.replace("str|None", "str | None")
        self.assertTrue(
            ("str | None" in normalised) or ("Optional[str]" in signature),
            f"aiohttp remote() return type is no longer str-or-None: {signature!r}")

    # ------------------------------------------------------------------ #
    # 1. the regression: reading the peer must never raise
    # ------------------------------------------------------------------ #
    def test_peer_host_handles_the_three_shapes(self):
        self.assertEqual(self.RT._peer_host(FakeRequest(remote="127.0.0.1")), "127.0.0.1")
        self.assertEqual(self.RT._peer_host(FakeRequest(remote="::1")), "::1")
        self.assertEqual(self.RT._peer_host(FakeRequest(remote="[::1]")), "::1")
        self.assertEqual(self.RT._peer_host(FakeRequest(remote=" FE80::1 ")), "fe80::1")
        self.assertEqual(self.RT._peer_host(FakeRequest(remote=None)), "")
        obj = types.SimpleNamespace(hostname="", host="10.1.2.3")
        self.assertEqual(self.RT._peer_host(FakeRequest(remote=obj)), "10.1.2.3")
        obj2 = types.SimpleNamespace(hostname="localhost", host="10.1.2.3")
        self.assertEqual(self.RT._peer_host(FakeRequest(remote=obj2)), "localhost")

    def test_loopback_read_is_allowed(self):
        self.assertIsNone(self.RT.reject_request(FakeRequest(method="GET")))
        for peer in ("127.0.0.1", "::1", "localhost"):
            self.assertIsNone(self.RT.reject_request(FakeRequest(method="POST",
                                                                  remote=peer,
                                                                  origin=ORIGIN)),
                              peer)

    def test_non_loopback_peer_is_refused_even_with_matching_origin(self):
        out = self.RT.reject_request(FakeRequest(method="POST", remote="192.168.1.9",
                                                 origin=ORIGIN))
        self.assertIsNotNone(out)
        self.assertEqual(out.status, 403)

    def test_refusal_body_is_json_with_the_error_key(self):
        out = self.RT.reject_request(FakeRequest(method="POST", remote="10.0.0.2",
                                                 origin=ORIGIN))
        self.assertIn('"error"', out.body.decode("utf-8"))

    # ------------------------------------------------------------------ #
    # 2. the CSRF half of the guard
    # ------------------------------------------------------------------ #
    def test_mutating_without_origin_or_referer_is_refused(self):
        out = self.RT.reject_request(FakeRequest(method="POST"))
        self.assertIsNotNone(out)
        self.assertEqual(out.status, 403)

    def test_referer_is_accepted_as_the_fallback(self):
        self.assertIsNone(self.RT.reject_request(FakeRequest(method="POST",
                                                             referer=ORIGIN + "/")))

    def test_port_mismatch_is_refused(self):
        out = self.RT.reject_request(FakeRequest(method="POST",
                                                 origin="http://127.0.0.1:9999"))
        self.assertIsNotNone(out)
        self.assertEqual(out.status, 403)

    def test_cross_site_fetch_policy_is_refused(self):
        out = self.RT.reject_request(FakeRequest(method="POST", origin=ORIGIN,
                                                 sec_fetch_site="cross-site"))
        self.assertIsNotNone(out)
        self.assertEqual(out.status, 403)

    def test_missing_host_header_is_refused(self):
        out = self.RT.reject_request(FakeRequest(method="POST", host=None,
                                                 origin=ORIGIN))
        self.assertIsNotNone(out)
        self.assertEqual(out.status, 403)

    def test_reads_are_not_origin_gated(self):
        # a GET carries no Origin from an address-bar visit; it must still work
        # for a loopback peer, which is what the sidebar's fetch() relies on.
        self.assertIsNone(self.RT.reject_request(FakeRequest(method="GET")))

    # ------------------------------------------------------------------ #
    # 3. end-to-end over a REAL socket
    # ------------------------------------------------------------------ #
    def test_guarded_route_over_real_aiohttp_transport(self):
        from aiohttp import web
        from aiohttp.test_utils import TestServer
        import aiohttp

        seen = {}

        async def ok(request):
            seen["remote_type"] = type(request.remote).__name__
            seen["remote"] = request.remote
            return web.json_response({"reached": True})

        app = web.Application()
        app.router.add_get("/probe", self.RT.guarded(ok))
        app.router.add_post("/probe", self.RT.guarded(ok))

        async def run():
            server = TestServer(app, host="127.0.0.1")
            await server.start_server()
            try:
                conn = aiohttp.TCPConnector()
                async with aiohttp.ClientSession(connector=conn) as s:
                    g = await s.get(server.make_url("/probe"))
                    g_status = g.status
                    p_bad = await s.post(server.make_url("/probe"))
                    p_bad_status = p_bad.status
                    p_bad_body = await p_bad.text()
                    p_ok = await s.post(server.make_url("/probe"),
                                        headers={"Origin": str(server.make_url("/"))[:-1]})
                    p_ok_status = p_ok.status
                    p_ok_body = await p_ok.text()
            finally:
                await server.close()
            return (g_status, p_bad_status, p_bad_body, p_ok_status, p_ok_body)

        g_status, p_bad_status, p_bad_body, p_ok_status, p_ok_body = asyncio.run(run())

        # the transport really hands us a str: this is the fact the 500 hinged on
        self.assertEqual(seen.get("remote_type"), "str", seen)
        self.assertIn(seen.get("remote"), ("127.0.0.1", "::1", "localhost"))
        self.assertEqual(g_status, 200)
        # POST with no Origin -> the guard's own 403 JSON, never a bare 500
        self.assertEqual(p_bad_status, 403, p_bad_body)
        self.assertIn("error", p_bad_body)
        self.assertNotIn("Internal Server Error", p_bad_body)
        # POST with same-origin Origin -> reaches the handler
        self.assertEqual(p_ok_status, 200, p_ok_body)
        self.assertIn("reached", p_ok_body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
