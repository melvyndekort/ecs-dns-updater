# ecs-dns-updater

> For global standards, way-of-workings, and pre-commit checklist, see `~/.claude/CLAUDE.md`

## Role

Python developer and DevOps engineer.

## What This Does

Generic, single-purpose sidecar container: on ECS task start, reads its own
service's public IPv4/IPv6 off the attached ENI and upserts a Cloudflare
A/AAAA record if it's changed, then exits. No daemon, no polling — reran on
every task restart by ECS itself starting the container fresh.

Extracted from minecraft-server's `mc-dns-updater` (which was
Minecraft-specific in name only — the code had no Minecraft logic) so
multiple repos (minecraft-server, hermes-agent) can share one image
instead of each maintaining a slightly different DNS-updater.

## Repository Structure

- `ecs_dns_updater/` — Application source (`config.py`, `main.py`)
- `tests/` — Test suite (`moto` for AWS, `responses` for Cloudflare)
- `Dockerfile` — Multi-stage Alpine build
- `Makefile` — `install`, `test`, `lint`, `run`

## Deployment

- Container image: `ghcr.io/melvyndekort/ecs-dns-updater:latest`
- Consumed as a non-essential sidecar in an ECS task definition — see README.md

## Related Repositories

- `~/src/melvyndekort/minecraft-server` — first consumer, original source of this code
- `~/src/melvyndekort/hermes-agent` — second consumer
- `~/src/melvyndekort/tf-cloudflare` — provides scoped Cloudflare API tokens per consumer
- `~/src/melvyndekort/tf-github` — repo registration (`terraform/repositories.yaml`)
