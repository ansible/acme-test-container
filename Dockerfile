FROM golang:1.12-stretch as builder
# Install pebble
ARG PEBBLE_CHECKOUT="c65a2f3c2be48868db01363f32d1d99c77281946"
ENV GOPATH=/go
RUN go get -u github.com/letsencrypt/pebble/... && \
    cd /go/src/github.com/letsencrypt/pebble && \
    git checkout ${PEBBLE_CHECKOUT} && \
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
ADD run.sh controller.py dns_server.py acme_tlsalpn.py create-pebble-config.py LICENSE LICENSE-acme README.md /root/
EXPOSE 5000 6000 14000
CMD [ "/bin/sh", "-c", "/root/run.sh" ]
