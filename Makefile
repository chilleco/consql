PYTHON := env/bin/python

setup:
	python3 -m venv env
	$(PYTHON) -m pip install -U --force-reinstall pip
	$(PYTHON) -m pip install -r requirements.txt

setup-tests:
	make setup
	$(PYTHON) -m pip install -r tests/requirements.txt

setup-release:
	python3 -m venv env
	$(PYTHON) -m pip install -r requirements.dev.txt

run:
	docker pull postgres
	docker run --name mypsql -e POSTGRES_PASSWORD=password -d -p 5432:5432 postgres

stop:
	docker stop mypsql
	docker rm mypsql

check:
	docker ps -a | grep mypsql

connect:
	docker exec -it mypsql bash

migrate:
	cd migrations \
	&& python3 -m venv env \
	&& env/bin/pip install -U --force-reinstall pip \
	&& env/bin/pip install -r ../requirements.txt \
	&& env/bin/python main.py

test-linter-all:
	find . -type f -name '*.py' \
	| grep -vE 'env/' \
	| grep -vE 'tests/' \
	| grep -vE 'build/' \
	| xargs $(PYTHON) -m pylint -f text \
		--rcfile=tests/.pylintrc \
		--msg-template='{path}:{line}:{column}: [{symbol}] {msg}'

test-linter:
	git status -s \
	| grep -vE 'tests/' \
	| grep '\.py$$' \
	| awk '{print $$1,$$2}' \
	| grep -i '^[ma]' \
	| awk '{print $$2}' \
	| xargs $(PYTHON) -m pylint -f text \
		--rcfile=tests/.pylintrc \
		--msg-template='{path}:{line}:{column}: [{symbol}] {msg}'

test-unit-all:
	$(PYTHON) -m pytest -s tests/

test-unit:
	git status -s \
	| grep 'tests/.*\.py$$' \
	| awk '{print $$1,$$2}' \
	| grep -i '^[ma]' \
	| awk '{print $$2}' \
	| xargs $(PYTHON) -m pytest -s

test:
	make test-linter-all
	make test-unit-all

release:
	$(PYTHON) setup.py sdist bdist_wheel
	sudo $(PYTHON) -m twine upload dist/*

clean:
	rm -rf .pytest_cache/
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/

clear:
	rm -rf env/
	rm -rf **/env/
	rm -rf __pycache__/
	rm -rf **/__pycache__/
	rm -rf .pytest_cache/
	rm -rf **/.pytest_cache/
