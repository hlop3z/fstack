# Static, dependency-free build -> minimal scratch image.
FROM golang:1.23-alpine AS build
WORKDIR /src
COPY go.mod ./
RUN go mod download
COPY *.go ./
RUN CGO_ENABLED=0 GOOS=linux go build -trimpath -ldflags="-s -w" -o /zk .

FROM scratch
# CA certs so `zk token` can talk to an HTTPS issuer (prod Zitadel).
COPY --from=build /etc/ssl/certs/ca-certificates.crt /etc/ssl/certs/
COPY --from=build /zk /zk
ENTRYPOINT ["/zk"]
