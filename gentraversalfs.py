#!/usr/bin/env python
# -*- coding: utf-8 -*-

import json,os,sys,mimetypes,contextlib,base64,re,bz2,tarfile

def listFilesystem(root):
	""" Yields entries in the form (virtual filename, children (None if an element), file handle (None if a directory)) """
	if not os.path.isdir(root):
		raise ValueError('Root is not a directory')
	visit = [(root, '')]
	while len(visit) > 0:
		r,v = visit.pop(0)
		children = os.listdir(r)
		yield (v, children, None)
		for direntry in children:
			rfn = os.path.join(r, direntry)
			vfn = v + '/' + direntry
			if os.path.isdir(rfn):
				visit.append((rfn, vfn))
			else:
				yield (vfn, None, open(rfn, 'rb'))

def listTar(tarfilename):
	tf = tarfile.open(tarfilename)
	members = tf.getmembers()
	rootChildren = []
	for entry in members:
		ename = '/' + entry.name.strip('/')
		if '/' not in ename:
			rootChildren.append(ename)
		if entry.isdir():
			children = [m.name.split('/')[-1] for m in members
				if m.name.startswith(ename[1:] + '/') and '/' not in m.name[len(ename[1:] + '/')]]
			yield (ename, children, None)
		else:
			f = tf.extractfile(entry)
			yield (ename, None, f)
	yield('', rootChildren, None)

def parseFiles(iterFiles):
	res = {}
	for vfn,children,fileh in iterFiles:
		assert (children is None) != (fileh is None)
		fdata = {}
		if fileh is None:
			fdata['type'] = '__directory__'
			fdata['content'] = list(sorted(children))
		else:
			fdata['type'] = mimetypes.guess_type(vfn)[0]
			with contextlib.closing(fileh) as f:
				content = f.read()
				fdata['blob_b64'] = base64.b64encode(content).decode('ascii')
		res[vfn] = fdata
	return res

def genFilesRaw(source):
	try:
		iterFiles = listFilesystem(source)
		fs = parseFiles(iterFiles)
	except ValueError:
		iterFiles = listTar(source)
		fs = parseFiles(iterFiles)
	if not '/var/www/img' in fs:
		raise ValueError('Filesystem is missing image directory')
	if len(fs['/var/www/img']['content']) == 0:
		raise ValueError('Image directory empty')
	if not '' in fs:
		raise ValueError('Filesystem is missing root directory')
	raw = json.dumps(fs).encode('utf-8')
	raw = bz2.compress(raw)
	return base64.b64encode(raw).decode('ascii')

def main():
	if len(sys.argv) != 2:
		print('Usage: ' + sys.argv[0] + ' [root]')
		print('root can be a directory or a tarfile.')
		sys.exit(101)
	filesRaw = genFilesRaw(sys.argv[1])

	scriptfn = os.path.join(os.path.dirname(__file__), 'vulnsrv.py')
	with contextlib.closing(open(scriptfn, 'r+')) as scriptf:
		code = scriptf.read()
		p = re.compile('_FILES_RAW = "[^"]*"')
		code = p.sub('_FILES_RAW = "' + filesRaw + '"', code)

		scriptf.seek(0)
		scriptf.truncate(0)
		scriptf.write(code)
		scriptf.flush()

if __name__ == '__main__':
	main()
