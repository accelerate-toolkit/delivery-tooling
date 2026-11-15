.DEFAULT_GOAL := help
RENOVATE_IMAGE := ghcr.io/renovatebot/renovate:44.151.0

.PHONY: help check
help: ## List supported actions.
	@awk 'BEGIN { FS = ":.*##" } /^[[:alnum:]_.-]+:.*##/ { printf "  %-16s %s\n", $$1, $$2 }' $(MAKEFILE_LIST)

check: ## Validate the public preset and repository Renovate configuration.
	docker run --rm -v "$(CURDIR):/work:ro" --entrypoint renovate-config-validator $(RENOVATE_IMAGE) --strict --no-global /work/default.json /work/renovate.json
