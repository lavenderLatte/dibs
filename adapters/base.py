from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Site:
    site_id: str
    campground_id: str
    name: str
    park: str
    available_dates: list[str]
    url: str


class BaseAdapter(ABC):
    @abstractmethod
    def get_available_sites(self, park_name: str, date_ranges: list[dict]) -> list["Site"]:
        """
        Returns a list of Site objects available within any of the given date ranges.

        Args:
            park_name: Human-readable park name (e.g. "Yosemite National Park")
            date_ranges: list of {"start": "YYYY-MM-DD", "end": "YYYY-MM-DD"}

        Returns:
            list of Site objects
        """
        raise NotImplementedError
