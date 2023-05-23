# !/usr/bin/env python
# -*- coding: utf-8 -*-

from celery import Celery

from src import config

__author__ = "Yashpal Meena <yashpal.meena@screen-magic.com>"
__copyright__ = "Copyright 2022 Screen Magic Mobile Pvt Ltd"


def get_celery_app(app_name):
    _app = Celery(app_name, broker=config.BROKER_URL)
    _app.conf.update(
        task_serializer='json',
        result_serializer='json',
        task_acks_late='False',
        accept_content=['json'],
        task_ignore_result=True,
        worker_hijack_root_logger=True
    )
    return _app


app = get_celery_app(config.APP_NAME)
