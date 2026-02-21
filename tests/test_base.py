from adapters.base import Site, BaseAdapter
import pytest


def test_site_dataclass_fields():
    site = Site(
        site_id="123",
        campground_id="456",
        name="Curry Cabin",
        park="Yosemite National Park",
        available_dates=["2025-07-03", "2025-07-04"],
        url="https://www.recreation.gov/camping/campsites/123",
    )
    assert site.site_id == "123"
    assert site.park == "Yosemite National Park"
    assert len(site.available_dates) == 2


def test_base_adapter_is_abstract():
    with pytest.raises(TypeError):
        BaseAdapter()
