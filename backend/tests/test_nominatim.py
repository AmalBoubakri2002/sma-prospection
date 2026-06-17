import asyncio

from app.agents.enrichissement.nominatim import geocode_address


def test_geocode_address_empty():
    result = asyncio.run(geocode_address(""))
    assert result is None


def test_geocode_address_none_like():
    result = asyncio.run(geocode_address("   "))
    assert result is None
