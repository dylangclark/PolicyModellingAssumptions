from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from ..db import RegistryDB
from ..http import HttpClient
from ..models import CollectionResult


class SourceAdapter(ABC):
    def __init__(
        self,
        source: dict[str, Any],
        variables: dict[str, dict[str, Any]],
        db: RegistryDB,
        http: HttpClient,
    ):
        self.source = source
        self.variables = variables
        self.db = db
        self.http = http
        self.source_id = source["id"]

    @abstractmethod
    def collect(self, full_refresh: bool = False) -> CollectionResult:
        raise NotImplementedError
