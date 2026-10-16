"""Инициализация Sentry. Без SENTRY_DSN — no-op."""

from __future__ import annotations

import logging

import sentry_sdk
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from sentry_sdk.integrations.logging import LoggingIntegration
from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

from app.core.config import settings

logger = logging.getLogger(__name__)


def init_sentry() -> None:
    if not settings.sentry_dsn:
        logger.info("Sentry is disabled (SENTRY_DSN is empty)")
        return

    sentry_sdk.init(
        dsn=settings.sentry_dsn,
        environment=settings.environment,
        traces_sample_rate=0.1,
        integrations=[
            FastApiIntegration(),
            CeleryIntegration(),
            SqlalchemyIntegration(),
            LoggingIntegration(level=logging.INFO, event_level=logging.ERROR),
        ],
        # не отправлять тело запросов с возможными секретами по умолчанию
        send_default_pii=False,
    )
    logger.info("Sentry initialized (env=%s)", settings.environment)