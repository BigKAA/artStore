#!/bin/bash
# ArtStore Development Environment Helper

COMPOSE_FILES="-f docker-compose.infrastructure.yml -f docker-compose.backend.yml -f docker-compose.dev.yml"

case "$1" in
  up)
    docker-compose $COMPOSE_FILES up --build "${@:2}"
    ;;
  down)
    docker-compose $COMPOSE_FILES down "${@:2}"
    ;;
  logs)
    docker-compose $COMPOSE_FILES logs -f "${@:2}"
    ;;
  restart)
    docker-compose $COMPOSE_FILES restart "${@:2}"
    ;;
  clean)
    docker-compose $COMPOSE_FILES down -v
    ;;
  *)
    echo "ArtStore Development Helper"
    echo "Usage: $0 {up|down|logs|restart|clean} [options]"
    echo ""
    echo "Commands:"
    echo "  up       - Start all services (with --build)"
    echo "  down     - Stop all services"
    echo "  logs     - View logs (specify service name)"
    echo "  restart  - Restart services"
    echo "  clean    - Stop and remove all volumes"
    echo ""
    echo "Examples:"
    echo "  $0 up -d              # Start in background"
    echo "  $0 logs admin-module  # View admin module logs"
    echo "  $0 restart redis      # Restart Redis"
    exit 1
    ;;
esac
