.PHONY: clean install update-deps test lint format run
.DEFAULT_GOAL: test

clean:
	@rm -rf .pytest_cache dist __pycache__ */__pycache__ .coverage

install: clean
	@uv sync --all-extras

update-deps:
	@uv sync --upgrade --all-extras

test: install
	@uv run pytest --cov=./ --cov-report=term-missing

lint: install
	@uv run pylint ecs_dns_updater

run: install
	@CLOUDFLARE_TOKEN=dummy CLOUDFLARE_ZONE_ID=dummy DNS_RECORD_NAME=example.com \
	  ECS_CLUSTER=dummy ECS_SERVICE=dummy uv run python -m ecs_dns_updater.main
