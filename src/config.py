#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from pathlib import Path

from dotenv import load_dotenv

curr_dir = os.path.dirname(__file__) or '.'
env_path = f'{curr_dir}/../env/{os.environ.get("ENVIRONMENT")}.env'
load_dotenv(dotenv_path=Path(env_path))


def get_worker_config(worker):
    return {
        'worker_name': os.environ.get(f'{worker}_TASK_NAME'),
        'task_module': os.environ.get(f'{worker}_TASK_MODULE'),
        'exchange': os.environ.get(f'{worker}_EXCHANGE'),
        'routing_key': os.environ.get(f'{worker}_ROUTE')
    }


APP_NAME = 'IncomingSMSHandler'

# Redis Configurations
SERVICE_REDIS_CLUSTER_HOST = os.environ.get("SERVICE_REDIS_CLUSTER_HOST")
SERVICE_REDIS_CLUSTER_PORT = os.environ.get("SERVICE_REDIS_CLUSTER_PORT")

SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
SQLALCHEMY_ECHO = False
SQLALCHEMY_POOL_CYCLE = 3600
SQLALCHEMY_CONVERT_UNICODE = True

BROKER_URL = os.environ.get('CELERY_BROKER_URL')

CELERY_CONFIG = dict(
    task_serializer=os.environ.get('CELERY_TASK_SERIALIZER'),
    result_serializer=os.environ.get('CELERY_RESULT_SERIALIZER'),
    task_acks_late=os.environ.get('CELERY_ACKS_LATE'),
    accept_content=[os.environ.get('CELERY_ACCEPT_CONTENT')],
    result_backend=os.environ.get("CELERY_CONFIG_RESULT_BACKEND")
)

attach_media_url = os.environ.get('ATTACH_MEDIA_URL', '')
attach_media_url_bandwidth = os.environ.get('ATTACH_MEDIA_URL_BANDWIDTH',
                                            attach_media_url)

DEFAULT_LOGGER_NAME = os.environ.get('LOGGER_NAME', 'incoming_sms_worker')

JSON_LOGGER_NAME = "json_logger"
LOG_LEVEL = os.environ.get('LOG_LEVEL', 'DEBUG')
LOG_FORMAT = '[%(task_id)s] [%(asctime)s] [%(levelname)s] ' \
             '[%(filename)s:%(lineno)d]: %(message)s'

# Feature flag for Multichannel Metering
METERING = os.environ.get('METERING', False)

JSON_LOG_FILE_PATH = os.environ.get('JSON_LOG_FILE_PATH')

INTERVAL_QUERY = "select id from incoming_sms_parts where createdOn > " \
                 "now() - interval 1 day limit 1;"
