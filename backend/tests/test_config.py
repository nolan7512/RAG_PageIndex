from app.config import Settings


def test_cors_origins_accept_comma_separated_values():
    settings = Settings(
        cors_origins="http://10.30.0.15:3111,http://localhost:3111",
        frontend_origin="http://10.30.0.15:3111",
    )

    assert settings.all_cors_origins == ["http://10.30.0.15:3111", "http://localhost:3111"]


def test_frontend_origin_is_added_to_cors_origins():
    settings = Settings(cors_origins="", frontend_origin="http://10.30.0.15:3111")

    assert settings.all_cors_origins == ["http://10.30.0.15:3111"]


def test_pageindex_runs_for_short_documents_by_default():
    settings = Settings()

    assert settings.pageindex_min_pages == 1
