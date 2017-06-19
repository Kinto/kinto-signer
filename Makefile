VIRTUALENV = virtualenv --python python3
VENV := $(shell echo $${VIRTUAL_ENV-$$PWD/.venv})
PYTHON = $(VENV)/bin/python
DEV_STAMP = $(VENV)/.dev_env_installed.stamp
INSTALL_STAMP = $(VENV)/.install.stamp
TEMPDIR := $(shell mktemp -d)

.IGNORE: clean
.PHONY: all install virtualenv tests install-dev tests-once

OBJECTS = .venv .coverage

all: install
install: $(INSTALL_STAMP)
$(INSTALL_STAMP): $(PYTHON) setup.py
	$(VENV)/bin/pip install -e .
	touch $(INSTALL_STAMP)

install-dev: $(INSTALL_STAMP) $(DEV_STAMP)
$(DEV_STAMP): $(PYTHON) dev-requirements.txt
	$(VENV)/bin/pip install -r dev-requirements.txt
	touch $(DEV_STAMP)

virtualenv: $(PYTHON)
$(PYTHON):
	$(VIRTUALENV) $(VENV)
	$(VENV)/bin/pip install -U pip

build-requirements:
	$(VIRTUALENV) $(TEMPDIR)
	$(TEMPDIR)/bin/pip install -U pip
	$(TEMPDIR)/bin/pip install -Ue .
	$(TEMPDIR)/bin/pip freeze | grep -v -- '^-e' > requirements.txt

tests-once: install-dev
	$(VENV)/bin/py.test --cov-report term-missing --cov-fail-under 100 --cov kinto_signer

tests: install-dev
	$(VENV)/bin/tox

clean:
	find . -name '*.pyc' -delete
	find . -name '__pycache__' -type d | xargs rm -fr

distclean: clean
	rm -fr *.egg *.egg-info/

maintainer-clean: distclean
	rm -fr .venv/ .tox/ dist/ build/

run-kinto: install-dev
	$(VENV)/bin/python --version
	$(VENV)/bin/kinto migrate --ini tests/config/signer.ini
	$(VENV)/bin/kinto start --ini tests/config/signer.ini

install-autograph: $(VENV)/bin/autograph

$(VENV)/bin/autograph:
	export GOPATH=$(VENV); export PATH="$$GOPATH/bin;$$PATH"; go get -d -u github.com/mozilla-services/autograph; cd $(VENV)/src/github.com/mozilla-services/autograph/; git checkout 1.3.2; go get github.com/mozilla-services/autograph

run-autograph: install-autograph
	$(VENV)/bin/autograph -c tests/config/autograph.yaml

need-kinto-running:
	@curl http://localhost:8888/v1/ 2>/dev/null 1>&2 || (echo "Run 'make run-kinto' before starting tests." && exit 1)

functional: install-dev need-kinto-running
	$(VENV)/bin/py.test tests/functional.py
