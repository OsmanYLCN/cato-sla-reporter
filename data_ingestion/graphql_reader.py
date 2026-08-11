import pandas as pd

from data_ingestion.base_reader import BaseLogReader
from utils.logger import get_logger

logger = get_logger(__name__)


class GraphQLLogReader(BaseLogReader):
    """Cato Networks GraphQL API okuyucusu (taslak)."""

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
        """API entegrasyonu henüz tamamlanmadığı için hata fırlatır."""
        logger.error(
            "Şu an yalnızca CSV girişi desteklenmektedir."
        )
        raise NotImplementedError(
            "GraphQL entegrasyonu henüz yok. "
            "Lütfen şimdilik --input parametresi ile CSV dosyası kullanın."
        )

    def __repr__(self) -> str:
        return f"<GraphQLLogReader account='{self._account_id}'>"
