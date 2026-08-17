from .crawler import FeriadosCrawler
from .models import (
    CrawlResult,
    CrawlScope,
    CrawlStatus,
    CrawlTask,
)

__all__ = [
    "FeriadosCrawler",
    "CrawlTask",
    "CrawlScope",
    "CrawlStatus",
    "CrawlResult",
]