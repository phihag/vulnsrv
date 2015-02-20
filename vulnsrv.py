#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import base64
import binascii
import bz2
import hashlib
import os
import os.path
import re
import struct
import sqlite3
import threading
import time
import urllib
import sys

try:
    import json
except ImportError:
    # Python <2.6, use trivialjson (https://github.com/phihag/trivialjson):
    unichr = __builtins__.unichr  # Trick modern flake8

    class json(object):
        @staticmethod
        def loads(s):
            s = s.decode('UTF-8')

            def raise_error(msg, i):
                raise ValueError(msg + ' at position ' + str(i) + ' of ' + repr(s) + ': ' + repr(s[i:]))

            def skip_space(i, expect_more=True):
                while i < len(s) and s[i] in ' \t\r\n':
                    i += 1
                if expect_more:
                    if i >= len(s):
                        raise_error('Premature end', i)
                return i

            def decodeEscape(match):
                esc = match.group(1)
                _STATIC = {
                    '"': '"',
                    '\\': '\\',
                    '/': '/',
                    'b': unichr(0x8),
                    'f': unichr(0xc),
                    'n': '\n',
                    'r': '\r',
                    't': '\t',
                }
                if esc in _STATIC:
                    return _STATIC[esc]
                if esc[0] == 'u':
                    if len(esc) == len('u') + 4:
                        return unichr(int(esc[1:5], 16))
                    if len(esc) == 5 + 6 and esc[5:7] == '\\u':
                        hi = int(esc[1:5], 16)
                        low = int(esc[7:11], 16)
                        return unichr((hi - 0xd800) * 0x400 + low - 0xdc00 + 0x10000)
                raise ValueError('Unknown escape ' + str(esc))

            def parse_string(i):
                i += 1
                e = i
                while True:
                    e = s.index('"', e)
                    bslashes = 0
                    while s[e - bslashes - 1] == '\\':
                        bslashes += 1
                    if bslashes % 2 == 1:
                        e += 1
                        continue
                    break
                rexp = re.compile(r'\\(u[dD][89aAbB][0-9a-fA-F]{2}\\u[0-9a-fA-F]{4}|u[0-9a-fA-F]{4}|.|$)')
                stri = rexp.sub(decodeEscape, s[i:e])
                return (e + 1, stri)

            def parseObj(i):
                i += 1
                res = {}
                i = skip_space(i)
                if s[i] == '}':  # Empty dictionary
                    return (i + 1, res)
                while True:
                    if s[i] != '"':
                        raise_error('Expected a string object key', i)
                    i, key = parse_string(i)
                    i = skip_space(i)
                    if i >= len(s) or s[i] != ':':
                        raise_error('Expected a colon', i)
                    i, val = parse(i + 1)
                    res[key] = val
                    i = skip_space(i)
                    if s[i] == '}':
                        return (i + 1, res)
                    if s[i] != ',':
                        raise_error('Expected comma or closing curly brace', i)
                    i = skip_space(i + 1)

            def parse_array(i):
                res = []
                i = skip_space(i + 1)
                if s[i] == ']':  # Empty array
                    return (i + 1, res)
                while True:
                    i, val = parse(i)
                    res.append(val)
                    i = skip_space(i)  # Raise exception if premature end
                    if s[i] == ']':
                        return (i + 1, res)
                    if s[i] != ',':
                        raise_error('Expected a comma or closing bracket', i)
                    i = skip_space(i + 1)

            def parse_discrete(i):
                for k, v in {'true': True, 'false': False, 'null': None}.items():
                    if s.startswith(k, i):
                        return (i + len(k), v)
                raise_error('Not a boolean (or null)', i)

            def parse_number(i):
                mobj = re.match('^(-?(0|[1-9][0-9]*)(\.[0-9]*)?([eE][+-]?[0-9]+)?)', s[i:])
                if mobj is None:
                    raise_error('Not a number', i)
                nums = mobj.group(1)
                if '.' in nums or 'e' in nums or 'E' in nums:
                    return (i + len(nums), float(nums))
                return (i + len(nums), int(nums))
            CHARMAP = {'{': parseObj, '[': parse_array, '"': parse_string, 't': parse_discrete, 'f': parse_discrete, 'n': parse_discrete}

            def parse(i):
                i = skip_space(i)
                i, res = CHARMAP.get(s[i], parse_number)(i)
                i = skip_space(i, False)
                return (i, res)
            i, res = parse(0)
            if i < len(s):
                raise ValueError('Extra data at end of input (index ' + str(i) + ' of ' + repr(s) + ': ' + repr(s[i:]) + ')')
            return res

try:
    _uc = unicode  # Python 2
except NameError:
    _uc = str  # Python 3


def _b(s):
    return s.encode('ascii')

try:
    compat_bytes = bytes
except NameError:  # Python < 2.6
    compat_bytes = str

try:
    import Cookie as _cookies
except ImportError:
    import http.cookies as _cookies

try:
    import Queue
    _queue = Queue.Queue
except ImportError:  # Python 3
    import queue
    _queue = queue.Queue

try:
    from SocketServer import ThreadingMixIn
except ImportError:
    from socketserver import ThreadingMixIn

try:
    from BaseHTTPServer import HTTPServer, BaseHTTPRequestHandler
except ImportError:
    from http.server import HTTPServer, BaseHTTPRequestHandler

try:
    import urlparse
    _urlparse = urlparse.urlparse
except ImportError:  # Python 3
    import urllib.parse
    _urlparse = urllib.parse.urlparse

try:
    from urllib.parse import urlencode
except ImportError:  # Python <3
    from urllib import urlencode

try:
    import html
    html.escape
except (ImportError, AttributeError):  # Python < 3.2
    _escape_map = {
        ord('&'): _uc('&amp;'),
        ord('<'): _uc('&lt;'),
        ord('>'): _uc('&gt;'),
    }
    _escape_map_full = {
        ord('&'): _uc('&amp;'),
        ord('<'): _uc('&lt;'),
        ord('>'): _uc('&gt;'),
        ord('"'): _uc('&quot;'),
        ord('\''): _uc('&#x27;'),
    }

    class html(object):
        @staticmethod
        def escape(s, quote=True):
            """
            Replace special characters "&", "<" and ">" to HTML-safe sequences.
            If the optional flag quote is true (the default), the quotation mark
            character (") is also translated.
            """
            s = _uc(s)
            if quote:
                return s.translate(_escape_map_full)
            return s.translate(_escape_map)


def query2dict(query):
    """ Raises a ValueError if the input is not valid application/x-www-form-urlencoded bytes """
    def _percentDecode(bin):
        bin = bin.replace(_b('+'), _b('%20'))
        pstrs = bin.split(_b('%'))
        resbin = pstrs[0]
        for pstr in pstrs[1:]:
            intv = int(pstr[:2], 16)
            pbyte = struct.pack('!B', intv)
            resbin += pbyte + pstr[2:]
        res = resbin.decode('UTF-8', 'ignore')
        return res

    res = {}
    for qel in query.split(_b('&')):
        if len(qel) == 0:
            continue
        kbin, eq, vbin = qel.partition(_b('='))
        k = _percentDecode(kbin)
        v = _percentDecode(vbin)
        res[k] = v
    return res

_FILES_RAW = "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"

_DBDATA_RAW = "QlpoOTFBWSZTWbHfiOgAAMGfgFCEABAq73xqP//+qjAA+WMNUxNAAAGgAaAANKYDQoyejSAAGgM1AlNKaRpoANAA0HqaHqGkGGgwJqs3mYlZcjGvRZKmFNA2DeSnk/ejxOkJxDs52efOMfkIZMJkBHGldvX6YaWimKrRnZgrIvbYUYXHsJBniC6LaEyXOkMpVCwMQpxALwYIEqm1KEDcN+JxCn1YYfWMQaDDXQyKBIoMqMxZfHQsF3CxnsUCrErVrzNCZwm2cn3JUiJVHExUCTMLSSO0TTS9Pr8RueRHnCUWKFoi2twKQJgrfRok6cEtJt19zLGAA0Et1rgkQAm9fxdyRThQkLHfiOg="

_FAVICON_RAW = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAABuwAAAbsBOuzj4gAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAInSURBVDiNlZTfS5NhFMc/5303R9t0SIqKRKgRCRmZZLwWqfSDCqKkIfgPBIEFIiLYH9BdQRfdVqAXmXQdRRdd5HzfJaybQkLMXZTgViGbc27vThfuHWYqdOBcPN9zzvf7nOfHQVUZPUFIVfkfHz/JDVXFABC4zR42LxLcDQ/5uANg3O+S1kgVlyoREcMRGY6LvHFEUi5kHZFFR2Q6LtIL8KBbzIDJuXsdYvlcl85wgLNPeqTtVAzXgOfAef1bsBVoVbhlizxqsFj8lieUdznkKxnMrhcJ1gZ5na6luv4XDXu1AxgCo81LFJ1aSj4hIarKWKe8OljFQKYAx5bh6M99KMr2vpG3Yz/0sgFwM8FweAXMLDRnPC2Dtqkp6mIxQgMDADSOjHBkYYHAxAS9K9QBoKo4cN0G3e5f+vs1lUqp3+/Xa3196vj96mazalmWRiIRjTc1Fb5CwAdQgtOyY4vriQTVQDQa5YxpooUCmbk5otEon22b0syMLw3HRVVxRB4Dd3f2adbUcKC9nYxtb92waRK2LDLxOJrPA1wwyrm53Q7KXVsjY9vkW1qYBeZFyCWTXjECG/sSeNYyNEQP0AXUDw5WcIGc95Q39iNITU4CoMUi6enpfwkUkjtqlgW+e4vNZBIFByhtJiupBRdWDQATXgJL5cDvElx14SKwWsbe5aBXYXyb+tNu1XTle36AwzY8c+CKh81Chw0vPkLQw2x4aMPEJ7ZGwB/9YAdxOTyWpQAAAABJRU5ErkJggg=="

FILES = json.loads(bz2.decompress(base64.b64decode(_FILES_RAW.encode('ascii'))).decode('UTF-8'))
DBDATA = json.loads(bz2.decompress(base64.b64decode(_DBDATA_RAW.encode('ascii'))).decode('UTF-8'))
FAVICON = base64.b64decode(_FAVICON_RAW.encode('ascii'))


class SQLliteManager(threading.Thread):
    """ Makes the thread-unsafe sqlite work with threads """
    def __init__(self):
        super(SQLliteManager, self).__init__()
        self.daemon = True
        self._commandq = _queue()
        self._resultq = _queue()
        self._clientLock = threading.Lock()

    def run(self):
        while True:
            conn = sqlite3.connect(":memory:")
            conn.isolation_level = None  # auto-commit
            cursor = conn.cursor()
            while True:
                sql = self._commandq.get()
                if sql == '_reset_':
                    self._resultq.put(None)
                    break
                try:
                    cursor.execute(sql)
                    res = cursor.fetchall()
                except:
                    _type, e, _traceback = sys.exc_info()
                    res = e
                self._resultq.put(res)
            cursor.close()
            conn.close()

    def query(self, sql):
        """ Called from another thread, blocks until the result is ready """
        self._clientLock.acquire()
        self._commandq.put(sql)
        res = self._resultq.get()
        self._clientLock.release()
        if isinstance(res, BaseException):
            raise res
        return res


def _VulnState_locked(f):
    def lockf(self, *args, **kwargs):
        self._lock.acquire()
        try:
            return f(self, *args, **kwargs)
        finally:
            self._lock.release()
    return lockf


class VulnState(object):
    def __init__(self):
        self._lock = threading.Lock()
        self._sqlThread = SQLliteManager()
        self._sqlThread.start()
        self.reset()

    @_VulnState_locked
    def csrfMessage(self, msg):
        self._csrfMessages.append(msg)

    @property
    @_VulnState_locked
    def csrfMessages(self):
        res = self._csrfMessages[:]
        return res

    @_VulnState_locked
    def xssMessage(self, msg):
        self._xssMessages.append(msg)

    @property
    @_VulnState_locked
    def xssMessages(self):
        return self._xssMessages[:]

    @_VulnState_locked
    def sqlQuery(self, sql):
        return self._sqlThread.query(sql)

    @property
    @_VulnState_locked
    def macSecret(self):
        return self._macSecret

    @_VulnState_locked
    def reset(self):
        self._csrfMessages = []
        self._xssMessages = []
        self._macSecret = hashlib.md5(os.urandom(32)).hexdigest().encode('ascii')
        assert len(self._macSecret) == 32

        # TODO replace this with a Python in-memory database, which takes DBDATA in its constructor (and only needs to be initialized once)
        self._sqlThread.query('_reset_')
        for tableName, td in DBDATA.items():
            csql = (
                'CREATE TABLE ' + tableName + ' (' +
                ','.join(col['name'] + ' ' + col['type'] for col in td['structure']) +
                ')')
            self._sqlThread.query(csql)
            for d in td['data']:
                dsql = (
                    'INSERT INTO ' + tableName +
                    ' (' + ','.join(k for k, v in d.items()) + ')' +
                    ' VALUES(' + ','.join("'" + v.replace("'", "''") + "'" for k, v in d.items()) +
                    ')')
                self._sqlThread.query(dsql)


def msgsToHtml(msgs):
    res = (_uc('''
<h2>Nachrichten</h2>

<ul class="messages">'''))

    for msg in reversed(msgs):
        res += _uc('<li>')
        res += html.escape(msg)
        res += _uc('</li>\n')

    res += _uc('</ul>')
    return res


class VulnHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        reqp = _urlparse(self.path)
        try:
            #  getParams = query2dict(reqp.query.encode('ascii'))
            postParams = self._readPostParams()
        except ValueError:
            _type, e, _traceback = sys.exc_info()
            self.send_error(400, str(e))
            return
        sessionID = self._getSessionID(False)

        if reqp.path == '/clientauth/secret':
            if self._csrfCheck(postParams):  # Technically, not a problem here - until we're starting to log who knows the secret
                self._writeHtmlDoc(
                    _uc('<code class="secret">%s</code>') %
                    html.escape(base64.b16decode('4356452F4D49545245'.encode('ascii')).decode('UTF-8')),
                    'Geheimnis', sessionID)
        elif reqp.path == '/csrf/send':
            # No CSRF check here, duh
            msg = postParams.get('message', '')
            if msg == '':
                self.send_error(400, 'Missing or empty message')
            else:
                self.vulnState.csrfMessage(msg)
                self._redirect('/csrf/')
        elif reqp.path == '/xss/send':
            if self._csrfCheck(postParams):
                msg = postParams.get('message', '')
                if msg == '':
                    self.send_error(400, 'Missing or empty message')
                else:
                    self.vulnState.xssMessage(msg)
                    self._redirect('/xss/?username=Sender%2C')
        elif reqp.path == '/mac/login':
            if self._csrfCheck(postParams):
                val = _uc('user=Gast&time=' + str(int(time.time())))
                mac = hashlib.sha256(self.vulnState.macSecret + val.encode('ascii')).hexdigest()
                cookieval = mac + '!' + val
                c = {'mac_session': cookieval}
                self._redirect('/mac/', c)
        elif reqp.path == '/reset':
            if self._csrfCheck(postParams):
                self.vulnState.reset()
                self._redirect('/')
        else:
            self.send_error(404, 'No POST handler defined')

    def do_GET(self):
        reqp = _urlparse(self.path)
        try:
            getParams = query2dict(reqp.query.encode('ascii'))
        except ValueError:
            _type, e, _traceback = sys.exc_info()
            self.send_error(400, 'Invalid query format: ' + str(e))
            return
        sessionID = self._getSessionID()

        if reqp.path == '/':
            self._writeHtmlDoc(_uc('''
<ol class="mainMenu">
<li><a href="clientauth/">Client-Side Authorization Check</a></li>
<li><a href="mac/">MAC Length Extension</a></li>
<li><a href="csrf/">Cross-Site Request Forgery (CSRF)</a></li>
<li><a href="xss/?username=Benutzer%21">Cross-Site Scripting (XSS)</a></li>
<li><a href="sqlinjection/">SQL Injection</a></li>
<li><a href="pathtraversal/">Path Traversal</a></li>
</ol>'''), 'vulnsrv', sessionID)
        elif reqp.path == '/clientauth/':
            js_code = html.escape('if (\'you\' != \'admin\') {alert(\'Zugriff verweigert!\'); return false;} else return true;', True)
            self._writeHtmlDoc(
                _uc('''
    <p>Finden Sie das Geheimnis heraus!</p>

    <form action="secret" method="post">
    <input type="submit" value="Geheimnis herausfinden"
    onclick="%s" />
    %s
    </form>
    ''') % (js_code, self._getCsrfTokenField(sessionID)),
                'Client-Side Authorization Check', sessionID)
        elif reqp.path == '/csrf/':
            self._writeHtmlDoc(
                _uc('''
<p>Mit dem untenstehendem Formular k&ouml;nnen Sie Nachrichten schreiben.
Erstellen Sie eine HTML-Datei <code>evil-csrf.html</code>, bei deren Aufruf der arglose Benutzer hier unfreiwillig eine &uuml;belgesinnte Nachricht hinterl&auml;sst.
</p>

<form action="send" enctype="application/x-www-form-urlencoded" method="post">
<input type="text" name="message" autofocus="autofocus" required="required" placeholder="Eine freundliche Nachricht" size="50" />
<input type="submit" value="Senden" />
</form>
''') + msgsToHtml(self.vulnState.csrfMessages), 'CSRF', sessionID)
        elif reqp.path == '/xss/':
            username = getParams.get('username', 'Unbekannter')
            self._writeHtmlDoc(_uc(
                '''<div>Hallo %s</div>
<p>Das untenstehende Formular ist gegen Cross-Site Request Forgery gesch&uuml;tzt.
Erstellen Sie eine HTML-Datei <code>evil-xss.html</code>, bei deren Aufruf der arglose Benutzer hier trotzdem unfreiwillig eine &uuml;belgesinnte Nachricht hinterl&auml;sst.
</p>

<form action="send" enctype="application/x-www-form-urlencoded" method="post">
<input type="text" name="message" autofocus="autofocus" required="required" placeholder="Eine freundliche Nachricht" size="50" />
%s
<input type="submit" value="Senden" />
</form>
''') % (_uc(username), self._getCsrfTokenField(sessionID)) + msgsToHtml(self.vulnState.xssMessages), 'XSS', sessionID)
        elif reqp.path == '/sqlinjection/':
            webMessages = self.vulnState.sqlQuery("SELECT id,msg FROM messages WHERE user='web'")
            self._writeHtmlDoc(_uc('''
<p>In der untenstehenden Tabelle sehen Sie die Nachrichten an den Benutzer <code>web</code>. Welche Nachrichten hat der Benutzer <code>admin</code> bekommen?</p>

<h2>Nachrichten an <code>web</code></h2>

<ul class="messages">
%s
</ul>''') % '\n'.join('<li><a href="/sqlinjection/msg?id=' + html.escape(str(row[0])) + '">' + html.escape(row[1]) + '</a></li>' for row in webMessages), 'SQL Injection', sessionID)
        elif reqp.path == '/sqlinjection/msg':
            msgNum = getParams.get('id', '')
            sql = "SELECT id,user,msg FROM messages WHERE user='web' AND id='" + msgNum + "'"
            try:
                msgs = self.vulnState.sqlQuery(sql)
                if len(msgs) == 0:
                    msg_html = '<td colspan="3">Keine web-Nachrichten gefunden</td>'
                else:
                    msg_html = '\n'.join('<tr>' + ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in row) + '</tr>' for row in msgs)
            except:
                _type, e, _traceback = sys.exc_info()
                msg_html = '<td colspan="3" class="error">' + html.escape(str(e)) + '</td>'
            self._writeHtmlDoc(('''
<table class="messages">
<thead><tr><th>ID</th><th>Benutzer</th><th>Nachricht</th></tr></thead>
%s
</table>
<p><a href="/sqlinjection/">Zur&uuml;ck zur &Uuml;bersicht</a></p>
''' % msg_html), 'Detailansicht: Nachricht ' + msgNum, sessionID)
        elif reqp.path == '/pathtraversal/':
            fileHtml = _uc('').join(
                _uc('<li><a href="get?') + html.escape(urlencode([('file', fn)])) + _uc('">') + html.escape(fn) + _uc('</a></li>\n')
                for fn in FILES['/var/www/img']['content'])
            self._writeHtmlDoc(_uc('''
<p>Welchen Unix-Account sollte ein Angreifer n&auml;her untersuchen?</p>

<p><em>Bonus-Aufgabe</em>: Was ist das Passwort des Accounts?</p>

<p>Dateien zum Download:</p>

<ul>
%s
</ul>''' % fileHtml), 'Path Traversal', sessionID)
        elif reqp.path == '/pathtraversal/get':
            fn = '/var/www/img/' + getParams.get('file', '')
            # Resolve the path.
            # If we were using a real filesystem, this would be done automatically by the OS filesystem functions, of course
            curPath = []
            for pel in fn.split('/'):
                if pel == '' or pel == '.':
                    continue
                if pel == '..':
                    if len(curPath) > 0:
                        curPath.pop()
                    # else: We're at the root, and /../ is /
                else:
                    curPath.append(pel)
            finalPath = '/' + '/'.join(curPath)
            if finalPath.endswith('/'):
                finalPath = finalPath[:-1]
            if finalPath in FILES:
                fdata = FILES[finalPath]
                if fdata['type'] == '__directory__':
                    self.send_error(404, 'Is a directory')
                else:
                    fileBlob = base64.b64decode(fdata['blob_b64'].encode('ascii'))
                    self.send_response(200)
                    self.send_header('Content-Type', fdata['type'])
                    self.send_header('Content-Length', str(len(fileBlob)))
                    self.end_headers()
                    self.wfile.write(fileBlob)
            else:
                self.send_error(404)
        elif reqp.path == '/mac/':
            cookies = self._readCookies()
            raw_cookie = cookies.get('mac_session')
            if raw_cookie is not None:
                if isinstance(raw_cookie, compat_bytes):  # Python 2.x
                    raw_cookie = raw_cookie.decode('latin1')
                mac, _, session_data_str = raw_cookie.rpartition(_uc('!'))
                session_data = session_data_str.encode('latin1')
                secret = self.vulnState.macSecret
                if hashlib.sha256(secret + session_data).hexdigest() == mac:
                    session = query2dict(session_data)
                    user = session['user']
                    timestamp = session['time']
                else:
                    user = timestamp = _uc('(Falscher MAC)')
            else:
                raw_cookie = _uc('')
                user = timestamp = _uc('(Nicht gesetzt)')

            assert isinstance(raw_cookie, _uc)
            raw_cookie_hex = binascii.b2a_hex(raw_cookie.encode('utf-8')).decode('ascii')
            assert isinstance(raw_cookie_hex, _uc)
            self._writeHtmlDoc(_uc('''
<p>Loggen Sie sich als Benutzer admin ein (ohne das Geheimnis aus dem Server-Prozess auszulesen).
Schreiben Sie daf&#x00fc;r ein Programm, das den korrekten Cookie-Wert berechnet.</p>

<form method="post" action="login">
%s
<input type="submit" value="Gast-Login" />
</form>

<h3>Aktuelle Session-Daten:</h3>

<p>Cookie (roh): <code>%s</code> (%s Bytes)</p>

<dl>
<dt>Benutzername:</dt><dd>%s</dd>
<dt>Login-Zeit:</dt><dd>%s</dd>
</dl>

<p>F&#x00fc;r den Angriff k&#x00f6;nnen Sie <a href="mac_attack.py">dieses Python-Skript</a> verwenden.
Das Skript erwartet, dass im lokalen Verzeichnis eine ausf&#x00fc;hrbare Datei ./mac_extension liegt, die mit den Argumenten <code>[Bekannter Hash]</code> <code>[Bekannte Eingabe]</code> <code>[Einzuf&#x00fc;gende Daten]</code> <code>[L&#x00e4;nge des secrets in Bytes (32)]</code> aufgerufen werden kann und das exploit zur&#x00fc;ckgibt.
</p>
      ''' % (
                self._getCsrfTokenField(sessionID),
                html.escape(raw_cookie),
                html.escape(_uc(len(raw_cookie))),
                html.escape(user),
                html.escape(timestamp)
            )), 'Length Extension-Angriffe gegen MAC', sessionID)
        elif reqp.path == '/mac/mac_attack.py':
            fdata = FILES['/mac/mac_attack.py']
            fileBlob = base64.b64decode(fdata['blob_b64'].encode('ascii'))
            self.send_response(200)
            self.send_header('Content-Type', fdata['type'])
            self.send_header('Content-Length', str(len(fileBlob)))
            self.end_headers()
            self.wfile.write(fileBlob)
        elif reqp.path == '/favicon.ico':
            self.send_response(200)
            self.send_header('Content-Type', 'image/png')
            self.send_header('Content-Length', str(len(FAVICON)))
            self.end_headers()
            self.wfile.write(FAVICON)
        else:
            self.send_error(404)

    def _writeHtmlDoc(self, htmlContent, title, sessionID, add_headers=None):
        if add_headers is None:
            add_headers = [
                ('X-Frame-Options', 'DENY'),
                ('X-XSS-Protection', '0'),
                ('Cache-Control', 'private, max-age=0, no-cache'),
                ('Pragma', 'no-cache'),
            ]

        title = _uc(title)
        mimeType = _uc('text/html; charset=utf-8')
        htmlCode = (_uc('''<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="%s" />
<title>%s</title>
<style type="text/css">
body {margin: 0; padding: 0 2em;}
.mainMenu {font-size: 160%%;}
h1 {text-align: center;}
.secret{font-size: 180%%; /*background: #000;*/}
.error {background: #ffd4d4;}
td[colspan] {text-align: center;}
nav {position: fixed; left: 0; bottom: 0; padding: 0.5em; background: #eef}
nav>a {display: inline-block; margin: 0 0.4em;}
nav>.sep{display: inline-block; width: 1em;}
nav>form {display: inline-block;}
.messages{padding-left: 0;}
.messages>li{list-style-type: none; padding: 0.3em 0.5em;}
.messages>li:nth-child(even){background: #f4f4f4;}
.messages>li:nth-child(odd){background: #ddd;}
</style>
</head>
<body>
<h1>%s</h1>
%s

<nav>
<a href="/clientauth/">Client-Side Authorization Check</a>
<a href="/mac/">MAC Length Extension</a>
<a href="/csrf/">Cross-Site Request Forgery (CSRF)</a>
<a href="/xss/?username=Benutzer%%21">Cross-Site Scripting (XSS)</a>
<a href="/sqlinjection/">SQL Injection</a>
<a href="/pathtraversal/">Path Traversal</a>
<span class="sep"></span>
<form class="reset" method="post" action="/reset">
%s
<input type="submit" value="clear data" />
</form>
</nav>
</body>
</html>
''' % (
            html.escape(mimeType),
            html.escape(title),
            html.escape(title),
            htmlContent,
            self._getCsrfTokenField(sessionID)
        )))
        htmlBytes = htmlCode.encode('utf-8')

        self.send_response(200)
        self._writeCookies()
        self.send_header('Content-Length', str(len(htmlBytes)))
        self.send_header('Content-Type', mimeType)
        for k, v in add_headers:
            self.send_header(k, v)
        self.end_headers()

        self.wfile.write(htmlBytes)

    def _redirect(self, target, cookieData=None):
        self.send_response(302)
        self.send_header('Location', target)
        self._writeCookies(cookieData)
        self.send_header('Content-Length', '0')
        self.end_headers()

    def _writeCookies(self, add=None):
        cookies = {
            'sessionID': self._getSessionID()
        }
        if add:
            cookies.update(add)
        c = _cookies.SimpleCookie()
        for k, v in cookies.items():
            assert re.match(r'^[a-zA-Z0-9_-]+$', k)
            c[k] = v
            c[k]['path'] = '/'
            if sys.version_info >= (2, 6):
                c[k]['httponly'] = True
        outp = c.output(sep=_uc('\r\n')) + _uc('\r\n')
        assert isinstance(outp, _uc)
        if hasattr(self, '_headers_buffer'):
            self._headers_buffer.append(outp.encode('latin1', 'strict'))
        else:
            self.wfile.write(outp.encode('latin1', 'strict'))

    def _readCookies(self):
        hdr = self.headers.get('cookie', '')
        c = _cookies.SimpleCookie(hdr)
        res = {}
        for morsel in c.values():
            res[morsel.key] = morsel.value
        return res

    def _readPostParams(self):
        contentLen = int(self.headers['content-length'])
        postBody = self.rfile.read(contentLen)

        contentType = self.headers['content-type']
        if not contentType.startswith('application/x-www-form-urlencoded'):
            raise ValueError('Invalid content type')
        res = query2dict(postBody)
        return res

    @property
    def vulnState(self):
        return self.server.vulnState

    def _getSessionID(self, autogenerate=True):
        cookies = self._readCookies()
        if 'sessionID' in cookies:
            return cookies['sessionID']
        elif autogenerate:
            return base64.b64encode(os.urandom(16)).decode('ascii')
        else:
            return None

    def _csrfCheck(self, postParams):
        if 'csrfToken' not in postParams:
            self.send_error(400, 'CSRF Token missing')
            return False
        elif postParams['csrfToken'] != self._getSessionID(False):
            self.send_error(400, 'CSRF Token not matching')
            return False
        else:
            return True

    def _getCsrfTokenField(self, sessionID):
        return _uc('<input type="hidden" name="csrfToken" value="') + html.escape(sessionID) + _uc('" />')

    error_message_format = _uc("""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<title>%(code)d %(codestr)s</title>
</head>
<body>
<h1>Error %(code)d: %(codestr)s</h1>
<p>%(explain)s</p>
<p>Message: %(message)s</p>
</body>
</html>
""")
    error_content_type = 'text/html; charset=utf-8'

    def send_error(self, code, message=_uc('')):
        codestr, explain = self.responses.get(code, (str(code), _uc('Unknown code')))
        self.log_error("code %d, message %s", code, message)
        content = (self.error_message_format %
                   {'code': code, 'message': html.escape(message),
                    'explain': explain, 'codestr': codestr})
        self.send_response(code, codestr)
        self.send_header('Content-Type', self.error_content_type)
        self.send_header('X-Frame-Options', 'deny')
        self.end_headers()
        if self.command != 'HEAD' and code >= 200 and code not in (204, 304):
            self.wfile.write(content.encode('utf-8'))


class VulnServer(ThreadingMixIn, HTTPServer):
    def __init__(self, config):
        self.vulnState = VulnState()
        addr = (config.get('addr', 'localhost'), config.get('port', 8666))
        HTTPServer.__init__(self, addr, VulnHandler)


def main():
    args = sys.argv[1:]
    if len(args) == 0:
        config = {}
    elif len(args) == 1:
        with open(args[0], 'rb') as f:
            config = json.load(f)
    else:
        help()
    vsrv = VulnServer(config)
    try:
        vsrv.serve_forever()
    except KeyboardInterrupt:
        print('Killed by keyboard interrupt')
        sys.exit(99)


def help():
    sys.stdout.write('Usage: ' + sys.argv[0] + ' [configfile]\n')
    sys.exit(2)


if __name__ == '__main__':
    main()
