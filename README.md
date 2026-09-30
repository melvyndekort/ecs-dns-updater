# ecs-dns-updater

Updates a Cloudflare A/AAAA record to an ECS service's own public IP address.

## Why

An ECS Fargate service with a public IP (no NAT/ALB) gets a new IP every
time its task restarts. This container runs as a **non-essential sidecar**
in the same task definition, once per task start: it looks up its own
service's task, reads the public IPv4/IPv6 off the attached ENI, and
upserts the matching Cloudflare DNS record if it's changed. Then it exits.
No daemon, no polling — the next task restart reruns it.

## Configuration (environment variables)

| Variable              | Required | Default | Description                                  |
|------------------------|----------|---------|-----------------------------------------------|
| `CLOUDFLARE_TOKEN`     | yes      |         | Cloudflare API token, scoped to DNS edit on the zone |
| `CLOUDFLARE_ZONE_ID`   | yes      |         | Cloudflare zone id                            |
| `DNS_RECORD_NAME`      | yes      |         | Fully-qualified record name, e.g. `hermes.mdekort.nl` |
| `ECS_CLUSTER`          | yes      |         | ECS cluster name                              |
| `ECS_SERVICE`          | yes      |         | ECS service name                              |
| `UPDATE_IPV4`          | no       | `true`  | Update the `A` record                         |
| `UPDATE_IPV6`          | no       | `false` | Update the `AAAA` record                      |

## Required IAM permissions

- `ecs:ListTasks`, `ecs:DescribeTasks` on the cluster/service
- `ec2:DescribeNetworkInterfaces`

## Usage as an ECS sidecar

Add as a non-essential container in the task definition, running the same
task role (or a scoped-down one with just the permissions above), sharing
no ports/volumes with the primary container. It exits 0 on success/no-op
and non-zero on failure — ECS will show the container as stopped, which is
expected and does not affect the primary container's health.

The image is published multi-arch (`linux/amd64` and `linux/arm64`), so it
works in both x86_64 and ARM64 Fargate task definitions. Note that
`essential = false` only covers *runtime* failures: if the image cannot be
pulled at all, ECS fails the whole task before any container starts, taking
the primary container down with it.

## Related repositories

- `~/src/melvyndekort/minecraft-server` — original consumer
- `~/src/melvyndekort/hermes-agent` — second consumer
- `~/src/melvyndekort/tf-cloudflare` — provides the scoped API token via remote state
