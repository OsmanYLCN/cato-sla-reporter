"""
data_ingestion/base_reader.py
==============================
Tüm log okuyucuların implement etmesi gereken soyut temel sınıf.

Açık/Kapalı Prensibi (OCP) gereği:
    - Yeni bir veri kaynağı (GraphQL, REST, DB vb.) eklemek için bu sınıftan
      türetmek ve `read()` metodunu implement etmek yeterlidir.
    - main.py gibi üst katmanlar kaynağın türünden bağımsız çalışır.
"""

from abc import ABC, abstractmethod

import pandas as pd


class BaseLogReader(ABC):
    """
    Log okuyucular için soyut temel sınıf.

    Alt sınıfların `read()` metodunu implement etmesi zorunludur.
    """

    @abstractmethod
    def read(self) -> pd.DataFrame:
        """
        Ham log verilerini okuyarak DataFrame olarak döndürür.

        Returns:
            En az şu sütunları içeren pd.DataFrame:
                - src_site_name (str)
                - time (str | datetime): UTC formatında
                - event_sub_type (str): 'Connected' veya 'Disconnected'
                - socket_interface (str): 'WAN1', 'WAN2', 'PRIMARY1' vb.
                - socket_role (str): 'primary' veya 'secondary'

        Raises:
            FileNotFoundError: Kaynak dosya/endpoint bulunamadığında.
            ValueError: Zorunlu sütunlar eksikse veya format geçersizse.
            RuntimeError: Okuma sırasında beklenmedik bir hata oluştuğunda.
        """
        ...

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"
