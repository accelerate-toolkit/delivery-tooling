.DEFAULT_GOAL := help
RENOVATE_IMAGE := ghcr.io/renovatebot/renovate:44.244.3
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

test: runner-test release-test ## Test dependency-runner and release behavior without publication credentials.

runner-test: ## Test runner targeting, preview behavior and credential validation without network access.
	uv run --script tests/test_runner.py

release-test: ## Test version planning, artifact verification and publication recovery offline.
	node --test tests/*.test.mjs

release-plan: ## Preview this repository's source release without publishing.
	node release/cli.mjs plan --repository accelerate-toolkit/delivery-tooling
