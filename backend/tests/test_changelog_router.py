"""Smoke tests for the changelog router — import checks and response envelope."""
from app.routers.changelog import _api_response


class TestChangelogApiResponse:
    def test_success(self):
        r = _api_response(data={"x": 1})
        assert r["success"] is True
        assert r["data"] == {"x": 1}
        assert r["error"] is None
        assert "timestamp" in r

    def test_error(self):
        r = _api_response(error="boom")
        assert r["success"] is False
        assert r["data"] is None
        assert r["error"] == "boom"


class TestChangelogRouterImports:
    def test_import_list(self):
        from app.routers.changelog import list_changelog
        assert callable(list_changelog)

    def test_import_create(self):
        from app.routers.changelog import create_manual_entry
        assert callable(create_manual_entry)

    def test_import_update(self):
        from app.routers.changelog import update_manual_entry
        assert callable(update_manual_entry)

    def test_import_delete(self):
        from app.routers.changelog import delete_manual_entry
        assert callable(delete_manual_entry)

    def test_import_categories(self):
        from app.routers.changelog import list_categories
        assert callable(list_categories)

    def test_import_resolve_context(self):
        from app.routers.changelog import resolve_context
        assert callable(resolve_context)


class TestChangelogRoutesRegistered:
    def test_all_endpoints_wired(self):
        from app.main import app

        paths = {getattr(r, "path", "") for r in app.routes}
        assert "/api/dashboard/country/changelog" in paths
        assert "/api/changelog/manual" in paths
        assert "/api/changelog/manual/{entry_id}" in paths
        assert "/api/changelog/categories" in paths
        assert "/api/changelog/resolve-context" in paths
