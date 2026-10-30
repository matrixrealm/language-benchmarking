FROM golang:1.25.0 AS build
WORKDIR /src
COPY go.mod main.go ./
RUN CGO_ENABLED=0 go build -trimpath -o /service .
FROM debian:bookworm-slim
COPY --from=build /service /service
CMD ["/service"]
