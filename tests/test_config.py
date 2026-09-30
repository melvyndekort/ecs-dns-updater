"""Tests for ecs_dns_updater.config."""

import pytest

from ecs_dns_updater.config import Config


def _env(monkeypatch, **overrides):
    base = {
        "CLOUDFLARE_TOKEN": "token123",
        "CLOUDFLARE_ZONE_ID": "zone123",
        "DNS_RECORD_NAME": "hermes.mdekort.nl",
        "ECS_CLUSTER": "my-cluster",
        "ECS_SERVICE": "my-service",
    }
    base.update(overrides)
    for key, value in base.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)


def test_from_env_defaults(monkeypatch):
    _env(monkeypatch)
    config = Config.from_env()
    assert config.cloudflare_token == "token123"
    assert config.zone_id == "zone123"
    assert config.record_name == "hermes.mdekort.nl"
    assert config.ecs_cluster == "my-cluster"
    assert config.ecs_service == "my-service"
    assert config.record_types == ("A",)
    assert config.ttl == 300


def test_from_env_custom_ttl(monkeypatch):
    _env(monkeypatch, DNS_TTL="120")
    assert Config.from_env().ttl == 120


def test_from_env_ipv6_enabled(monkeypatch):
    _env(monkeypatch, UPDATE_IPV6="true", UPDATE_IPV4="false")
    assert Config.from_env().record_types == ("AAAA",)


def test_from_env_both_ip_versions(monkeypatch):
    _env(monkeypatch, UPDATE_IPV4="true", UPDATE_IPV6="true")
    assert Config.from_env().record_types == ("A", "AAAA")


@pytest.mark.parametrize(
    "missing",
    ["CLOUDFLARE_TOKEN", "CLOUDFLARE_ZONE_ID", "DNS_RECORD_NAME", "ECS_CLUSTER", "ECS_SERVICE"],
)
def test_from_env_missing_required(monkeypatch, missing):
    _env(monkeypatch, **{missing: None})
    with pytest.raises(ValueError, match=missing):
        Config.from_env()
