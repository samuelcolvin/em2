.DEFAULT_GOAL:=all

.PHONY: install
install:
	pip install -U pip setuptools
	pip install -r tests/requirements.txt
	pip install -r em2/requirements1.txt
	pip install -r em2/requirements2.txt


.PHONY: format
format:
	isort -rc -w 120 em2 tests
	black -S -l 120 --py36 em2 tests

.PHONY: lint
lint:
	flake8 em2/ tests/
	PYTHONPATH=em2 pytest -p no:sugar -q --cache-clear --isort -W ignore em2
	black -S -l 120 --py36 --check em2 tests
	./tests/check_debug.sh
	cd js && yarn lint && cd ..

.PHONY: test
test:
	PYTHONPATH=em2 pytest --cov=em2

.PHONY: testcov
testcov: test
	coverage html

.PHONY: all
all: testcov lint
