FROM golang:1.26-alpine AS build

WORKDIR /src
COPY go.mod ./
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 go build -trimpath -ldflags='-s -w' -o /out/energytool-api ./cmd/api

FROM alpine:3.22

RUN addgroup -S app && adduser -S -G app app
WORKDIR /app
COPY --from=build /out/energytool-api /app/energytool-api
RUN mkdir -p /app/var && chown -R app:app /app
USER app
ENV BACKEND_ADDR=:8080 BACKEND_STORE_PATH=/app/var/sessions.json
EXPOSE 8080
ENTRYPOINT ["/app/energytool-api"]