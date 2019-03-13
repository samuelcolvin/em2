.DEFAULT_GOAL:=all
isort = isort -rc -w 120 em2 tests
black = black -S -l 120 --py36 em2 tests
heroku ?= em2-demo

.PHONY: install
install:
	pip install -U pip setuptools
	pip install -r tests/requirements.txt
	pip install -r em2/requirements1.txt
	pip install -r em2/requirements2.txt

.PHONY: format
format:
	$(isort)
	$(black)
	./tests/clean_python.py

.PHONY: lint
lint:
	flake8 em2/ tests/
	$(isort) --check-only
	$(black) --check
	./tests/check_debug.sh
	cd js && yarn --offline lint && cd ..

.PHONY: test
test:
	pytest --cov=em2

.PHONY: testcov
testcov: test
	coverage html

.PHONY: all
all: testcov lint


.PHONY: robot
robot:
	PYTHONPATH="`pwd`" ./tests/robot.py

.PHONY: clean
clean:
	rm -rf `find . -name __pycache__`
	rm -f `find . -type f -name '*.py[co]' `
	rm -f `find . -type f -name '*~' `
	rm -f `find . -type f -name '.*~' `
	rm -rf .cache
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf htmlcov
	rm -rf *.egg-info
	rm -f .coverage
	rm -f .coverage.*
	rm -rf build
	rm -r em2/.index

.PHONY: build
build: C=$(shell git rev-parse HEAD)
build: BT="$(shell date)"
build:
	@find em2 -name '*.py[co]' -delete
	@find em2 -name '__pycache__' -delete
	docker build em2 -f docker/Dockerfile -t em2 --build-arg COMMIT=$(C) --build-arg BUILD_TIME=$(BT)

.PHONY: docker-dev
docker-dev: build
	# ================================================================================
	# running locally for development and testing
	# You'll want to run docker-logs in anther window see what's going on
	# ================================================================================
	#
	# running docker compose...
	docker-compose -f docker/docker-compose.yml up -d

.PHONY: docker-dev-stop
docker-dev-stop:
	docker-compose -f docker/docker-compose.yml stop

.PHONY: push
push: build
	@if [ "`git status --porcelain | wc -l`" -ne "0" ]; then \
	    echo "REPO NOT CLEAN"; \
	    # exit 1; \
	fi
	docker tag em2 registry.heroku.com/$(heroku)/web
	docker push registry.heroku.com/$(heroku)/web
	docker tag em2 registry.heroku.com/$(heroku)/worker
	docker push registry.heroku.com/$(heroku)/worker

.PHONY: release
release: push
	heroku container:release web worker -a $(heroku)
