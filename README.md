vulnsrv is a web applications that allows students to exploit various common security vulnerabilites.

All vulnerabilities are only simulated; vulnsrv is intended to be 100% safe. However, vulnsrv may contain bugs and security vulnerabilities, like every other program.
Note that vulnsrv reproduces user-supplied content, which can be rude/in violation of local laws restricting speech. By default, it accepts only connections from the local machine. Due to the simulated security vulnerabilities, vulnsrv must not be mapped in(proxied) in a regular domain, as doing so would expose the domain and super-domains to Cross-Site Scripting vulnerabilties.

vulnsrv was originally written to provide excercises for a [German computer security lecture](http://www.cn.uni-duesseldorf.de/teaching/sose11/netsec). vulnsrv is intended to be easier to use and simpler than [Google Gruyere](http://google-gruyere.appspot.com/), and used in an educational context.

# Running vulnsrv

You can either run it yourself or use the web service at [vulnsrv.net](http://vulnsrv.net/) (TODO: Not yet deployed, see [issue #11](https://github.com/phihag/vulnsrv/issues/11)).

1. Download [vulnsrv.py](https://raw.github.com/phihag/vulnsrv/master/vulnsrv.py).
2. Execute it with `python vulnsrv.py`

# System Requirements

For running vulnsrv yourself: Python 2.5 or newer (2.6+ recommended in service mode, 2.6+ required for development).
vulnsrv should work under Python 3 even without 2to3.

For the user, any web browser (although a modern web browser that includes developer tools is certainly a good idea).

# Developing vulnsrv

Development goals in the near future are [**translation**](https://github.com/phihag/vulnsrv/issues/3) and a [service mode](https://github.com/phihag/vulnsrv/issues/2) for deployment on vulnsrv.net. If you can translate vulnsrv (about 30 lines of text), feel free to contact [Philipp Hagemeister](https://github.com/phihag).
