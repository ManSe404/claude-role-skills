# Everyday commands of the Acme Foods platform. JOB is a job name from jobs/, DATE a delivery date (YYYY-MM-DD).
JOB ?=
DATE ?=
LAYER ?= silver

.PHONY: run status backfill-day checks dq samples

run:  ## run a job now: make run JOB=load_erp_orders
	python3 -m pipeline.runner run $(JOB)

status:  ## the last runs of a job, task by task: make status JOB=load_erp_orders
	python3 -m pipeline.runner status $(JOB)

backfill-day:  ## run a job again for one past delivery: make backfill-day JOB=load_erp_orders DATE=2026-10-01
	python3 -m pipeline.runner run $(JOB) --date $(DATE)

checks:  ## run the checks of one layer: make checks LAYER=silver
	python3 -m pipeline.runner checks --layer $(LAYER)

dq: checks  ## alias of checks

samples:  ## CSV copies of the served tables into samples/
	python3 -m pipeline.tools.export_samples --days 29
