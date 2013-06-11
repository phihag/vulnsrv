default: content

all: content

content:
	python set_content.py -t traversalfs.tar.bz2 -f favicon.png -d db.data

.PHONY: default all content
