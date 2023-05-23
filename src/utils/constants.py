TASK_MODULE = 'incoming_sms_processor'
MULTI_CHANNEL_TASK_MODULE = 'incoming_whatsapp_process'

MAIN_MODULE = 'incoming_sms_processor'

CHANNEL_SALESFORCE = 'PUSH_TO_SF'
CHANNEL_ZOHO = 'PUSH_TO_ZOHO'
CHANNEL_PUSH_TO_ZOHO = 'PUSH_TO_ZOHO'
CHANNEL_BULLHORN = 'PUSH_TO_BULLHORN'
CHANNEL_URL = 'PUSH_TO_URL'
CHANNEL_EMAIL = 'PUSH_TO_EMAIL'
CHANNEL_LIVE_CHAT = 'PUSH_TO_LIVECHAT'
CHANNEL_BOT = 'PUSH_TO_BOT'
CHANNEL_MOBILE = 'PUSH_NOTIFICATION'
CHANNEL_CONVERSE_DESK = 'CONVERSE_DESK_NOTIFICATION'
CHANNEL_SUBSCRIPTION = 'SUBSCRIPTION'
CHANNEL_AUTO_REPLY = 'BUSINESS_HOUR_AUTOREPLY'
CHANNEL_SALESFORCE_PUSH = 'SALESFORCE_PUSH'

EMAIL_FROM_ADDRESS = 'noreply@screen-magic.com'
PUSH_EMAIL_TEMPLATE_TYPE = 36
CC_ADDRESS = 'notifications@screen-magic.com'
IS_PUSH_ENABLED_ACCOUNT_TAG_FLAG_NAME = 'is_push_notification_enabled'

IS_CONVERSE_DESK_ENABLED_ACCOUNT_TAG_FLAG_NAME = 'is_converse_desk_enabled'

sender_id_type_map = {1: "longcode", 2: "shortcode", 3: "TFN"}
ACTIVE, DELETED = 0, 1
ENABLED, DISABLED = 1, 0

DUPLICATE_INCOMING_REDIS_EXPIRY = 'duplicate_incoming_expiry'
SYNC_CHANNEL_EVENTS_REQUEST_TYPE = 'push_multichannel_events'

SF_STORAGE = "SF"

COMPONENT = 'incoming_sms_handler'
CONTEXT = 'incoming_sms'
INCOMING_SINGLE = 'incoming_single'
INCOMING_MULTICHANNEL = 'incoming_multichannel'

CELERY_X_HEADER = 'x-request-id'

MASK_FILTER = [
    'message',
    'text',
    'original_message_body',
    'messageText',
    'body',
    'text',
    'attachments',
    'attachment',
    'mobilenumber'
]

DEFAULT_FALSE_FLAG, DEFAULT_TRUE_FLAG = 1, 0
CHILD_ACCOUNT_FLAG = 2
CUSTOMER_THRESHOLD_BAL_AMT = 0

CELERY_TASK_STATUS_STARTED = 'STARTED'
CELERY_TASK_STATUS_COMPLETED = 'COMPLETED'
CELERY_TASK_STATUS_FAILED = 'FAILED'

SMS_TASK_NAME = "incoming_sms_processor.handle_incoming_sms"
WA_TASK_NAME = "incoming_sms_processor.handle_incoming_whatsapp"

SCREEN_MAGIC_DOMAINS = {'sms-magic.com', 'txtbox.in'}

MEXICO_INVALID_PREFIX = "521"
MEXICO_VALID_PREFIX = "52"


class CHANNEL:
    SMS = 'sms'
    MMS = 'mms'
    WEB = 'web'
    WHATSAPP = 'whatsapp'
    LINE = 'line'
