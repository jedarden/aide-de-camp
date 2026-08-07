"""
VictoriaLogs client for querying latency metrics.

Provides connection management and query execution for VictoriaLogs,
accessible through the kubectl proxy on ardenone-cluster.
"""

import httpx
import json
import logging
from typing import Dict, Any, List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class VictoriaLogsClient:
    """
    Client for querying VictoriaLogs through kubectl proxy.

    VictoriaLogs is accessible via the kubectl proxy at:
    http://traefik-ardenone-cluster:8001/api/v1/namespaces/monitoring/services/vlogs-server:9428/proxy/

    Query API: /api/v1/query (instant queries) or /api/v1/query_range (range queries)
    """

    def __init__(self, proxy_url: str = "http://traefik-ardenone-cluster:8001"):
        """
        Initialize VictoriaLogs client.

        Args:
            proxy_url: Base URL for kubectl proxy (default: traefik-ardenone-cluster)
        """
        self.proxy_url = proxy_url
        self.service_url = f"{proxy_url}/api/v1/namespaces/monitoring/services/vlogs-server:9428/proxy"
        self.query_api = f"{self.service_url}/api/v1/query"
        self.query_range_api = f"{self.service_url}/api/v1/query_range"

        # Create async client for queries
        self.client = httpx.AsyncClient(timeout=30.0, verify=False)

    async def close(self):
        """Close the HTTP client."""
        await self.client.aclose()

    async def health_check(self) -> Dict[str, Any]:
        """
        Check VictoriaLogs connectivity and health.

        Returns:
            Health check response with status and metadata
        """
        try:
            # VictoriaLogs doesn't have a dedicated health endpoint, so we query a simple metric
            response = await self.client.get(
                f"{self.service_url}/health",
                timeout=5.0
            )

            return {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "status_code": response.status_code,
                "service_url": self.service_url,
                "timestamp": datetime.now().isoformat()
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {
                "status": "unhealthy",
                "error": str(e),
                "service_url": self.service_url,
                "timestamp": datetime.now().isoformat()
            }

    async def execute_query(self, query: str, time: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute an instant query at a specific timestamp.

        Args:
            query: LogQL query string
            time: ISO format timestamp (defaults to now)

        Returns:
            Query response with data and metadata
        """
        try:
            params = {"query": query}
            if time:
                params["time"] = time

            logger.info(f"Executing instant query: {query}")
            response = await self.client.get(
                self.query_api,
                params=params
            )
            response.raise_for_status()

            data = response.json()
            return {
                "success": True,
                "query": query,
                "time": time or "now",
                "result": data.get("data", {}),
                "status": data.get("status", "unknown")
            }

        except Exception as e:
            logger.error(f"Query execution failed: {e}")
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "time": time or "now"
            }

    async def execute_range_query(
        self,
        query: str,
        start: str,
        end: str,
        step: str = "1h"
    ) -> Dict[str, Any]:
        """
        Execute a range query over a time interval.

        Args:
            query: LogQL query string
            start: Start timestamp (ISO format)
            end: End timestamp (ISO format)
            step: Query step interval (default: 1h)

        Returns:
            Query response with time-series data and metadata
        """
        try:
            params = {
                "query": query,
                "start": start,
                "end": end,
                "step": step
            }

            logger.info(f"Executing range query: {query} from {start} to {end}")
            response = await self.client.get(
                self.query_range_api,
                params=params
            )
            response.raise_for_status()

            data = response.json()
            return {
                "success": True,
                "query": query,
                "range": {"start": start, "end": end, "step": step},
                "result": data.get("data", {}),
                "status": data.get("status", "unknown")
            }

        except Exception as e:
            logger.error(f"Range query execution failed: {e}")
            return {
                "success": False,
                "query": query,
                "error": str(e),
                "range": {"start": start, "end": end, "step": step}
            }

    async def search_logs(
        self,
        query: str,
        start: str,
        end: str,
        limit: int = 1000
    ) -> Dict[str, Any]:
        """
        Search for raw log entries matching a query.

        Args:
            query: LogQL search query
            start: Start timestamp (ISO format)
            end: End timestamp (ISO format)
            limit: Maximum number of results (default: 1000)

        Returns:
            Search results with log entries
        """
        try:
            # VictoriaLogs uses /select/logql for log searches
            search_api = f"{self.service_url}/select/logql"
            params = {
                "query": query,
                "start": start,
                "end": end,
                "limit": limit
            }

            logger.info(f"Searching logs: {query} from {start} to {end}")
            response = await self.client.get(
                search_api,
                params=params
            )
            response.raise_for_status()

            data = response.json()
            return {
                "success": True,
                "query": query,
                "time_range": {"start": start, "end": end},
                "limit": limit,
                "result_count": len(data.get("data", [])),
                "results": data.get("data", [])
            }

        except Exception as e:
            logger.error(f"Log search failed: {e}")
            return {
                "success": False,
                "query": query,
                "error": str(e)
            }


# Utility functions for time range generation
def get_time_range_days_ago(days: int = 30) -> tuple[str, str]:
    """
    Get ISO format time range for N days ago to now.

    Args:
        days: Number of days to look back (default: 30)

    Returns:
        Tuple of (start_time, end_time) in ISO format
    """
    end_time = datetime.now()
    start_time = end_time - timedelta(days=days)

    return (
        start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    )


def get_time_range_custom(start_date: str, end_date: str) -> tuple[str, str]:
    """
    Get ISO format time range for custom dates.

    Args:
        start_date: Start date in YYYY-MM-DD format
        end_date: End date in YYYY-MM-DD format

    Returns:
        Tuple of (start_time, end_time) in ISO format
    """
    start_time = datetime.strptime(start_date, "%Y-%m-%d")
    end_time = datetime.strptime(end_date, "%Y-%m-%d") + timedelta(days=1) - timedelta(seconds=1)

    return (
        start_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        end_time.strftime("%Y-%m-%dT%H:%M:%SZ")
    )
