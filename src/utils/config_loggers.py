#!/usr/bin/env python
# -*- coding: utf-8 -*-
import logging
import logging.config
import uuid

from celery import current_task
from celery.app.log import TaskFormatter
from celery.signals import after_setup_task_logger
from celery.utils.log import get_task_logger

from src import config
from src.utils.constants import COMPONENT, CONTEXT

__author__ = "Yashpal Meena <yashpal.meena@screen-magic.com>"
__copyright__ = "Copyright 2022 Screen Magic Mobile Pvt Ltd"

LOG_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        "json": {
            "format": '%(request_id)s %(asctime)s %(processName)s %(filename)s'
                      ' %(module)s %(funcName)s %(lineno)d %(levelname)s '
                      '%(component)s %(context)s %(account_id)s %(short_code)s'
                      ' %(message)s',
            "datefmt": "%Y-%m-%dT%H:%M:%S%z",
            "class": "pythonjsonlogger.jsonlogger.JsonFormatter"
        }
    },
    'handlers': {
        config.JSON_LOGGER_NAME: {
            'class': 'logging.handlers.WatchedFileHandler',
            'formatter': 'json',
            'level': 'DEBUG',
            'filename': config.JSON_LOG_FILE_PATH,
        }
    },
    'loggers': {
        config.JSON_LOGGER_NAME: {
            'handlers': [config.JSON_LOGGER_NAME],
            'level': 'DEBUG',
            'propagate': False
        }
    }
}

DISABLE_LOGGERS = [
    'amqp.connection.Connection.heartbeat_tick',
    'celery'
]


class JsonFilter(logging.Filter):
    def __init__(self):
        super(JsonFilter, self).__init__()

    def filter(self, record):
        record.context = CONTEXT
        record.component = COMPONENT
        if current_task and current_task.request:
            record.request_id = current_task.request.id
            record.account_id = current_task.request.kwargs.get('account_id')
            record.short_code = current_task.request.kwargs.get('short_code')
        else:
            record.request_id = str(uuid.uuid4())
            record.account_id = ''
            record.short_code = ''
        return True


@after_setup_task_logger.connect
def setup_task_logger(logger, *args, **kwargs):
    print(f'setup_task_logger: args{args}, kwargs: {kwargs}')
    for name in DISABLE_LOGGERS:
        _logger = logging.getLogger(name)
        _logger.propagate = False
    for handler in logger.handlers:
        handler.setFormatter(TaskFormatter(config.LOG_FORMAT))


log = get_task_logger(config.DEFAULT_LOGGER_NAME)
log.setLevel(config.LOG_LEVEL)
log.info(f'{config.DEFAULT_LOGGER_NAME} logger configured!')

logging.config.dictConfig(LOG_CONFIG)
log_json = logging.getLogger(config.JSON_LOGGER_NAME)
log_json.addFilter(JsonFilter())
