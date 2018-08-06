#!/usr/bin/env python
# -*- coding: utf-8 -*-
# (c) 2018 Felix Fontein (@felixfontein) <felix@fontein.de>
#
# Written by Felix Fontein <felix@fontein.de>
# This file is part of Ansible
#
# Ansible is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Ansible is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Ansible.  If not, see <http://www.gnu.org/licenses/>.

import base64
import codecs
import logging
import os
import re
import ssl
import sys
import urllib

from functools import partial

from flask import Flask
from flask import request

from acme_tlsalpn import ALPNChallengeServer, gen_ss_cert
from OpenSSL import crypto

from dns_server import DNSServer


app = Flask(__name__)
app.config['LOGGER_HANDLER_POLICY'] = 'always'

PEBBLE_PATH = os.path.join(os.path.abspath(os.environ.get('GOPATH', '.')), 'src', 'github.com', 'letsencrypt', 'pebble')


challenges = {}


def log(message, data=None, program='Controller'):
    sys.stdout.write('[{0}] {1}\n'.format(program, message))
    if data:
        if not isinstance(data, list):
            data = [data]
        while data and not data[-1]:
            data = data[:-1]
        for value in data:
            sys.stdout.write('[{0}] | {1}\n'.format(program, value))
    sys.stdout.flush()


def setup_loggers():
    class SimpleLogger(logging.StreamHandler):
        def emit(self, record):
            try:
                msg = self.format(record)
                log(msg)
            except (KeyboardInterrupt, SystemExit):
                raise
            except Exception as _:
                self.handleError(record)

    log_handler = SimpleLogger()
    log_handler.setLevel(logging.DEBUG)
    app.logger.handlers = []
    app.logger.propagate = False
    app.logger.addHandler(log_handler)
    logger = logging.getLogger('werkzeug')
    logger.setLevel(logging.DEBUG)
    logger.handlers = []
    logger.propagate = False
    logger.addHandler(log_handler)


setup_loggers()


@app.route('/')
def m_index():
    return 'ACME test environment controller'


@app.route('/http/<string:host>/<string:filename>', methods=['PUT', 'DELETE'])
def http_challenge(host, filename):
    if request.method == 'PUT':
        if host not in challenges:
            challenges[host] = {}
        value = request.data
        log('Defining challenge file for {0}'.format(host), '/.well-known/acme-challenge/{0} => {1}'.format(filename, value))
        challenges[host][filename] = value
        return 'ok'
    else:
        if host not in challenges or filename not in challenges[host]:
            return 'not found', 404
        log('Removing challenge file for {0}'.format(host), '/.well-known/acme-challenge/{0}'.format(filename))
        del challenges[host][filename]
        return 'ok'


dns_server = DNSServer(port=53, log_callback=partial(log, program='DNS Server'))


@app.route('/dns/<string:record>', methods=['PUT', 'DELETE'])
def dns_challenge(record):
    if request.method == 'PUT':
        values = request.get_json(force=True)
        log('Adding TXT records for {0}'.format(record), values)
        dns_server.set_txt_records(record, values)
    else:
        log('Removing TXT records for {0}'.format(record))
        dns_server.clear_txt_records(record)
    return 'ok'


tls_alpn_server = ALPNChallengeServer(port=5001, log_callback=log)


def _get_alpn_key_cert_from_der_value(domain, data):
    der_value = b"DER:0420" + codecs.encode(base64.standard_b64decode(data), 'hex')
    # Create private key
    key = crypto.PKey()
    key.generate_key(crypto.TYPE_RSA, 2048)
    # Create self-signed certificates
    acme_extension = crypto.X509Extension(b"1.3.6.1.5.5.7.1.30.1", critical=True, value=der_value)
    cert_challenge = gen_ss_cert(key, [domain], extensions=[acme_extension])
    return key, cert_challenge


def _find_line_regex(lines, regex):
    pattern = re.compile(regex)
    for i, line in enumerate(lines):
        if re.fullmatch(pattern, line):
            return i
    raise Exception('Cannot find line in input which matches "{0}"!'.format(regex))


def _get_alpn_key_cert_from_pem_chain(domain, data):
    data = data.split(b'\n')
    # Extract challenge certificate
    cert_lines = data[_find_line_regex(data, b'-----BEGIN .*CERTIFICATE-----'):_find_line_regex(data, b'-----END .*CERTIFICATE-----') + 1]
    cert_challenge = crypto.load_certificate(crypto.FILETYPE_PEM, b'\n'.join(cert_lines))
    # Extract challenge private key
    key_lines = data[_find_line_regex(data, b'-----BEGIN .*PRIVATE KEY-----'):_find_line_regex(data, b'-----END .*PRIVATE KEY-----') + 1]
    key = crypto.load_privatekey(crypto.FILETYPE_PEM, b'\n'.join(key_lines))
    return key, cert_challenge


@app.route('/tls-alpn/<string:domain>/der-value-b64', methods=['PUT'])
def tls_alpn_challenge_put_b64(domain):
    log('Adding TLS ALPN challenge for domain {0} (Base64 encoded DER value)'.format(domain))
    key, cert_challenge = _get_alpn_key_cert_from_der_value(domain, request.data)
    cert_normal = gen_ss_cert(key, [domain], [])
    # Start/modify TLS-ALPN-01 challenge server
    tls_alpn_server.add(domain, key, cert_normal, cert_challenge)
    tls_alpn_server.update()
    return 'ok'


@app.route('/tls-alpn/<string:domain>/certificate-and-key', methods=['PUT'])
def tls_alpn_challenge_put_pem(domain):
    log('Adding TLS ALPN challenge for domain {0} (PEM certificate and key)'.format(domain))
    key, cert_challenge = _get_alpn_key_cert_from_pem_chain(domain, request.data)
    cert_normal = gen_ss_cert(key, [domain], [])
    # Start/modify TLS-ALPN-01 challenge server
    tls_alpn_server.add(domain, key, cert_normal, cert_challenge)
    tls_alpn_server.update()
    return 'ok'


@app.route('/tls-alpn/<string:domain>', methods=['DELETE'])
def tls_alpn_challenge_delete(domain):
    log('Removing TLS ALPN challenge for domain {0}'.format(domain))
    tls_alpn_server.remove(domain)
    tls_alpn_server.update()
    return 'ok'


@app.route('/.well-known/acme-challenge/<string:filename>')
def get_http_challenge(filename):
    host = request.headers.get('Host')
    i = host.find(':')
    if i >= 0:
        host = host[:i]
    if host not in challenges:
        log('Retrieving HTTP challenge for unknown host {0}!'.format(host))
        return 'unknown host', 404
    if filename not in challenges[host]:
        log('Retrieving unknown HTTP challenge {0} for host {0}!'.format(host, '/.well-known/acme-challenge/{0}'.format(filename)))
        return 'not found', 404
    log('Retrieving HTTP challenge {1} for host {0}'.format(host, '/.well-known/acme-challenge/{0}'.format(filename)))
    return challenges[host][filename]


@app.route('/root-certificate-for-acme-endpoint')
def get_root_certificate_minica():
    with open(os.path.join(PEBBLE_PATH, 'test', 'certs', 'pebble.minica.pem'), 'rt') as f:
        return f.read()


@app.route('/root-certificate-for-ca')
def get_root_certificate_pebble():
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return urllib.request.urlopen("https://localhost:14000/root", context=ctx).read()


if __name__ == "__main__":
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('CONTROLLER_PORT', 5000)))
