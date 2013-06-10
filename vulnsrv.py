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
        elif reqp.path == '/mac/set':
            if self._csrfCheck(postParams):
                sessionval_input = postParams.get('sessionval', '')
                assert isinstance(sessionval_input, _uc)
                sessionval = binascii.a2b_hex(sessionval_input.encode('ascii'))
                c = {'mac_session': sessionval}
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
                assert isinstance(raw_cookie, _uc)
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
Schreiben Sie daf&uuml;r ein Programm, das den korrekten Cookie-Wert berechnet.</p>

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

<!--
This form does not impact security at all, but is hidden in order to avoid confusion.
-->
<form method="post" action="set">''')
+ self._getCsrfTokenField(sessionID) +
_uc('''<input placeholder="Cookie als hexadezimale Byte-Werte" type="text" name="sessionval" size="100" required="required" pattern="[a-zA-Z0-9]*" value="''') + html.escape(raw_cookie_hex) + _uc('''" />
<input type="submit" value="Cookie für den Browser setzen" />
</form>
'''), 'Length Extension-Angriffe gegen MAC', sessionID)
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
            assert isinstance(v, _uc)
            c[k] = v
            c[k]['path'] = '/'
            c[k]['httponly'] = True
        outp = c.output(sep=_uc('\r\n')) + _uc('\r\n')
        assert isinstance(outp, _uc)
        self.wfile.write(outp.encode('utf-8'))

    def _readCookies(self):
        hdr = self.headers.get('cookie', '')
        assert isinstance(hdr, _uc)
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
        self.mac_secret = hashlib.sha256(os.urandom(32)).hexdigest().encode('ascii')
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
    vsrv.serve_forever()

def help():
    sys.stdout.write('Usage: ' + sys.argv[0] + ' [configfile]\n')
    sys.exit(2)


if __name__ == '__main__':
    main()
