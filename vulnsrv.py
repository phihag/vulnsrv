#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import base64
import binascii
import bz2
import hashlib
import os
import os.path
import pickle
import re
import struct
import sqlite3
import threading
import time
import urllib
import sys

try:
    import json
except ImportError: # Python <2.6, use trivialjson (https://github.com/phihag/trivialjson):
    import re
    class json(object):
        @staticmethod
        def loads(s):
            s = s.decode('UTF-8')
            def raiseError(msg, i):
                raise ValueError(msg + ' at position ' + str(i) + ' of ' + repr(s) + ': ' + repr(s[i:]))
            def skipSpace(i, expectMore=True):
                while i < len(s) and s[i] in ' \t\r\n':
                    i += 1
                if expectMore:
                    if i >= len(s):
                        raiseError('Premature end', i)
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
                    if len(esc) == 1+4:
                        return unichr(int(esc[1:5], 16))
                    if len(esc) == 5+6 and esc[5:7] == '\\u':
                        hi = int(esc[1:5], 16)
                        low = int(esc[7:11], 16)
                        return unichr((hi - 0xd800) * 0x400 + low - 0xdc00 + 0x10000)
                raise ValueError('Unknown escape ' + str(esc))
            def parseString(i):
                i += 1
                e = i
                while True:
                    e = s.index('"', e)
                    bslashes = 0
                    while s[e-bslashes-1] == '\\':
                        bslashes += 1
                    if bslashes % 2 == 1:
                        e += 1
                        continue
                    break
                rexp = re.compile(r'\\(u[dD][89aAbB][0-9a-fA-F]{2}\\u[0-9a-fA-F]{4}|u[0-9a-fA-F]{4}|.|$)')
                stri = rexp.sub(decodeEscape, s[i:e])
                return (e+1,stri)
            def parseObj(i):
                i += 1
                res = {}
                i = skipSpace(i)
                if s[i] == '}': # Empty dictionary
                    return (i+1,res)
                while True:
                    if s[i] != '"':
                        raiseError('Expected a string object key', i)
                    i,key = parseString(i)
                    i = skipSpace(i)
                    if i >= len(s) or s[i] != ':':
                        raiseError('Expected a colon', i)
                    i,val = parse(i+1)
                    res[key] = val
                    i = skipSpace(i)
                    if s[i] == '}':
                        return (i+1, res)
                    if s[i] != ',':
                        raiseError('Expected comma or closing curly brace', i)
                    i = skipSpace(i+1)
            def parseArray(i):
                res = []
                i = skipSpace(i+1)
                if s[i] == ']': # Empty array
                    return (i+1,res)
                while True:
                    i,val = parse(i)
                    res.append(val)
                    i = skipSpace(i) # Raise exception if premature end
                    if s[i] == ']':
                        return (i+1, res)
                    if s[i] != ',':
                        raiseError('Expected a comma or closing bracket', i)
                    i = skipSpace(i+1)
            def parseDiscrete(i):
                for k,v in {'true': True, 'false': False, 'null': None}.items():
                    if s.startswith(k, i):
                        return (i+len(k), v)
                raiseError('Not a boolean (or null)', i)
            def parseNumber(i):
                mobj = re.match('^(-?(0|[1-9][0-9]*)(\.[0-9]*)?([eE][+-]?[0-9]+)?)', s[i:])
                if mobj is None:
                    raiseError('Not a number', i)
                nums = mobj.group(1)
                if '.' in nums or 'e' in nums or 'E' in nums:
                    return (i+len(nums), float(nums))
                return (i+len(nums), int(nums))
            CHARMAP = {'{': parseObj, '[': parseArray, '"': parseString, 't': parseDiscrete, 'f': parseDiscrete, 'n': parseDiscrete}
            def parse(i):
                i = skipSpace(i)
                i,res = CHARMAP.get(s[i], parseNumber)(i)
                i = skipSpace(i, False)
                return (i,res)
            i,res = parse(0)
            if i < len(s):
                raise ValueError('Extra data at end of input (index ' + str(i) + ' of ' + repr(s) + ': ' + repr(s[i:]) + ')')
            return res

try:
    _uc = unicode # Python 2
except NameError:
    _uc = str # Python 3

_b = lambda s: s.encode('ascii')

try:
    compat_bytes = bytes
except NameError: # Python < 2.6
    compat_bytes = str

try:
    import Cookie as _cookies
except ImportError:
    import http.cookies as _cookies

try:
    import Queue
    _queue = Queue.Queue
except ImportError: # Python 3
    import queue
    _queue = queue.Queue

try:
    from SocketServer import ThreadingMixIn
except ImportError:
    from socketserver import ThreadingMixIn

try:
    from BaseHTTPServer import HTTPServer,BaseHTTPRequestHandler
except ImportError:
    from http.server import HTTPServer,BaseHTTPRequestHandler

try:
    import urlparse
    _urlparse = urlparse.urlparse
except ImportError: # Python 3
    import urllib.parse
    _urlparse = urllib.parse.urlparse

try:
    from urllib.parse import urlencode
except ImportError: # Python <3
    from urllib import urlencode

try:
    import html
    html.escape
except (ImportError,AttributeError): # Python < 3.2
    _escape_map = {ord('&'): _uc('&amp;'), ord('<'): _uc('&lt;'), ord('>'): _uc('&gt;')}
    _escape_map_full = {ord('&'): _uc('&amp;'), ord('<'): _uc('&lt;'), ord('>'): _uc('&gt;'), ord('"'): _uc('&quot;'), ord('\''): _uc('&#x27;')}
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
        kbin,eq,vbin = qel.partition(_b('='))
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
            conn.isolation_level = None # auto-commit
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
                    _type,e,_traceback = sys.exc_info()
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

    @_VulnState_locked
    def reset(self):
        self._csrfMessages = []
        self._xssMessages = []
        # TODO replace this with a Python in-memory database, which takes DBDATA in its constructor (and only needs to be initialized once)
        self._sqlThread.query('_reset_')
        for tableName,td in DBDATA.items():
            csql = ('CREATE TABLE ' + tableName + ' (' +
                ','.join(col['name'] + ' ' + col['type'] for col in td['structure'])
                + ')')
            self._sqlThread.query(csql)
            for d in td['data']:
                dsql = ('INSERT INTO ' + tableName +
                    ' (' + ','.join(k for k,v in d.items()) + ')' +
                    ' VALUES(' + ','.join("'" + v.replace("'", "''") + "'" for k,v in d.items()) +
                ')')
                self._sqlThread.query(dsql)

def msgsToHtml(msgs):
    res = (
_uc('''
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
            getParams = query2dict(reqp.query.encode('ascii'))
            postParams = self._readPostParams()
        except ValueError:
            _type,e,_traceback = sys.exc_info()
            self.send_error(400, str(e))
            return
        sessionID = self._getSessionID(False)

        if reqp.path == '/clientauth/secret':
            if self._csrfCheck(postParams): # Technically, not a problem here - until log who got the secret or so
                self._writeHtmlDoc(
                    _uc('<code class="secret">')
                    + html.escape(base64.b16decode('4356452F4D49545245'.encode('ascii')).decode('UTF-8')) +
                    _uc('</code>')
                    , 'Geheimnis', sessionID)
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
                mac = hashlib.sha256(self.server.mac_secret + val.encode('ascii')).hexdigest()
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
            _type,e,_traceback = sys.exc_info()
            self.send_error(400, 'Invalid query format: ' + str(e))
            return
        sessionID = self._getSessionID()

        if reqp.path == '/':
            self._writeHtmlDoc(
_uc('''
<ol class="mainMenu">
<li><a href="clientauth/">Client-Side Authorization Check</a></li>
<li><a href="csrf/">Cross-Site Request Forgery (CSRF)</a></li>
<li><a href="xss/?username=Benutzer%21">Cross-Site Scripting (XSS)</a></li>
<li><a href="sqlinjection/">SQL Injection</a></li>
<li><a href="pathtraversal/">Path Traversal</a></li>
<li><a href="mac/">MAC Length Extension</a></li>
</ol>'''), 'vulnsrv', sessionID)
        elif reqp.path == '/clientauth/':
            self._writeHtmlDoc(
_uc('''
<p>Finden Sie das Geheimnis heraus!</p>

<form action="secret" method="post">
<input type="submit" value="Geheimnis herausfinden"
onclick="''')
+ html.escape('if (\'you\' != \'admin\') {alert(\'Zugriff verweigert!\'); return false;} else return true;', True) +
_uc('''" />''')
+ self._getCsrfTokenField(sessionID) +
_uc('''</form>
'''), 'Aufgabe 1: Client-Side Authorization Check', sessionID)
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
''') + msgsToHtml(self.vulnState.csrfMessages), 'Aufgabe 2: CSRF', sessionID)
        elif reqp.path == '/xss/':
            username = getParams.get('username', 'Unbekannter')
            self._writeHtmlDoc(
_uc('<div>Hallo ')
+ _uc(username) +
_uc('''</div>
<p>Das untenstehende Formular ist gegen Cross-Site Request Forgery gesch&uuml;tzt.
Erstellen Sie eine HTML-Datei <code>evil-xss.html</code>, bei deren Aufruf der arglose Benutzer hier trotzdem unfreiwillig eine &uuml;belgesinnte Nachricht hinterl&auml;sst.
</p>

<form action="send" enctype="application/x-www-form-urlencoded" method="post">
''')
+ self._getCsrfTokenField(sessionID) +
_uc('''
<input type="text" name="message" autofocus="autofocus" required="required" placeholder="Eine freundliche Nachricht" size="50" />
<input type="submit" value="Senden" />
</form>
''') + msgsToHtml(self.vulnState.xssMessages), 'Aufgabe 3: XSS', sessionID)
        elif reqp.path == '/sqlinjection/':
            webMessages = self.vulnState.sqlQuery("SELECT id,msg FROM messages WHERE user='web'")
            self._writeHtmlDoc(
_uc('''
<p>In der untenstehenden Tabelle sehen Sie die Nachrichten an den Benutzer <code>web</code>. Welche Nachrichten hat der Benutzer <code>admin</code> bekommen?</p>

<h2>Nachrichten an <code>web</code></h2>

<ul class="messages">''')
+ '\n'.join('<li><a href="/sqlinjection/msg?id=' + html.escape(str(row[0])) + '">' + html.escape(row[1]) + '</a></li>' for row in webMessages) +
_uc('</ul>'), 'Aufgabe 4: SQL Injection', sessionID)
        elif reqp.path == '/sqlinjection/msg':
            msgNum = getParams.get('id', '')
            sql = "SELECT id,user,msg FROM messages WHERE user='web' AND id='" + msgNum + "'"
            try:
                msgs = self.vulnState.sqlQuery(sql)
                if len(msgs) == 0:
                    msgHtml = '<td colspan="3">Keine web-Nachrichten gefunden</td>'
                else:
                    msgHtml = '\n'.join('<tr>' + ''.join('<td>' + html.escape(str(cell)) + '</td>' for cell in row) + '</tr>' for row in msgs)
            except:
                _type,e,_traceback = sys.exc_info()
                msgHtml = '<td colspan="3" class="error">' + html.escape(str(e)) + '</td>'
            self._writeHtmlDoc(
_uc('''
<table class="messages">
<thead><tr><th>ID</th><th>Benutzer</th><th>Nachricht</th></tr></thead>
''')
+ msgHtml +
_uc('''
</table>
<p><a href="/sqlinjection/">Zur&uuml;ck zur &Uuml;bersicht</a></p>
'''), 'Detailansicht: Nachricht ' + msgNum, sessionID)
        elif reqp.path == '/pathtraversal/':
            fileHtml = _uc('').join(
                _uc('<li><a href="get?') + html.escape(urllib.urlencode([('file', fn)])) + _uc('">') + html.escape(fn) + _uc('</a></li>\n')
                for fn in FILES['/var/www/img']['content'])
            self._writeHtmlDoc(
_uc('''
<p>Welchen Unix-Account sollte ein Angreifer n&auml;her untersuchen?</p>

<p><em>Bonus-Aufgabe</em>: Was ist das Passwort des Accounts?</p>

<p>Dateien zum Download:</p>

<ul>''')
+ fileHtml +
_uc('</ul>'), 'Aufgabe 5: Path Traversal', sessionID)
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
                if isinstance(raw_cookie, compat_bytes): # Python 2.x
                    raw_cookie = raw_cookie.decode('latin1')
                mac,_,session_data_str = raw_cookie.rpartition(_uc('!'))
                session_data = session_data_str.encode('latin1')
                secret = self.server.mac_secret
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
            self._writeHtmlDoc(
_uc('''
<p>Loggen Sie sich als Benutzer admin ein (ohne das Geheimnis aus dem Server-Prozess auszulesen).
Schreiben Sie daf&#x00fc;r ein Programm, das den korrekten Cookie-Wert berechnet.</p>

<form method="post" action="login">''')
+ self._getCsrfTokenField(sessionID) +
_uc('''<input type="submit" value="Gast-Login" />
</form>

<h3>Aktuelle Session-Daten:</h3>

<p>Cookie (roh): <code>''') + html.escape(raw_cookie) + _uc('''</code> (''') + html.escape(_uc(len(raw_cookie))) + _uc(''' Bytes)</p>

<dl>
<dt>Benutzername:</dt><dd>''') + html.escape(user) + _uc('''</dd>
<dt>Login-Zeit:</dt><dd>''') + html.escape(timestamp) + _uc('''</dd>
</dl>
'''), 'Length Extension-Angriffe gegen MAC', sessionID)
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

    def _writeHtmlDoc(self, htmlContent, title, sessionID):
        title = _uc(title)
        mimeType = _uc('text/html; charset=utf-8')
        htmlCode = (
_uc('''<!DOCTYPE html>
<html>
<head>
<meta http-equiv="Content-Type" content="''')
+ html.escape(mimeType) +
_uc('''"/>
<title>''')
+ html.escape(title) +
_uc('''</title>
<style type="text/css">
body {margin: 0; padding: 0 2em;}
.mainMenu {font-size: 160%;}
h1 {text-align: center;}
.secret{font-size: 180%; /*background: #000;*/}
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
<h1>''')
+ html.escape(title) +
_uc('</h1>\n')
+ htmlContent +
_uc('''
<nav>
<a href="/clientauth/">Client-Side Authorization Check</a>
<a href="/csrf/">Cross-Site Request Forgery (CSRF)</a>
<a href="/xss/?username=Benutzer%21">Cross-Site Scripting (XSS)</a>
<a href="/sqlinjection/">SQL Injection</a>
<a href="/pathtraversal/">Path Traversal</a>
<a href="/mac/">MAC Length Extension</a>
<span class="sep"></span>
<form class="reset" method="post" action="/reset">''')
+ self._getCsrfTokenField(sessionID) +
_uc('''<input type="submit" value="clear data" />
</form>
</nav>
</body>
</html>'''))
        htmlBytes = htmlCode.encode('utf-8')

        self.send_response(200)
        self._writeCookies()
        self.send_header('X-XSS-Protection', '0')
        self.send_header('Content-Length', str(len(htmlBytes)))
        self.send_header('Content-Type', mimeType)
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
        for k,v in cookies.items():
            assert re.match(r'^[a-zA-Z0-9_-]+$', k)
            c[k] = v
            c[k]['path'] = '/'
            if sys.version_info >= (2, 6):
                c[k]['httponly'] = True
        outp = c.output(sep=_uc('\r\n')) + _uc('\r\n')
        assert isinstance(outp, _uc)
        self.wfile.write(outp.encode('utf-8'))

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

class VulnServer(ThreadingMixIn, HTTPServer):
    def __init__(self, config):
        self.vulnState = VulnState()
        self.mac_secret = hashlib.md5(os.urandom(32)).hexdigest().encode('ascii')
        assert len(self.mac_secret) == 32
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
