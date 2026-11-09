test:
	PYTHONPATH=src pipenv run pytest tests

lambda:
	cd src; pipenv run chalice package ../out; cd -
