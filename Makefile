.DEFAULT_GOAL := help
RENOVATE_IMAGE := ghcr.io/renovatebot/renovate:44.257.9
ACTIONLINT_VERSION := 1.7.12

.PHONY: help setup check config-check workflows-check test runner-test release-test release-plan
help: ## List supported actions.
	@awk 'BEGIN { FS = ":.*##" } /^[[:alnum:]_.-]+:.*##/ { printf "  %-16s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

setup: ## Install locked release libraries without lifecycle scripts.
	npm ci --ignore-scripts

check: config-check workflows-check test ## Validate configuration, workflows and runner behavior.

config-check: ## Validate the public preset and repository Renovate configuration.
	docker run --rm -v "$(CURDIR):/work:ro" --entrypoint renovate-config-validator $(RENOVATE_IMAGE) --strict --no-global /work/default.json /work/renovate.json

workflows-check: ## Check workflow syntax with the pinned actionlint release.
	go run github.com/rhysd/actionlint/cmd/actionlint@v$(ACTIONLINT_VERSION) -shellcheck= .github/workflows/*.yml

test: runner-test release-test reservation-test ## Test dependency, release and reservation behavior without credentials.

runner-test: ## Test runner targeting, preview behavior and credential validation without network access.
	uv run --script tests/test_runner.py

release-test: ## Test version planning, artifact verification and publication recovery offline.
	node --test tests/*.test.mjs

release-plan: ## Preview this repository's source release without publishing.
	node release/cli.mjs plan --repository accelerate-toolkit/delivery-tooling

.PHONY: reservation-test reservation-package reservation-integration-test reservation-module-test
reservation-test: ## Test reservation contention, expiry, process supervision and verified caching offline.
	uv run --script tests/test_reservation.py
	uv run --script tests/test_tooling_cache.py
reservation-integration-test: ## Check real DynamoDB conditional writes and CLI nesting in an ephemeral container.
	uv run --script tests/test_reservation_dynamodb.py
reservation-package: ## Package the standalone script and Terraform module deterministically.
	python3 reservation/package.py
reservation-module-test: ## Validate and mock-plan the extracted backend archive without AWS credentials.
	uv run --script tests/test_reservation_module.py
