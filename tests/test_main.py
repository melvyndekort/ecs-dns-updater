"""Tests for ecs_dns_updater.main."""

import json

import boto3
import pytest
import responses
from moto import mock_aws

from ecs_dns_updater.config import Config
from ecs_dns_updater.main import (
    CloudflareAPI,
    get_service_public_ips,
    update_dns_if_needed,
)

CF_BASE = "https://api.cloudflare.com/client/v4"


def _config(**overrides):
    base = dict(
        cloudflare_token="token123",
        zone_id="zone123",
        record_name="hermes.mdekort.nl",
        ecs_cluster="my-cluster",
        ecs_service="my-service",
        record_types=("A",),
        ttl=300,
    )
    base.update(overrides)
    return Config(**base)


@pytest.fixture
def ecs_service_with_eni():
    """Spin up a moto ECS cluster/service/task with an ENI attached."""
    with mock_aws():
        ec2 = boto3.client("ec2", region_name="eu-west-1")
        ecs = boto3.client("ecs", region_name="eu-west-1")

        vpc = ec2.create_vpc(CidrBlock="10.0.0.0/16")["Vpc"]["VpcId"]
        subnet = ec2.create_subnet(VpcId=vpc, CidrBlock="10.0.0.0/24")["Subnet"][
            "SubnetId"
        ]
        eni = ec2.create_network_interface(SubnetId=subnet)["NetworkInterface"][
            "NetworkInterfaceId"
        ]

        ecs.create_cluster(clusterName="my-cluster")
        task_def = ecs.register_task_definition(
            family="my-task",
            containerDefinitions=[
                {"name": "app", "image": "alpine", "memory": 128}
            ],
        )["taskDefinition"]["taskDefinitionArn"]

        task = ecs.run_task(
            cluster="my-cluster",
            taskDefinition=task_def,
            count=1,
            launchType="FARGATE",
        )["tasks"][0]

        # moto's run_task doesn't attach a real ENI - patch describe_tasks
        # response shape by re-registering the task's attachments via the
        # internal moto backend is not exposed publicly, so we drive
        # get_service_public_ips against a hand-built describe_tasks-shaped
        # dict instead, and only use this fixture's clients for the ENI.
        yield {"ec2": ec2, "ecs": ecs, "eni_id": eni, "task_arn": task["taskArn"]}


def test_get_service_public_ips_no_tasks():
    with mock_aws():
        ecs = boto3.client("ecs", region_name="eu-west-1")
        ec2 = boto3.client("ec2", region_name="eu-west-1")
        ecs.create_cluster(clusterName="empty-cluster")

        result = get_service_public_ips(ecs, ec2, "empty-cluster", "no-service")
        assert result == {"ipv4": None, "ipv6": None}


def test_get_service_public_ips_reads_eni(monkeypatch, ecs_service_with_eni):
    ec2 = ecs_service_with_eni["ec2"]
    ecs = ecs_service_with_eni["ecs"]
    eni_id = ecs_service_with_eni["eni_id"]
    task_arn = ecs_service_with_eni["task_arn"]

    monkeypatch.setattr(
        ecs,
        "list_tasks",
        lambda cluster, serviceName: {"taskArns": [task_arn]},
    )
    monkeypatch.setattr(
        ecs,
        "describe_tasks",
        lambda cluster, tasks: {
            "tasks": [
                {
                    "attachments": [
                        {
                            "type": "ElasticNetworkInterface",
                            "details": [
                                {"name": "networkInterfaceId", "value": eni_id}
                            ],
                        }
                    ]
                }
            ]
        },
    )

    real_describe = ec2.describe_network_interfaces

    def fake_describe(NetworkInterfaceIds):
        response = real_describe(NetworkInterfaceIds=NetworkInterfaceIds)
        response["NetworkInterfaces"][0]["Association"] = {"PublicIp": "34.244.76.91"}
        response["NetworkInterfaces"][0]["Ipv6Addresses"] = [
            {"Ipv6Address": "2a05:d018::1", "IsPrimary": True}
        ]
        return response

    monkeypatch.setattr(ec2, "describe_network_interfaces", fake_describe)

    result = get_service_public_ips(ecs, ec2, "my-cluster", "my-service")
    assert result == {"ipv4": "34.244.76.91", "ipv6": "2a05:d018::1"}


class TestCloudflareAPI:
    @responses.activate
    def test_get_dns_record_found(self):
        responses.add(
            responses.GET,
            f"{CF_BASE}/zones/zone123/dns_records",
            json={"success": True, "result": [{"id": "rec1", "content": "1.2.3.4"}]},
        )
        api = CloudflareAPI("token123")
        record = api.get_dns_record("zone123", "hermes.mdekort.nl", "A")
        assert record == {"id": "rec1", "content": "1.2.3.4"}

    @responses.activate
    def test_get_dns_record_not_found(self):
        responses.add(
            responses.GET,
            f"{CF_BASE}/zones/zone123/dns_records",
            json={"success": True, "result": []},
        )
        api = CloudflareAPI("token123")
        assert api.get_dns_record("zone123", "hermes.mdekort.nl", "A") is None

    @responses.activate
    def test_update_dns_record_success(self):
        responses.add(
            responses.PUT,
            f"{CF_BASE}/zones/zone123/dns_records/rec1",
            json={"success": True},
        )
        api = CloudflareAPI("token123", ttl=120)
        assert api.update_dns_record(
            "zone123", "rec1", "hermes.mdekort.nl", "1.2.3.4", "A"
        )
        assert json.loads(responses.calls[0].request.body)["ttl"] == 120


@responses.activate
def test_update_dns_if_needed_updates_changed_record(monkeypatch):
    config = _config()

    monkeypatch.setattr(
        "ecs_dns_updater.main.get_service_public_ips",
        lambda ecs_client, ec2_client, cluster, service: {
            "ipv4": "34.244.76.91",
            "ipv6": None,
        },
    )
    monkeypatch.setattr("boto3.client", lambda name: object())

    responses.add(
        responses.GET,
        f"{CF_BASE}/zones/zone123/dns_records",
        json={"success": True, "result": [{"id": "rec1", "content": "1.1.1.1"}]},
    )
    responses.add(
        responses.PUT,
        f"{CF_BASE}/zones/zone123/dns_records/rec1",
        json={"success": True},
    )

    update_dns_if_needed(config)

    assert len(responses.calls) == 2


@responses.activate
def test_update_dns_if_needed_skips_when_unchanged(monkeypatch):
    config = _config()

    monkeypatch.setattr(
        "ecs_dns_updater.main.get_service_public_ips",
        lambda ecs_client, ec2_client, cluster, service: {
            "ipv4": "34.244.76.91",
            "ipv6": None,
        },
    )
    monkeypatch.setattr("boto3.client", lambda name: object())

    responses.add(
        responses.GET,
        f"{CF_BASE}/zones/zone123/dns_records",
        json={
            "success": True,
            "result": [{"id": "rec1", "content": "34.244.76.91"}],
        },
    )

    update_dns_if_needed(config)

    assert len(responses.calls) == 1  # GET only, no PUT


@responses.activate
def test_update_dns_if_needed_updates_ipv6_when_enabled(monkeypatch):
    config = _config(record_types=("AAAA",))

    monkeypatch.setattr(
        "ecs_dns_updater.main.get_service_public_ips",
        lambda ecs_client, ec2_client, cluster, service: {
            "ipv4": "34.244.76.91",
            "ipv6": "2a05:d018::1",
        },
    )
    monkeypatch.setattr("boto3.client", lambda name: object())

    responses.add(
        responses.GET,
        f"{CF_BASE}/zones/zone123/dns_records",
        json={"success": True, "result": [{"id": "rec2", "content": "::1"}]},
    )
    responses.add(
        responses.PUT,
        f"{CF_BASE}/zones/zone123/dns_records/rec2",
        json={"success": True},
    )

    update_dns_if_needed(config)

    put_calls = [c for c in responses.calls if c.request.method == "PUT"]
    assert len(put_calls) == 1
    assert '"type": "AAAA"'.encode() in put_calls[0].request.body


def test_update_dns_if_needed_no_ip_skips_gracefully(monkeypatch):
    config = _config()
    monkeypatch.setattr(
        "ecs_dns_updater.main.get_service_public_ips",
        lambda ecs_client, ec2_client, cluster, service: {
            "ipv4": None,
            "ipv6": None,
        },
    )
    monkeypatch.setattr("boto3.client", lambda name: object())

    # No responses registered - would raise ConnectionError if a request
    # were attempted, proving the "no IP" path makes no network calls.
    update_dns_if_needed(config)


@responses.activate
def test_update_dns_if_needed_uses_configured_ttl(monkeypatch):
    """The Config's ttl reaches the Cloudflare payload, not a hardcoded value."""
    config = _config(ttl=120)

    monkeypatch.setattr(
        "ecs_dns_updater.main.get_service_public_ips",
        lambda ecs_client, ec2_client, cluster, service: {
            "ipv4": "34.244.76.91",
            "ipv6": None,
        },
    )
    monkeypatch.setattr("boto3.client", lambda name: object())

    responses.add(
        responses.GET,
        f"{CF_BASE}/zones/zone123/dns_records",
        json={"success": True, "result": [{"id": "rec1", "content": "1.1.1.1"}]},
    )
    responses.add(
        responses.PUT,
        f"{CF_BASE}/zones/zone123/dns_records/rec1",
        json={"success": True},
    )

    update_dns_if_needed(config)

    assert json.loads(responses.calls[1].request.body)["ttl"] == 120
