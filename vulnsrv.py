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
                _uc('<li><a href="get?') + html.escape(urlencode([('file', fn)])) + _uc('">') + html.escape(fn) + _uc('</a></li>\n')
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

<p>F&#x00fc;r den Angriff k&#x00f6;nnen Sie <a href="mac_attack.py">dieses Python-Skript</a> verwenden.
Das Skript erwartet, dass im lokalen Verzeichnis eine ausf&#x00fc;hrbare Datei ./mac_extension liegt, die mit den Argumenten <code>[Bekannter Hash]</code> <code>[Bekannte Eingabe]</code> <code>[Einzuf&#x00fc;gende Daten]</code> <code>[L&#x00e4;nge des secrets in Bytes (32)]</code> aufgerufen werden kann und das exploit zur&#x00fc;ckgibt.
</p>
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
        for k,v in cookies.items():
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

    error_message_format = u"""<!DOCTYPE html>
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
"""
    error_content_type = 'text/html; charset=utf-8'

    def send_error(self, code, message=u''):
        codestr, explain = self.responses.get(code, (str(code), u'Unknown code'))
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
