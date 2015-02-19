#!/usr/bin/env python
# -*- coding: utf-8 -*-

import base64
import bz2
import contextlib
import itertools
import json
import mimetypes
import optparse
import os
import re
import tarfile


def list_files(fn):
    if os.path.isdir(fn):
        return listFilesystem(fn)
    else:
        return listTar(fn)


def listFilesystem(root):
    """ Yields entries in the form (virtual filename, children (None if an element), file handle (None if a directory)) """
    visit = [(root, '')]
    while len(visit) > 0:
        r, v = visit.pop(0)
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
            children = [
                m.name.split('/')[-1] for m in members
                if (m.name.startswith(ename[1:] + '/') and
                    '/' not in m.name[len(ename[1:] + '/')])]
            yield (ename, children, None)
        else:
            f = tf.extractfile(entry)
            yield (ename, None, f)
    yield('', rootChildren, None)


def parseFiles(iterFiles):
    res = {}
    for vfn, children, fileh in iterFiles:
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


def genFilesRaw(iterFiles):
    fs = parseFiles(iterFiles)
    if '/var/www/img' not in fs:
        raise ValueError('Filesystem is missing image directory')
    if len(fs['/var/www/img']['content']) == 0:
        raise ValueError('Image directory empty')
    if '' not in fs:
        raise ValueError('Filesystem is missing root directory')
    raw = json.dumps(fs).encode('utf-8')
    raw = bz2.compress(raw)
    return raw


def genFaviconRaw(source):
    with contextlib.closing(open(source, 'rb')) as f:
        return f.read()


def genDbDataRawFromFile(source):
    with contextlib.closing(open(source, 'rb')) as f:
        raw = base64.b16decode(bz2.decompress(f.read()))
        raw = bz2.compress(raw)
        return raw


def replace_constant(code, constant, rawVal):
    strVal = base64.b64encode(rawVal).decode('ascii')
    p = re.compile('(' + re.escape(constant) + ') = "[^"]*"')
    code = p.sub(lambda m: m.group(1) + ' = "' + strVal + '"', code)
    return code


def main():
    op = optparse.OptionParser()
    op.add_option('-t', '--traversal-root', dest='traversalroots',
                  action='append',
                  help='Directory or tar file containing the filesystem presented in the path traversal task (can be specified multiple times)'),
    op.add_option('-f', '--favicon', dest='favicon',
                  help='The favicon file (browser tab/window icon)')
    op.add_option('-d', '--dbdata-file', dest='dbdata_file',
                  help='Write the initial database data content from the specified, compressed base16-encoded file')
    options, args = op.parse_args()

    if len(args) != 0:
        op.error('incorrect number of arguments, use -t and/or -f')
    if options.traversalroots is None and options.favicon is None and options.dbdata_file is None:
        op.error('Please supply at least one of -t, -f, or -d')

    scriptfn = os.path.join(os.path.dirname(__file__), 'vulnsrv.py')
    with contextlib.closing(open(scriptfn, 'r+')) as scriptf:
        code = scriptf.read()
        if options.traversalroots is not None:
            fileList = itertools.chain(* map(list_files, options.traversalroots))
            filesRaw = genFilesRaw(fileList)
            code = replace_constant(code, '_FILES_RAW', filesRaw)
        if options.favicon is not None:
            faviconRaw = genFaviconRaw(options.favicon)
            code = replace_constant(code, '_FAVICON_RAW', faviconRaw)
        if options.dbdata_file is not None:
            dbDataRaw = genDbDataRawFromFile(options.dbdata_file)
            code = replace_constant(code, '_DBDATA_RAW', dbDataRaw)

        scriptf.seek(0)
        scriptf.truncate(0)
        scriptf.write(code)
        scriptf.flush()

if __name__ == '__main__':
    main()
