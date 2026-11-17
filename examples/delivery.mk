# Consumer sets DELIVERY_TOOLING_VERSION and the reservation target before including this file.
DELIVERY_CACHE := $(CURDIR)/.tools/delivery-tooling/$(DELIVERY_TOOLING_VERSION)
RESERVATION_DURATION ?= 30m
RESERVATION_TOKEN_FILE ?= $(CURDIR)/.private/reservation-$(RESERVATION_ENVIRONMENT)-$(RESERVATION_PRODUCT).json
RESERVATION_OPTIONS = --table "$(RESERVATION_TABLE)" --region "$(RESERVATION_REGION)" --environment "$(RESERVATION_ENVIRONMENT)" --product "$(RESERVATION_PRODUCT)" $(if $(RESERVATION_PROFILE),--profile "$(RESERVATION_PROFILE)")
RESERVATION = uv run --script "$(DELIVERY_CACHE)/reservation.py"
RESERVATION_TOKEN = $(if $(DELIVERY_RESERVATION_CONTEXT),,$(if $(wildcard $(RESERVATION_TOKEN_FILE)),--token-file "$(RESERVATION_TOKEN_FILE)"))
RESERVATION_RUN = $(RESERVATION) run $(RESERVATION_OPTIONS) --duration "$(RESERVATION_DURATION)" $(if $(RESERVATION_WAIT),--wait "$(RESERVATION_WAIT)") $(RESERVATION_TOKEN) --

.PHONY: delivery-tools reservation-status reservation-acquire reservation-extend reservation-release reservation-check reservation-shell reservation-recover
delivery-tools: ## Cache and verify the pinned delivery-tooling release; no AWS access.
	uv run --script scripts/cache_delivery_tooling.py --version "$(DELIVERY_TOOLING_VERSION)"
reservation-status: delivery-tools ## Inspect the shared environment/product reservation.
	$(RESERVATION) status $(RESERVATION_OPTIONS)
reservation-acquire: delivery-tools ## Reserve the environment/product for manual work across commands.
	$(RESERVATION) acquire $(RESERVATION_OPTIONS) --duration "$(RESERVATION_DURATION)" $(if $(RESERVATION_WAIT),--wait "$(RESERVATION_WAIT)") --token-file "$(RESERVATION_TOKEN_FILE)"
reservation-extend: delivery-tools ## Explicitly extend the current manual reservation by the chosen duration.
	$(RESERVATION) extend $(RESERVATION_OPTIONS) --duration "$(RESERVATION_DURATION)" --token-file "$(RESERVATION_TOKEN_FILE)"
reservation-release: delivery-tools ## Release a healthy idle manual reservation and remove its local token file.
	$(RESERVATION) release $(RESERVATION_OPTIONS) --token-file "$(RESERVATION_TOKEN_FILE)"
reservation-check: delivery-tools ## Check inherited reservation ownership; used by guarded cloud runners.
	@test -n "$$DELIVERY_RESERVATION_CONTEXT" || { echo 'Use a reserved Make target; no inherited reservation.' >&2; exit 1; }
	$(RESERVATION) check $(RESERVATION_OPTIONS)
reservation-shell: delivery-tools ## Hold one supervised reservation across an interactive operator shell.
	$(RESERVATION_RUN) $(SHELL)
reservation-recover: delivery-tools ## Recover an exact observed revision after explicit operator reconciliation.
	$(RESERVATION) recover $(RESERVATION_OPTIONS) --revision "$(RESERVATION_REVISION)" --reason "$(RESERVATION_REASON)" $(if $(filter yes,$(RESERVATION_DRAINED)),--confirm-drained)
