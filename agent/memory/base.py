from abc import ABC, abstractmethod
from typing import Any


class MemoryBase(ABC):
    @abstractmethod
    def get(self, key: str, default: Any = None) -> Any:
        ...

    @abstractmethod
    def save(self, key: str, value: Any) -> None:
        ...

    @abstractmethod
    def clear(self) -> None:
        ...
