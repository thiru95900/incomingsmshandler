# !/usr/bin/env python
# -*- coding: utf-8 -*-
import json

from celery import Celery

__author__ = "Yashpal Meena <yashpal.meena@screen-magic.com>"
__copyright__ = "Copyright 2022 Screen Magic Mobile Pvt Ltd"


def get_celery_app(app_name):
    _app = Celery(app_name, broker='amqp://guest:guest@localhost:5672//')
    _app.conf.update(
        task_serializer='json',
        result_serializer='json',
        task_acks_late='False',
        accept_content=['json'],
        worker_hijack_root_logger=True
    )
    return _app


app = get_celery_app('TestAPP')

payload = {
    "providerId": 1,
    "providerName": "aerial",
    "messageId": "982764345689122324151455589128273132",
    "mobilenumber": "919756120280",
    "shortCode": "19404613124",
    "message": "testingcrm1 what is converse app",
    "mms_urls": [],
    "duplicate_incoming_redis_key": "incoming_sms:3bf2efeebc010e9be8a31131a82a",
    "entry_id": 1
}
app.send_task(
    'incoming_sms_processor.handle_incoming_sms',
    task_id='1-62daa92d-6985708e24633ab7558c9ebb',
    args=[json.dumps(payload)],
    exchange='incoming_sms_processor',
    routing_key='incoming_sms_processor'
)
