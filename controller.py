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
import subprocess
import sys

from flask import Flask
from flask import request

from acme_tlsalpn import ALPNChallengeServer, gen_ss_cert
from OpenSSL import crypto


app = Flask(__name__)
app.config['LOGGER_HANDLER_POLICY'] = 'always'

ZONES_PATH = os.path.abspath(os.environ.get('ZONES_PATH', '.'))

PEBBLE_PATH = os.path.join(os.path.abspath(os.environ.get('GOPATH', '.')), 'src', 'github.com', 'letsencrypt', 'pebble')


zones = set(['example.com', 'example.org'])
challenges = {}
txt_records = {}


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


def execute(what, command):
    try:
        p = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        (so, se) = p.communicate()
        data = []
        if so:
            data.append('*** STDOUT:')
            data.extend(so.decode('utf8').split('\n'))
        if se:
            data.append('*** STDERR:')
            data.extend(se.decode('utf8').split('\n'))
        log(what, data)
    except Exception as e:
        log('FAILED: {0}'.format(what), e)


def update_zone(zone, restart=True):
    result = R"""$TTL    1
@       IN      SOA     {0}. localhost. (1 1 1 1 1)
@       IN      NS      localhost.
@       IN      A       127.0.0.1
@       IN      AAAA    ::1
*       IN      A       127.0.0.1
*       IN      AAAA    ::1
""".format(zone)
    for record, values in txt_records.get(zone, {}).items():
        for value in values:
            result += '{0} IN TXT {1}\n'.format(record if record else '@', value)
    log('Updating zone {0}'.format(zone), result.split('\n'))
    with open(os.path.join(ZONES_PATH, zone), "wb") as f:
        f.write(result.encode('utf-8'))
    if restart:
        execute('Restarting BIND', ['service', 'bind9', 'restart'])


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


@app.route('/dns/<string:record>', methods=['PUT', 'DELETE'])
def dns_challenge(record):
    i = record.rfind('.')
    j = record.rfind('.', 0, i - 1)
    if i >= 0 and j >= 0:
        zone = record[j + 1:]
        record = record[:j]
    elif i >= 0:
        zone = record
        record = ''
    else:
        return 'cannot parse record', 400
    if zone not in zones:
        return 'unknown zone "{0}"; must be one of {1}'.format(zone, ', '.join(zones)), 404
    if request.method == 'PUT':
        if zone not in txt_records:
            txt_records[zone] = {}
        values = request.get_json(force=True)
        log('Adding TXT records for zone {0}, record {1}'.format(zone, record), values)
        txt_records[zone][record] = values
    else:
        if zone not in txt_records or record not in txt_records[zone]:
            return 'not found', 404
        log('Removing TXT records for zone {0}, record {1}'.format(zone, record))
        del txt_records[zone][record]
    update_zone(zone)
    return 'ok'


tls_alpn_server = ALPNChallengeServer(port=5001, log_callback=log)


@app.route('/tls-alpn/<string:domain>', methods=['PUT', 'DELETE'])
def tls_alpn_challenge(domain):
    if request.method == 'PUT':
        log('Adding TLS ALPN challenge for domain {0}'.format(domain))
        der_value = b"DER:0420" + codecs.encode(base64.standard_b64decode(request.data), 'hex')
        # Create private key
        key = crypto.PKey()
        key.generate_key(crypto.TYPE_RSA, 2048)
        # Create self-signed certificates
        acme_extension = crypto.X509Extension(b"1.3.6.1.5.5.7.1.30.1", critical=True, value=der_value)
        cert_normal = gen_ss_cert(key, [domain], [])
        cert_challenge = gen_ss_cert(key, [domain], extensions=[acme_extension])
        # Start/modify TLS-ALPN-01 challenge server
        tls_alpn_server.add(domain, key, cert_normal, cert_challenge)
    else:
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


@app.route('/root-certificate')
def get_root_certificate():
    with open(os.path.join(PEBBLE_PATH, 'test', 'certs', 'pebble.minica.pem'), 'rt') as f:
        return f.read()


def setup_zones():
    for zone in zones:
        update_zone(zone, restart=False)
    execute('Starting BIND', ['service', 'bind9', 'start'])


if __name__ == "__main__":
    setup_zones()
    app.run(debug=False, host='0.0.0.0', port=int(os.environ.get('CONTROLLER_PORT', 5000)))
