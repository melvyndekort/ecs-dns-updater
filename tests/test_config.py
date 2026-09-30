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
    assert config.update_ipv4 is True
    assert config.update_ipv6 is False


def test_from_env_ipv6_enabled(monkeypatch):
    _env(monkeypatch, UPDATE_IPV6="true", UPDATE_IPV4="false")
    config = Config.from_env()
    assert config.update_ipv4 is False
    assert config.update_ipv6 is True


@pytest.mark.parametrize(
    "missing",
    ["CLOUDFLARE_TOKEN", "CLOUDFLARE_ZONE_ID", "DNS_RECORD_NAME", "ECS_CLUSTER", "ECS_SERVICE"],
)
def test_from_env_missing_required(monkeypatch, missing):
    _env(monkeypatch, **{missing: None})
    with pytest.raises(ValueError, match=missing):
        Config.from_env()
