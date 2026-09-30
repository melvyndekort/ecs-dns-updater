"""Update Cloudflare A/AAAA records to an ECS service's own public IP.

Runs once, as a non-essential sidecar container in the same ECS task
definition as the primary workload. On task start it looks up its own
service's running task, reads the public IPv4/IPv6 off the attached ENI,
and upserts the matching Cloudflare DNS record(s) if they've changed, then
exits. No daemon, no polling - the next task start (after a restart) reruns
it and refreshes the record again.
"""

import logging
import sys
from typing import Any

import boto3
import requests
from botocore.exceptions import ClientError

from ecs_dns_updater.config import Config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class CloudflareAPI:
    """Minimal Cloudflare DNS API client."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.base_url = "https://api.cloudflare.com/client/v4"
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

    def get_dns_record(
        self, zone_id: str, record_name: str, record_type: str
    ) -> dict[str, Any] | None:
        """Get a DNS record by name and type."""
        try:
            response = requests.get(
                f"{self.base_url}/zones/{zone_id}/dns_records",
                headers=self.headers,
                params={"name": record_name, "type": record_type},
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()
            if data["success"] and data["result"]:
                return data["result"][0]
            return None
        except requests.RequestException:
            logger.error("Failed to get %s record", record_type)
            raise

    def update_dns_record(
        self,
        zone_id: str,
        record_id: str,
        record_name: str,
        ip_address: str,
        record_type: str,
    ) -> bool:
        """Update a DNS record with a new IP address."""
        try:
            response = requests.put(
                f"{self.base_url}/zones/{zone_id}/dns_records/{record_id}",
                headers=self.headers,
                json={
                    "type": record_type,
                    "name": record_name,
                    "content": ip_address,
                    "ttl": 300,
                },
                timeout=30,
            )
            response.raise_for_status()

            data = response.json()
            return data["success"]
        except requests.RequestException:
            logger.error("Failed to update %s record", record_type)
            raise


def _ips_from_eni(ec2_client: Any, eni_id: str) -> dict[str, str | None] | None:
    """Look up the public IPv4/IPv6 for a single ENI. None if it has neither."""
    try:
        eni_response = ec2_client.describe_network_interfaces(
            NetworkInterfaceIds=[eni_id]
        )
    except ClientError:
        logger.warning("Failed to get IPs for ENI %s", eni_id)
        return None

    if not eni_response["NetworkInterfaces"]:
        return None

    eni = eni_response["NetworkInterfaces"][0]
    ipv4 = eni.get("Association", {}).get("PublicIp")
    ipv6 = None
    for addr in eni.get("Ipv6Addresses", []):
        if addr.get("IsPrimary", True):
            ipv6 = addr.get("Ipv6Address")
            break
    return {"ipv4": ipv4, "ipv6": ipv6}


def _eni_ids_from_task(task: dict[str, Any]) -> list[str]:
    """Extract ENI ids from a describe_tasks task entry."""
    eni_ids = []
    for attachment in task.get("attachments", []):
        if attachment["type"] != "ElasticNetworkInterface":
            continue
        for detail in attachment["details"]:
            if detail["name"] == "networkInterfaceId":
                eni_ids.append(detail["value"])
    return eni_ids


def get_service_public_ips(
    ecs_client: Any, ec2_client: Any, cluster: str, service: str
) -> dict[str, str | None]:
    """Get the public IPv4/IPv6 addresses for the first running task of a service."""
    empty: dict[str, str | None] = {"ipv4": None, "ipv6": None}

    try:
        tasks_response = ecs_client.list_tasks(cluster=cluster, serviceName=service)
    except ClientError:
        logger.error("AWS error listing tasks")
        raise

    if not tasks_response["taskArns"]:
        logger.info("No running tasks found")
        return empty

    try:
        task_details = ecs_client.describe_tasks(
            cluster=cluster, tasks=tasks_response["taskArns"]
        )
    except ClientError:
        logger.error("AWS error describing tasks")
        raise

    for task in task_details["tasks"]:
        for eni_id in _eni_ids_from_task(task):
            ips = _ips_from_eni(ec2_client, eni_id)
            if ips is not None:
                return ips

    return empty


def _update_record(
    cloudflare: CloudflareAPI,
    config: Config,
    ip_address: str | None,
    record_type: str,
) -> None:
    """Fetch, compare, and update a single DNS record if needed."""
    if not ip_address:
        logger.info(
            "No %s address found, skipping %s update", record_type, record_type
        )
        return

    logger.info("Current service %s: %s", record_type, ip_address)

    dns_record = cloudflare.get_dns_record(
        config.zone_id, config.record_name, record_type
    )
    if not dns_record:
        logger.error("%s record %s not found", record_type, config.record_name)
        return

    current_dns_ip = dns_record["content"]
    logger.info("Current DNS %s: %s", record_type, current_dns_ip)

    if ip_address == current_dns_ip:
        logger.info("%s record is already up to date", record_type)
        return

    logger.info(
        "Updating %s record from %s to %s", record_type, current_dns_ip, ip_address
    )
    success = cloudflare.update_dns_record(
        config.zone_id, dns_record["id"], config.record_name, ip_address, record_type
    )
    if success:
        logger.info("%s record updated successfully", record_type)
    else:
        logger.error("Failed to update %s record", record_type)


def update_dns_if_needed(config: Config) -> None:
    """Update A/AAAA records if the service's public IPs have changed."""
    ecs_client = boto3.client("ecs")
    ec2_client = boto3.client("ec2")
    cloudflare = CloudflareAPI(config.cloudflare_token)

    ips = get_service_public_ips(
        ecs_client, ec2_client, config.ecs_cluster, config.ecs_service
    )

    if config.update_ipv4:
        _update_record(cloudflare, config, ips["ipv4"], "A")
    if config.update_ipv6:
        _update_record(cloudflare, config, ips["ipv6"], "AAAA")


def main() -> None:
    """Main entry point."""
    try:
        config = Config.from_env()
        logger.info("Starting DNS updater for %s", config.record_name)

        update_dns_if_needed(config)
        logger.info("DNS update complete, exiting successfully")
        sys.exit(0)

    except ValueError:
        logger.error("Configuration error")
        sys.exit(1)
    except KeyboardInterrupt:
        logger.info("DNS updater stopped by user")
        sys.exit(0)
    except Exception:  # pylint: disable=broad-exception-caught
        # Top-level guard: any unexpected failure must exit non-zero so ECS
        # marks the sidecar container failed rather than silently succeeding.
        logger.error("DNS updater failed", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
