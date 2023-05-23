import json
from time import time

from src.functionality.incoming_sms_handler import IncomingSMSHandler
from src.functionality.incoming_whatsapp_handler import IncomingWhatsappHandler
from src.models.database import Model
from src.utils.celery_app import app
from src.utils.config_loggers import log, log_json
from src.utils.constants import TASK_MODULE, SMS_TASK_NAME, WA_TASK_NAME, \
    INCOMING_MULTICHANNEL, INCOMING_SINGLE, MULTI_CHANNEL_TASK_MODULE, \
    CELERY_TASK_STATUS_FAILED
from src.utils.helper import insensitive_data, masked_data

OPTIONS = {'bind': True, 'max_retries': 2}


@app.task(name=SMS_TASK_NAME, task_module=TASK_MODULE, **OPTIONS)
def handle_incoming_sms(self, data):
    log.info('Inside handle_incoming_sms task')
    status, exception = handle_incoming(data, clazz=IncomingSMSHandler,
                                        channel=INCOMING_SINGLE)
    if not status:
        self.retry(countdown=30, exc=exception)
    return True


@app.task(name=WA_TASK_NAME, task_module=MULTI_CHANNEL_TASK_MODULE, **OPTIONS)
def handle_incoming_whatsapp(self, data):
    log.info('Inside handle_incoming_whatsapp task')
    status, exception = handle_incoming(data, clazz=IncomingWhatsappHandler,
                                        channel=INCOMING_MULTICHANNEL)
    if not status:
        self.retry(countdown=30, exc=exception)
    return True


def handle_incoming(data, clazz=None, channel=None):
    ts = time()
    payload = {}
    try:
        payload = data if isinstance(data, dict) else json.loads(data)
        log.info(f'Task received: {insensitive_data(payload)}')
        log_json.info(f'Payload for incoming sms:{masked_data(payload)}')
        clazz(payload).process()
    except (ValueError, KeyError) as e:
        log.exception(f'Error for task {insensitive_data(payload)}: {e}')
        log_json.exception(f'Unable to process request as exception '
                           f'occurred while processing incoming sms for '
                           f'payload: {masked_data(payload)}.',
                           extra={'error': str(e), 'channel': channel})
        Model.update_celery_task(payload.get('entry_id'),
                                 status=CELERY_TASK_STATUS_FAILED,
                                 error=str(e))
    except Exception as e:
        log.exception(f'Error for task {insensitive_data(payload)}: {e}')
        log_json.exception(f'Exception occurred while incoming sms '
                           f'processing for payload:{masked_data(payload)}'
                           f'; Retrying the process...',
                           extra={'error': str(e), 'channel': channel})

        return False, e

    log.info(f'Task succeeded in {(time() - ts):2.4f}s\n')
    return True, None


if __name__ == '__main__':
    _data = {
        'mobilenumber': '9922000602',
        'providerId': 1,
        'messageId': 111,
        'message': 'Beatles',
        'shortCode': '14242387011'
    }
    handle_incoming_sms(json.dumps(_data))
