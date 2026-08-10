"""
data_ingestion/graphql_reader.py
=================================
Cato Networks GraphQL API istemcisi — ilerideki entegrasyon için stub.

Bu modül şu an NotImplementedError fırlatır.
Gelecekte Cato API kimlik bilgileri ve sorgu şeması buraya eklenerek
aynı DataFrame çıktısını üretecek şekilde implement edilecektir.
"""

import pandas as pd

from data_ingestion.base_reader import BaseLogReader
from utils.logger import get_logger

logger = get_logger(__name__)


class GraphQLLogReader(BaseLogReader):
    """
    Cato Networks GraphQL API'sinden log verisi çeken sınıf.

    Args:
        api_key: Cato API anahtarı.
        account_id: Cato hesap kimliği.
        endpoint: GraphQL endpoint URL'si.

    Note:
        Bu sınıf henüz implement edilmemiştir.
        Proje ilerledikçe CSV reader ile aynı DataFrame şemasını döndürecektir.
    """

    def __init__(
        self,
        api_key: str,
        account_id: str,
        endpoint: str = "https://api.catonetworks.com/api/v1/graphql2",
    ) -> None:
        self._api_key = api_key
        self._account_id = account_id
        self._endpoint = endpoint

    def read(self) -> pd.DataFrame:
        """
        GraphQL API'sinden log verisi çeker.

        Raises:
            NotImplementedError: Bu metot henüz implement edilmemiştir.
        """
        logger.error(
            "GraphQLLogReader henüz implement edilmemiştir. "
            "Şu an yalnızca CSV girişi desteklenmektedir."
        )
        raise NotImplementedError(
            "GraphQL entegrasyonu henüz geliştirilme aşamasındadır. "
            "Lütfen şimdilik --input parametresi ile CSV dosyası kullanın."
        )

    def __repr__(self) -> str:
        return f"<GraphQLLogReader account='{self._account_id}'>"
