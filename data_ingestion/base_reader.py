from abc import ABC, abstractmethod

import pandas as pd

# Veri okuma modülleri için soyut taban sınıf
class BaseLogReader(ABC):
    """Log okuyucu modüller için soyut taban sınıf."""

    @abstractmethod
    def read(self) -> pd.DataFrame:
        """Log kaynağından ham veriyi okuyarak DataFrame döndürür."""
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
