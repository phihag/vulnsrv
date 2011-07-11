#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os,sys,mimetypes,contextlib,base64,re,bz2
import pickle

def lsRecursive(root):
	""" Yields entries in the form (real filename, virtual filename, children (None if an element)) """
	visit = [(root, '')]
	yield (root, '', True)
	while len(visit) > 0:
		r,v = visit.pop(0)
		for direntry in os.listdir(r):
			fn = os.path.join(r, direntry)
			vfn = v + '/' + direntry
			if os.path.isdir(fn):
				visit.append((fn, vfn))
				yield (fn, vfn, os.listdir(fn))
			else:
				yield (fn, vfn, None)

def readFilesFromFsTree(fsroot):
	res = {}
	for rfn,vfn,children in lsRecursive(fsroot):
		fdata = {}
		if children is not None:
			fdata['type'] = '__directory__' 
			fdata['content'] = list(sorted(children))
		else:
			fdata['type'] = mimetypes.guess_type(rfn)[0]
			with contextlib.closing(open(rfn, 'rb')) as f:
				content = f.read()
				fdata['blob_b64'] = base64.b64encode(content)
		res[vfn] = fdata
	return res

def main():
	if len(sys.argv) != 2:
		print('Usage: ' + sys.argv[0] + ' [filesystem-root]')
		sys.exit(101)
	fsroot = sys.argv[1]
	fstree = readFilesFromFsTree(fsroot)
	s = pickle.dumps(fstree)
	s64 = base64.b64encode(bz2.compress(s))

	scriptfn = os.path.join(os.path.dirname(__file__), 'vulnsrv.py')
	with contextlib.closing(open(scriptfn, 'r+')) as scriptf:
		code = scriptf.read()
		p = re.compile('_FILES_RAW = "[^"]*"')
		code = p.sub('_FILES_RAW = "' + s64 + '"', code)

		scriptf.seek(0)
		scriptf.truncate(0)
		scriptf.write(code)
		scriptf.flush()

if __name__ == '__main__':
	main()
