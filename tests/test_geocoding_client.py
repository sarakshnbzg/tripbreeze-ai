"""Tests for infrastructure/apis/geocoding_client.py."""

import requests

from infrastructure.apis import geocoding_client


class DummyResponse:
    def __init__(self, payload, should_raise: Exception | None = None):
        self.payload = payload
        self.should_raise = should_raise

    def raise_for_status(self):
        if self.should_raise:
            raise self.should_raise

    def json(self):
        return self.payload


class TestResolveDestinationCountry:
    def setup_method(self):
        geocoding_client.geocode_place.cache_clear()
        geocoding_client.resolve_destination_country.cache_clear()

    def test_uses_db_mapping_before_local_or_api(self, monkeypatch):
        monkeypatch.setattr(geocoding_client, "load_place_country", lambda destination: "France")

        def fail_get(*args, **kwargs):
            raise AssertionError("API should not be called for DB matches")

        monkeypatch.setattr(geocoding_client.requests, "get", fail_get)

        assert geocoding_client.resolve_destination_country("Paris") == "France"

    def test_uses_local_mapping_before_api(self, monkeypatch):
        monkeypatch.setattr(geocoding_client, "load_place_country", lambda destination: "")

        def fail_get(*args, **kwargs):
            raise AssertionError("API should not be called for local matches")

        monkeypatch.setattr(geocoding_client.requests, "get", fail_get)

        assert geocoding_client.resolve_destination_country("Paris") == "France"

    def test_falls_back_to_geocoder_for_unknown_city(self, monkeypatch):
        saved = {}
        monkeypatch.setattr(geocoding_client, "load_place_country", lambda destination: "")
        monkeypatch.setattr(
            geocoding_client,
            "save_place_alias",
            lambda destination, **kwargs: saved.update({"destination": destination, **kwargs}),
        )

        def fake_get(url, params, timeout):
            assert url == geocoding_client.GEOCODE_URL
            assert params["name"] == "Marrakesh"
            return DummyResponse({"results": [{"country": "Morocco"}]})

        monkeypatch.setattr(geocoding_client.requests, "get", fake_get)

        assert geocoding_client.resolve_destination_country("Marrakesh") == "Morocco"
        assert saved == {
            "destination": "Marrakesh",
            "country_name": "Morocco",
            "source": "geocoder",
        }

    def test_returns_empty_string_when_geocoder_has_no_results(self, monkeypatch):
        monkeypatch.setattr(geocoding_client, "load_place_country", lambda destination: "")
        monkeypatch.setattr(
            geocoding_client.requests,
            "get",
            lambda *args, **kwargs: DummyResponse({"results": []}),
        )

        assert geocoding_client.resolve_destination_country("Nowhereville") == ""

    def test_returns_empty_string_on_request_exception(self, monkeypatch):
        monkeypatch.setattr(geocoding_client, "load_place_country", lambda destination: "")

        def fake_get(*args, **kwargs):
            raise requests.RequestException("boom")

        monkeypatch.setattr(geocoding_client.requests, "get", fake_get)

        assert geocoding_client.resolve_destination_country("Marrakesh") == ""

    def test_db_lookup_failure_falls_back_cleanly(self, monkeypatch):
        def fail_lookup(destination):
            raise RuntimeError("db unavailable")

        monkeypatch.setattr(geocoding_client, "load_place_country", fail_lookup)
        monkeypatch.setattr(geocoding_client.requests, "get", lambda *args, **kwargs: DummyResponse({"results": [{"country": "Morocco"}]}))
        monkeypatch.setattr(geocoding_client, "save_place_alias", lambda *args, **kwargs: None)

        assert geocoding_client.resolve_destination_country("Marrakesh") == "Morocco"


class TestGeocodePlace:
    def setup_method(self):
        geocoding_client.geocode_place.cache_clear()

    def test_returns_first_geocoded_place(self, monkeypatch):
        def fake_get(url, params, timeout):
            assert url == geocoding_client.GEOCODE_URL
            assert params["name"] == "Paris"
            return DummyResponse(
                {
                    "results": [
                        {
                            "latitude": 48.8566,
                            "longitude": 2.3522,
                            "name": "Paris",
                            "country": "France",
                        }
                    ]
                }
            )

        monkeypatch.setattr(geocoding_client.requests, "get", fake_get)

        result = geocoding_client.geocode_place("Paris")

        assert result is not None
        assert result.latitude == 48.8566
        assert result.longitude == 2.3522
        assert result.name == "Paris"
        assert result.country == "France"

    def test_returns_none_when_no_results(self, monkeypatch):
        monkeypatch.setattr(
            geocoding_client.requests,
            "get",
            lambda *args, **kwargs: DummyResponse({"results": []}),
        )

        assert geocoding_client.geocode_place("Nowhereville") is None
