import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch


# Load the submodule's Query without importing its plotting dependencies.
spec = importlib.util.spec_from_file_location(
    "query_base", Path(__file__).resolve().parents[1] / "notion-query/notion/query.py"
)
base = importlib.util.module_from_spec(spec)
with patch.dict(sys.modules, {
    "PIL": Mock(), "matplotlib": Mock(), "matplotlib.pyplot": Mock(), "numpy": Mock()
}):
    spec.loader.exec_module(base)
with patch.dict(sys.modules, {"notion": base}):
    import notion_client


def response(status=200, data=None, headers=None):
    return Mock(status_code=status, headers=headers or {}, text=f"error {status}",
                json=Mock(return_value=data or {"results": [], "has_more": False}))


class QueryTests(unittest.TestCase):
    def setUp(self):
        self.query = notion_client.Query("test-token")
        self.request = patch.object(notion_client.requests, "request").start()
        self.sleep = patch.object(notion_client.time, "sleep").start()
        self.addCleanup(patch.stopall)

    def test_retry_body_delay_then_return_images(self):
        image = {"type": "image"}
        self.request.side_effect = [
            response(429, {"additional_data": {"retry_after": "9"}}),
            response(data={"results": [image]}),
        ]
        self.assertEqual(self.query.get_blocks("page", {"type": "image"}), [image])
        self.sleep.assert_called_once_with(9)

    def test_header_delay_takes_precedence(self):
        self.request.side_effect = [
            response(429, {"additional_data": {"retry_after": "9"}}, {"Retry-After": "12"}),
            response(),
        ]
        self.query.get_pages(database_id="db")
        self.sleep.assert_called_once_with(12)

    def test_exhaustion_raises_instead_of_returning_empty(self):
        self.request.return_value = response(429)
        with self.assertRaisesRegex(RuntimeError, "429"):
            self.query.get_blocks("page")
        self.assertEqual(self.request.call_count, 6)
        self.assertEqual([call.args[0] for call in self.sleep.call_args_list], [1, 2, 4, 8, 16])

    def test_auth_failure_does_not_retry(self):
        self.request.return_value = response(401)
        with self.assertRaisesRegex(RuntimeError, "401"):
            self.query.get_pages(database_id="db")
        self.sleep.assert_not_called()
        self.request.assert_called_once()

    def test_both_endpoints_paginate(self):
        for method, kwargs, argument in [
            (self.query.get_blocks, {"page_id": "page"}, "params"),
            (self.query.get_pages, {"database_id": "db"}, "json"),
        ]:
            with self.subTest(method=method.__name__):
                self.request.side_effect = [
                    response(data={"results": [{"id": "first"}], "has_more": True, "next_cursor": "cursor"}),
                    response(data={"results": [{"id": "second"}], "has_more": False}),
                ]
                self.assertEqual(method(**kwargs), [{"id": "first"}, {"id": "second"}])
                self.assertEqual(self.request.call_args.kwargs[argument]["start_cursor"], "cursor")


if __name__ == "__main__":
    unittest.main()
