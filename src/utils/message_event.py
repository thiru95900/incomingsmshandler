#!/usr/bin/python
# -*- coding: utf-8 -*-

"""
Provides method to post updates to conversation worker.
We need to post updates about messages coming from Converse Desk to
Conversation worker for further processing which includes:
    1. Mapping message id to conversation id
    2. Sending updates to user browsers
"""
from src.config import get_worker_config
from src.utils.celery_app import app
from src.utils.config_loggers import log
from src.utils.constants import CHANNEL_CONVERSE_DESK

__author__ = "Yashpal Meena <yashpal.meena@screen-magic.com>"
__copyright__ = "Copyright 2019 Screen Magic Mobile Pvt Ltd"


class MessageEvent:
    """Utility class for sending updates to conversation worker."""

    def __init__(self):
        log.debug("In the constructor of MessageEvent")
        self.app = app
        self.config = get_worker_config(CHANNEL_CONVERSE_DESK)
        self.log = log

    def in_event(self, message_id, subscription_payload=None, bot_status=False):
        self.__post(message_id,
                    event='IN', subscription_payload=subscription_payload,
                    bot_status=bot_status)

    def __post(self, message_id, event=None, subscription_payload=None,
               bot_status=False):
        """
        This method will post updates to conversation worker in terms of
        message id (that means record has been saved in db) and direction of
        such message. Here it will be 'OUT' direction. Similarly, there will
        be such task in incoming handler which will be sending such updates i.e.
        message id and direction - 'IN'
        of Converse Desk messages.
        :param message_id: Saved message primary id
        :return:
        """
        # TODO :Need EventFactory design pattern here.
        self.log.info(f"Inside post func with message id: {message_id}")
        try:
            _id = self.app.send_task(
                self.config.get('worker_name'),
                args=[event, message_id, None, subscription_payload,
                      bot_status],
                exchange=self.config.get('exchange'),
                routing_key=self.config.get('routing_key')
            )
            self.log.info("Conversation task[id :{0}] posted".format(_id))
        except Exception as e:
            self.log.exception(f"Can not post message task. {str(e)}")
