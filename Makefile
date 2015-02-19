default: content

all: content

content:
	python set_content.py -t traversalfs.tar.bz2 -t mac_task -f favicon.png -d db.data

test:
	flake8 .

.PHONY: default all content test
