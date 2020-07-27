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

import datetime
import json
import os
import urllib
import traceback

from flask import Response

from cryptography import x509
from cryptography.x509 import ocsp
from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives import serialization


SAMPLE_REQUEST_CACHE = {}


def _get_sample_request_for_root(root, hash_algorithm, pebble_urlopen):
    '''
    Returns an OCSP sample request for this root, together with the intermediate certificate and its key.
    '''
    cache_key = (root, hash_algorithm.name)
    if cache_key in SAMPLE_REQUEST_CACHE:
        return SAMPLE_REQUEST_CACHE[cache_key]

    # Get hold of intermediate certificate with key
    intermediate = x509.load_pem_x509_certificate(
        pebble_urlopen("/intermediates/{0}".format(root)).read(),
        backend=default_backend())
    intermediate_key = serialization.load_pem_private_key(
        pebble_urlopen("/intermediate-keys/{0}".format(root)).read(),
        None,
        backend=default_backend())

    one_day = datetime.timedelta(1, 0, 0)
    builder = x509.CertificateBuilder()
    builder = builder.subject_name(intermediate.subject)
    builder = builder.issuer_name(intermediate.subject)
    builder = builder.not_valid_before(datetime.datetime.today() - one_day)
    builder = builder.not_valid_after(datetime.datetime.today() + one_day)
    builder = builder.serial_number(x509.random_serial_number())
    builder = builder.public_key(intermediate.public_key())
    certificate = builder.sign(
        private_key=intermediate_key,
        algorithm=hashes.SHA256(),
        backend=default_backend())

    req = ocsp.OCSPRequestBuilder()
    req = req.add_certificate(certificate, intermediate, hash_algorithm)
    req = req.build()

    result = req, intermediate, intermediate_key
    SAMPLE_REQUEST_CACHE[cache_key] = result
    return result


RECOVATION_REASONS = {
    1: x509.ReasonFlags.key_compromise,
    2: x509.ReasonFlags.ca_compromise,
    3: x509.ReasonFlags.affiliation_changed,
    4: x509.ReasonFlags.superseded,
    5: x509.ReasonFlags.cessation_of_operation,
    6: x509.ReasonFlags.certificate_hold,
    7: x509.ReasonFlags.privilege_withdrawn,
    8: x509.ReasonFlags.aa_compromise,
}


def _get_ocsp_response(data, pebble_urlopen, log):
    try:
        ocsp_request = ocsp.load_der_ocsp_request(data)
    except Exception:
        log('Error while decoding OCSP request')
        return ocsp.OCSPResponseBuilder.build_unsuccessful(
            ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

    log('OCSP request for certificate # {0}'.format(ocsp_request.serial_number))

    # Process possible extensions
    nonce = None
    for ext in ocsp_request.extensions:
        if isinstance(ext.value, x509.OCSPNonce):
            nonce = ext.value.nonce
            continue
        if ext.critical:
            return ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.MALFORMED_REQUEST)

    # Determine issuer
    root_count = int(os.environ.get('PEBBLE_ALTERNATE_ROOTS') or '0') + 1
    for root in range(root_count):
        req, intermediate, intermediate_key = _get_sample_request_for_root(
            root, ocsp_request.hash_algorithm, pebble_urlopen)
        if req.issuer_key_hash == ocsp_request.issuer_key_hash and req.issuer_name_hash == ocsp_request.issuer_name_hash:
            log('Identified intermediate certificate {0}'.format(intermediate.subject))
            break
        intermediate = None
        intermediate_key = None
    if intermediate is None or intermediate_key is None:
        log(ocsp_request.issuer_key_hash, ocsp_request.issuer_name_hash)
        log('Cannot identify intermediate certificate')
        return ocsp.OCSPResponseBuilder.build_unsuccessful(
            ocsp.OCSPResponseStatus.UNAUTHORIZED)

    serial_hex = hex(ocsp_request.serial_number)[2:]
    if len(serial_hex) % 2 == 1:
        serial_hex = '0' + serial_hex
    try:
        url = pebble_urlopen("/cert-status-by-serial/{0}".format(serial_hex))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log('Unknown certificate with # {0}'.format(ocsp_request.serial_number))
            return ocsp.OCSPResponseBuilder.build_unsuccessful(
                ocsp.OCSPResponseStatus.UNAUTHORIZED)
        raise

    data = json.loads(url.read())
    log('Pebble result on certificate:', json.dumps(data, sort_keys=True, indent=2))

    cert = x509.load_pem_x509_certificate(
        data['Certificate'].encode('utf-8'), backend=default_backend())

    now = datetime.datetime.now()
    if data['Status'] == 'Revoked':
        cert_status = ocsp.OCSPCertStatus.REVOKED
        revoked_at = data.get('RevokedAt')
        if revoked_at is not None:
            revoked_at = ' '.join(revoked_at.split(' ')[:2])  # remove time zones
            if '.' in revoked_at:
                revoked_at = revoked_at[:revoked_at.index('.')]  # remove milli- or nanoseconds
            revoked_at = datetime.datetime.strptime(revoked_at, '%Y-%m-%d %H:%M:%S')
        revocation_time = revoked_at,
        revocation_reason = RECOVATION_REASONS.get(data.get('Reason'), x509.ReasonFlags.unspecified)
    elif data['Status'] == 'Valid':
        cert_status = ocsp.OCSPCertStatus.GOOD
        revocation_time = None
        revocation_reason = None
    else:
        log('Unknown certificate status "{0}"'.format(data['Status']))
        return ocsp.OCSPResponseBuilder.build_unsuccessful(
            ocsp.OCSPResponseStatus.INTERNAL_ERROR)

    response = ocsp.OCSPResponseBuilder()
    response = response.add_response(
        cert=cert,
        issuer=intermediate,
        algorithm=ocsp_request.hash_algorithm,
        cert_status=cert_status,
        this_update=now,
        next_update=None,
        revocation_time=revocation_time,
        revocation_reason=revocation_reason)
    response = response.responder_id(
        ocsp.OCSPResponderEncoding.HASH,
        intermediate)
    if nonce is not None:
        response = response.add_extension(x509.OCSPNonce(nonce), False)
    return response.sign(intermediate_key, hashes.SHA256())


def get_ocsp_response(data, pebble_urlopen, log=lambda *args: print(args)):
    try:
        response = _get_ocsp_response(data, pebble_urlopen, log=log)
    except Exception as e:
        log('Error while processing OCSP request: {0}'.format(e), traceback.format_exc())
        response = ocsp.OCSPResponseBuilder.build_unsuccessful(
            ocsp.OCSPResponseStatus.INTERNAL_ERROR)
    return Response(
        response.public_bytes(serialization.Encoding.DER),
        mimetype='application/ocsp-response')
