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

# Some of these headers allow attacks, do not copy for use outside of vulnsrv!
DEFAULT_HEADERS = [
    ('X-Frame-Options', 'DENY'),
    ('X-XSS-Protection', '0'),
    ('Cache-Control', 'private, max-age=0, no-cache'),
    ('Pragma', 'no-cache'),
]


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
    def reflected_xss_message(self, msg):
        self._reflected_xss_messages.append(msg)

    @property
    @_VulnState_locked
    def reflected_xss_messages(self):
        return self._reflected_xss_messages[:]

    @_VulnState_locked
    def stored_xss_message(self, msg):
        self._stored_xss_messages.append(msg)

    @_VulnState_locked
    def remove_stored_xss_messages(self):
        self._stored_xss_messages = []

    @property
    @_VulnState_locked
    def stored_xss_messages(self):
        return self._stored_xss_messages[:]

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
        self._reflected_xss_messages = []
        self._stored_xss_messages = []
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
        elif reqp.path == '/reflected_xss/send':
            if self._csrfCheck(postParams):
                msg = postParams.get('message', '')
                if msg == '':
                    self.send_error(400, 'Missing or empty message')
                else:
                    self.vulnState.reflected_xss_message(msg)
                    self._redirect('/reflected_xss/?username=Sender%2C')
        elif reqp.path == '/stored_xss/send':
            if self._csrfCheck(postParams):
                msg = postParams.get('message', '')
                if msg == '':
                    self.send_error(400, 'Missing or empty message')
                else:
                    self.vulnState.stored_xss_message(msg)
                    self._redirect('/stored_xss/')
        elif reqp.path == '/stored_xss/clear':
            if self._csrfCheck(postParams):
                self.vulnState.remove_stored_xss_messages()
                self._redirect('/stored_xss/')
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
<li><a href="reflected_xss/?username=Benutzer%21">Reflected Cross-Site Scripting (XSS)</a></li>
<li><a href="stored_xss/?username=Benutzer%21">Stored Cross-Site Scripting (XSS)</a></li>
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
        elif reqp.path == '/reflected_xss/':
            username = getParams.get('username', 'Unbekannter')
            self._writeHtmlDoc(_uc(
                '''<div>Hallo %s</div>
<p>Das untenstehende Formular ist gegen Cross-Site Request Forgery gesch&uuml;tzt.
Erstellen Sie eine HTML-Datei <code>evil-reflected-xss.html</code>, bei deren Aufruf der arglose Benutzer hier trotzdem unfreiwillig eine &uuml;belgesinnte Nachricht hinterl&auml;sst.
</p>

<form action="send" enctype="application/x-www-form-urlencoded" method="post">
<input type="text" name="message" autofocus="autofocus" required="required" placeholder="Eine freundliche Nachricht" size="50" />
%s
<input type="submit" value="Senden" />
</form>
''') % (_uc(username), self._getCsrfTokenField(sessionID)) + msgsToHtml(self.vulnState.reflected_xss_messages), 'Reflected XSS', sessionID)
        elif reqp.path == '/stored_xss/':
            self._writeHtmlDoc(_uc(
                '''<div>Hallo <span class="userid">%s</span></div>
<p>Das untenstehende Formular ist gegen Cross-Site Request Forgery gesch&uuml;tzt.
Sorgen Sie daf&uuml;r, dass jeder Benutzer der diese Seite aufruft unfreiwillig eine Nachricht hinterl&auml;sst, die IP und Port des Benutzers beinhaltet.
</p>

<form action="send" enctype="application/x-www-form-urlencoded" method="post">
<input type="text" name="message" autocomplete="off" autofocus="autofocus" required="required" placeholder="Eine freundliche Nachricht" size="50" />
%s
<input type="submit" value="Senden" />
</form>
%s

<script>
function show(messages_json) {
    var messages = JSON.parse(messages_json);
    var list = document.querySelector('.messages');
    messages.forEach(function(m) {
        var li = document.createElement('li');
        li.appendChild(document.createTextNode(m));
        list.appendChild(li);
    });
}

function download() {
    var xhr = new XMLHttpRequest();
    xhr.dataType = 'text';
    xhr.onload = function(e) {
        show(xhr.responseText);
    };
    xhr.open('GET', 'json');
    xhr.send();
}

function send(msg) {
    var xhr = new XMLHttpRequest();
    var token = document.querySelector('input[name="csrfToken"]').value;
    var params = 'csrfToken=' + encodeURIComponent(token) + '&message=' +encodeURIComponent(msg);
    xhr.open('POST', 'send');
    xhr.setRequestHeader('Content-type', 'application/x-www-form-urlencoded');
    xhr.send(params);

}

function user() {
    return document.querySelector('.userid').textContent;
}
</script>

<script>
// JSON direkt einbinden
var messages_json = '%s';
show(messages_json);

// Vorheriger Code:
// download();

</script>

<form action="clear" enctype="application/x-www-form-urlencoded" method="post">
%s
<button role="submit">Alle Nachrichten l&ouml;schen</button
</form>

''') % (_uc(':').join(map(_uc, self.client_address)), self._getCsrfTokenField(sessionID), msgsToHtml([]), json.dumps(self.vulnState.stored_xss_messages), self._getCsrfTokenField(sessionID)), 'Stored XSS', sessionID)
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
        elif reqp.path == '/stored_xss/json':
            self._write_json(self.vulnState.stored_xss_messages)
        else:
            self.send_error(404)

    def _writeHtmlDoc(self, htmlContent, title, sessionID, add_headers=None):
        if add_headers is None:
            add_headers = DEFAULT_HEADERS

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
<a href="/reflected_xss/?username=Benutzer%%21">Reflected XSS</a>
<a href="/stored_xss/"">Stored XSS</a>
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

    def _write_json(self, data):
        json_bytes = json.dumps(data).encode('utf-8')

        self.send_response(200)
        self._writeCookies()
        self.send_header('Content-Length', str(len(json_bytes)))
        self.send_header('Content-Type', 'application/json')
        for k, v in DEFAULT_HEADERS:
            self.send_header(k, v)
        self.end_headers()

        self.wfile.write(json_bytes)

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
