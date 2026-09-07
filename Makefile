.PHONY: install gen plan explain whatif ml ablate ui serve bench test clean

install:
	pip install -r requirements.txt

gen:            ## build the synthetic division + ML training log
	python -m sanchay gen

plan:           ## run every method, compare, write out/compare.html
	python -m sanchay plan --time-limit 15

explain:        ## why this block, and why not another window
	python -m sanchay explain

whatif:         ## perturb an assumption and re-optimise
	python -m sanchay whatif

bench:          ## the full 30-scenario benchmark (~2 min)
	python -m sanchay bench --scenarios 10 --time-limit 15 --jobs 4

ml:             ## train both models and test whether they help
	python -m sanchay ml --risk --experiment

ablate:         ## ablations and the Pareto frontier
	python -m sanchay ablate --seeds 3 --time-limit 12

ui:             ## build the web frontend
	cd ui && npm install && npm run build

serve: ui       ## run the API and the web UI on :8000
	python -m sanchay serve

test:
	python -m pytest tests/ -q

clean:
	rm -rf out __pycache__ .pytest_cache
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
