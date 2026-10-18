#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   ./deploy/setup-ssl.sh rag.example.com you@email.com
#
# Домен уже должен указывать A-записью на IP сервера.

DOMAIN="${1:?укажи домен, например rag.example.com}"
EMAIL="${2:?укажи email для Let's Encrypt}"

# 1) Временно оставляем только HTTP-сервер, если сертификатов ещё нет:
#    если nginx падает из-за отсутствующих ssl-файлов — используем bootstrap ниже.

echo "→ Стартуем nginx + api (если ещё не запущены)"
docker compose -f docker-compose.prod.yml up -d db redis api nginx

echo "→ Запрашиваем сертификат для ${DOMAIN}"
docker compose -f docker-compose.prod.yml run --rm --entrypoint certbot certbot certonly \
  --webroot \
  --webroot-path=/var/www/certbot \
  --email "${EMAIL}" \
  --agree-tos \
  --no-eff-email \
  -d "${DOMAIN}"

echo "→ Перезагружаем nginx"
docker compose -f docker-compose.prod.yml exec nginx nginx -s reload

echo "Готово: https://${DOMAIN}"