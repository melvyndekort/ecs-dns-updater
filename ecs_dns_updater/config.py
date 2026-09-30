"""Configuration from environment variables."""

import os
from dataclasses import dataclass


@dataclass
class Config:
    """ecs-dns-updater configuration."""

    cloudflare_token: str
    zone_id: str
    record_name: str
    ecs_cluster: str
    ecs_service: str
    record_types: tuple[str, ...] = ("A",)
    ttl: int = 300

    @classmethod
    def from_env(cls) -> "Config":
        """Create config from environment variables."""
        token = os.getenv("CLOUDFLARE_TOKEN")
        zone_id = os.getenv("CLOUDFLARE_ZONE_ID")
        record_name = os.getenv("DNS_RECORD_NAME")
        cluster = os.getenv("ECS_CLUSTER")
        service = os.getenv("ECS_SERVICE")

        if not token:
            raise ValueError("CLOUDFLARE_TOKEN environment variable is required")
        if not zone_id:
            raise ValueError("CLOUDFLARE_ZONE_ID environment variable is required")
        if not record_name:
            raise ValueError("DNS_RECORD_NAME environment variable is required")
        if not cluster:
            raise ValueError("ECS_CLUSTER environment variable is required")
        if not service:
            raise ValueError("ECS_SERVICE environment variable is required")

        return cls(
            cloudflare_token=token,
            zone_id=zone_id,
            record_name=record_name,
            ecs_cluster=cluster,
            ecs_service=service,
            record_types=cls._record_types_from_env(),
            ttl=int(os.getenv("DNS_TTL", "300")),
        )

    @staticmethod
    def _record_types_from_env() -> tuple[str, ...]:
        """Which record types to update, from the UPDATE_IPV4/6 toggles."""
        types = []
        if os.getenv("UPDATE_IPV4", "true").lower() == "true":
            types.append("A")
        if os.getenv("UPDATE_IPV6", "false").lower() == "true":
            types.append("AAAA")
        return tuple(types)
