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
    update_ipv4: bool = True
    update_ipv6: bool = False

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
            update_ipv4=os.getenv("UPDATE_IPV4", "true").lower() == "true",
            update_ipv6=os.getenv("UPDATE_IPV6", "false").lower() == "true",
        )
