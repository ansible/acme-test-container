FROM golang:1.10-stretch as builder
# Install pebble
ARG PEBBLE_CHECKOUT="25448686e9b499e42380ddf965d8e23bd794378c"
ENV GOPATH=/go
RUN go get -u github.com/letsencrypt/pebble/... && \
    cd /go/src/github.com/letsencrypt/pebble && \
    git checkout ${PEBBLE_CHECKOUT} && \
    go install ./...

FROM debian:stretch-slim
# Install software
RUN apt-get update \
 && apt-get install -y bind9 python3 python3-pip \
 && apt-get clean all \
 && rm -rf /var/lib/apt/lists/*;
ADD requirements.txt /root/
RUN pip3 install -r /root/requirements.txt
# Setup bind9
ADD bind.conf /etc/bind/named.conf
RUN mkdir /etc/bind/zones
# Install pebble
COPY --from=builder /go/bin /go/bin
COPY --from=builder /go/pkg /go/pkg
COPY --from=builder /go/src/github.com/letsencrypt/pebble/test /go/src/github.com/letsencrypt/pebble/test
ADD pebble-config.json /go/src/github.com/letsencrypt/pebble/test/config/pebble-config.json
# Setup controller.py and run.sh
ADD run.sh controller.py acme_tlsalpn.py LICENSE LICENSE-acme README.md /root/
EXPOSE 5000 14000
CMD [ "/bin/sh", "-c", "/root/run.sh" ]
