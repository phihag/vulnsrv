#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import sys,threading,base64,os,urllib,os.path,pickle,sqlite3,struct

try:
	import json
except ImportError: # Python < 2.6
	pass # configuration file won't work, but everything else should be fine

try:
	_uc = unicode # Python 2
except NameError:
	_uc = str # Python 3

_b = lambda s: s.encode('ascii')

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
		res = resbin.decode('UTF-8')
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

_FILES_RAW = "TODO: Update from tree"

_INITQUERIES_RAW = "KGxwMApTJ19yZXNldF8nCnAxCmFTJ0NSRUFURSBUQUJMRSBtZXNzYWdlcyAoaWQgSU5URUdFUiBQUklNQVJZIEtFWSBBU0MsIHVzZXIgVEVYVCwgbXNnIFRFWFQpJwpwMgphUyJJTlNFUlQgSU5UTyBtZXNzYWdlcyAodXNlciwgbXNnKSBWQUxVRVMgKCd3ZWInLCAnSGVsbG8sIGRhdGFiYXNlIHdvcmxkJykiCnAzCmFTIklOU0VSVCBJTlRPIG1lc3NhZ2VzICh1c2VyLCBtc2cpIFZBTFVFUyAoJ2FkbWluJywgJ2J1Z3RyYXEnKSIKcDQKYVMiSU5TRVJUIElOVE8gbWVzc2FnZXMgKHVzZXIsIG1zZykgVkFMVUVTICgnYWRtaW4nLCAnZnVsbCBkaXNjbG9zdXJlJykiCnA1CmFTIklOU0VSVCBJTlRPIG1lc3NhZ2VzICh1c2VyLCBtc2cpIFZBTFVFUyAoJ3dlYicsICdZb3UgY2FuJyd0IHNlZSBoaWRkZW4gbWVzc2FnZXMnKSIKcDYKYVMiSU5TRVJUIElOVE8gbWVzc2FnZXMgKHVzZXIsIG1zZykgVkFMVUVTICgnQ0VSVCcsICdSZW1lbWJlciB0byBjaGVjayBmb3IgU1FMIGluamVjdGlvbnMnKSIKcDcKYS4="

_FAVICON_RAW = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAABYgAAAWIBXyfQUwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAIvSURBVDiNlZPPS9NxGMdfz8cfrTVJJxOJOTWRDgo2CekHNUe3SiqpQ/euHqJTINQQBA9eCjvkX+At7BBoZ5tJTWjhpqamGBK52Kbfrdy+Twf3tdFB8YHn8Hl/nvf7efP+8EFVedZLpapynB5rpl9VMQDerzzlmPV7h2EA8zwgnXsWD8ovV0WGkiILn0V2YyLFLyKpRZG5dZE+ZyafpX2sTa5XVig3d7O0vmiXtrvLmCy8y0KgXHAP6oALApMFkTdv/cSKfzAU6JGXLVzcXuO9q4ZsTwGXK0fVkf4FphS8zVwRVWXUKxu5X/hFoKMGzmSOzuDHKTZu7WjAANzY4X59LVS7oDZfmjCGzvl5zm1t0Tg4CEDr+Djn02maJidp2aUOAFVlBYZmQaOCzrLfawMDmkql1O12673+fp1zu1VtW8PhsPp8Pv3Y1aXfwW0AinAVQPSfxfT0NB6Ph1AoxKWODmzLopjJEAqFCPf2YieTFKDPANiU7JRVPpEg0d3Nq2CQayMjAMQCAR6K8GRmBjufx4amylKo+f8FAHLxOLl4nEIwyKdYjBOWRcXEBHubm85jZI2z8LDEz0Yi9ABdtk1jJHKA25AxJaXcYQI/h4dLDJvt0dEDXCBtAAyslhOqoVAFRedsRaO4SkusaNQhUwFLBuAkPK6GAvug+uBOA9yuAhvAAykv+OvhtSN6Ghb8qksH33MTLicguQ6PHOwb9C3AygZ4HWwRPizB1DI0qCp/Af4hCtO0EP8SAAAAAElFTkSuQmCC"

FILES = pickle.loads(base64.b64decode(_FILES_RAW.encode('ascii')))
INITQUERIES = pickle.loads(base64.b64decode(_INITQUERIES_RAW.encode('ascii')))
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
		for q in INITQUERIES:
			self._sqlThread.query(q)

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
			self._writeHtmlDoc(
_uc('''
<p>Welchen Unix-Account sollte ein Angreifer n&auml;her untersuchen?</p>

<p><em>Bonus-Aufgabe</em>: Was ist das Passwort des Accounts?</p>

<p>Dateien zum Download:</p>

<ul>
<li><a href="get?file=good.png">good.png</a></li>
<li><a href="get?file=good_small.png">good_small.png</a></li>
</ul>'''), 'Aufgabe 5: Path Traversal', sessionID)
		elif reqp.path == '/pathtraversal/get':
			fn = '/var/www/imgs/' + getParams.get('file', '')
			# Resolve the path.
			# If we were using a real filesystem, this would be done automatically by the OS filesystem functions, of course
			curPath = []
			for pel in fn.split('/'):
				if pel == '' or pel == '.':
					continue
				if pel == '..':
					curPath.pop()
				else:
					curPath.append(pel)
			finalPath = '/' + '/'.join(curPath)
			if finalPath in FILES:
				fdata = FILES[finalPath]
				fileBlob = base64.b64decode(fdata['blob_b64'].encode('ascii'))
				self.send_response(200)
				self.send_header('Content-Type', fdata['type'])
				self.send_header('Content-Length', str(len(fileBlob)))
				self.end_headers()
				self.wfile.write(fileBlob)
			else:
				self.send_error(404)
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
		sessionCookie = _cookies.SimpleCookie()
		sessionCookie['sessionID'] = sessionID # Automatically converted to Morsel
		sessionCookie['sessionID']['path'] = '/'
		self.wfile.write((sessionCookie.output(sep='\r\n') + '\r\n').encode('ascii'))
		self.send_header('X-XSS-Protection', '0')
		self.send_header('Content-Length', str(len(htmlBytes)))
		self.send_header('Content-Type', mimeType)
		self.end_headers()

		self.wfile.write(htmlBytes)

	def _redirect(self, target):
		self.send_response(302)
		self.send_header('Location', target)
		self.send_header('Content-Length', '0')
		self.end_headers()

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
		cookieHeader = self.headers.get('cookie', '')
		cookie = _cookies.SimpleCookie(cookieHeader)
		if 'sessionID' in cookie:
			return cookie['sessionID'].value
		elif autogenerate:
			return base64.b64encode(os.urandom(16))
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
		printHelp()
	vsrv = VulnServer(config)
	vsrv.serve_forever()

def printHelp():
	sys.stdout.write('Usage: ' + sys.argv[0] + ' [configfile]\n')
	sys.exit(2)


if __name__ == '__main__':
	main()
