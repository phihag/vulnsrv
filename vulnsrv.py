#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import with_statement

import bz2,sys,threading,base64,os,urllib,os.path,pickle,sqlite3,struct

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

_FILES_RAW = "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"

_INITQUERIES_RAW = "KGxwMApTJ19yZXNldF8nCnAxCmFTJ0NSRUFURSBUQUJMRSBtZXNzYWdlcyAoaWQgSU5URUdFUiBQUklNQVJZIEtFWSBBU0MsIHVzZXIgVEVYVCwgbXNnIFRFWFQpJwpwMgphUyJJTlNFUlQgSU5UTyBtZXNzYWdlcyAodXNlciwgbXNnKSBWQUxVRVMgKCd3ZWInLCAnSGVsbG8sIGRhdGFiYXNlIHdvcmxkJykiCnAzCmFTIklOU0VSVCBJTlRPIG1lc3NhZ2VzICh1c2VyLCBtc2cpIFZBTFVFUyAoJ2FkbWluJywgJ2J1Z3RyYXEnKSIKcDQKYVMiSU5TRVJUIElOVE8gbWVzc2FnZXMgKHVzZXIsIG1zZykgVkFMVUVTICgnYWRtaW4nLCAnZnVsbCBkaXNjbG9zdXJlJykiCnA1CmFTIklOU0VSVCBJTlRPIG1lc3NhZ2VzICh1c2VyLCBtc2cpIFZBTFVFUyAoJ3dlYicsICdZb3UgY2FuJyd0IHNlZSBoaWRkZW4gbWVzc2FnZXMnKSIKcDYKYVMiSU5TRVJUIElOVE8gbWVzc2FnZXMgKHVzZXIsIG1zZykgVkFMVUVTICgnQ0VSVCcsICdSZW1lbWJlciB0byBjaGVjayBmb3IgU1FMIGluamVjdGlvbnMnKSIKcDcKYS4="

_FAVICON_RAW = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAABHNCSVQICAgIfAhkiAAAAAlwSFlzAAABYgAAAWIBXyfQUwAAABl0RVh0U29mdHdhcmUAd3d3Lmlua3NjYXBlLm9yZ5vuPBoAAAIvSURBVDiNlZPPS9NxGMdfz8cfrTVJJxOJOTWRDgo2CekHNUe3SiqpQ/euHqJTINQQBA9eCjvkX+At7BBoZ5tJTWjhpqamGBK52Kbfrdy+Twf3tdFB8YHn8Hl/nvf7efP+8EFVedZLpapynB5rpl9VMQDerzzlmPV7h2EA8zwgnXsWD8ovV0WGkiILn0V2YyLFLyKpRZG5dZE+ZyafpX2sTa5XVig3d7O0vmiXtrvLmCy8y0KgXHAP6oALApMFkTdv/cSKfzAU6JGXLVzcXuO9q4ZsTwGXK0fVkf4FphS8zVwRVWXUKxu5X/hFoKMGzmSOzuDHKTZu7WjAANzY4X59LVS7oDZfmjCGzvl5zm1t0Tg4CEDr+Djn02maJidp2aUOAFVlBYZmQaOCzrLfawMDmkql1O12673+fp1zu1VtW8PhsPp8Pv3Y1aXfwW0AinAVQPSfxfT0NB6Ph1AoxKWODmzLopjJEAqFCPf2YieTFKDPANiU7JRVPpEg0d3Nq2CQayMjAMQCAR6K8GRmBjufx4amylKo+f8FAHLxOLl4nEIwyKdYjBOWRcXEBHubm85jZI2z8LDEz0Yi9ABdtk1jJHKA25AxJaXcYQI/h4dLDJvt0dEDXCBtAAyslhOqoVAFRedsRaO4SkusaNQhUwFLBuAkPK6GAvug+uBOA9yuAhvAAykv+OvhtSN6Ghb8qksH33MTLicguQ6PHOwb9C3AygZ4HWwRPizB1DI0qCp/Af4hCtO0EP8SAAAAAElFTkSuQmCC"

FILES = pickle.loads(bz2.decompress(base64.b64decode(_FILES_RAW.encode('ascii'))))
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
			print(repr(FILES['/var/www/img']['content']))
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
					curPath.pop()
				else:
					curPath.append(pel)
			finalPath = '/' + '/'.join(curPath)
			if finalPath.endswith('/'):
				finalPath = finalPath[:-1]
			print(FILES.keys())
			print('path: ' + repr(finalPath))
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
