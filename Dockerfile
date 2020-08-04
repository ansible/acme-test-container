FROM golang:1.13-stretch as builder
# Install pebble
ARG PEBBLE_REMOTE=
ARG PEBBLE_CHECKOUT="05f79ba495ab6a27cbbc32e20b44afac52eb9914"
ENV GOPATH=/go
RUN go get -v -u github.com/letsencrypt/pebble/... && \
    cd /go/src/github.com/letsencrypt/pebble && \
    if [ "${PEBBLE_REMOTE}" != "" ]; then \
      git remote add other ${PEBBLE_REMOTE} && \
      git fetch other && \
      git checkout -b other-${PEBBLE_CHECKOUT} --track other/${PEBBLE_CHECKOUT}; \
    else \
      git checkout ${PEBBLE_CHECKOUT}; \
    fi && \
    go install ./...

FROM python:3.6-slim-stretch
# Install software
ADD requirements.txt /root/
RUN pip3 install -r /root/requirements.txt
# Install pebble
COPY --from=builder /go/bin /go/bin
COPY --from=builder /go/pkg /go/pkg
COPY --from=builder /go/src/github.com/letsencrypt/pebble/test /go/src/github.com/letsencrypt/pebble/test
# Setup controller.py and run.sh
ADD run.sh controller.py dns_server.py acme_tlsalpn.py ocsp.py create-pebble-config.py LICENSE LICENSE-acme README.md /root/
EXPOSE 5000 14000
CMD [ "/bin/sh", "-c", "/root/run.sh" ]
