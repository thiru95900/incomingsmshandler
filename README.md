----------------------------------
Project Setup
---------------------------------
Python 3.6

virtualenv -p python3.6 ~/virt/incoming_celery5
[we need to change virtualenv (incoming_celery5) to suitable name]

pip install -r requirements.txt



----------------------------------
Description
---------------------------------
After receiving incoming payload in "one_api" we are inserting payload in
celery_tasks and put payload (celery_tasks id ) in RQ This project is used to
further processing of incoming payload:

- create entry in incoming_sms table in database (smsmagic)
- sync incoming message to external crm i.e. SF, Zoho, etc..

payload in RQ (added by one_api project)
--------------------------------------------------------------------------

    ------------------------------------------------------------------------
    Payload in RQ
    ------------------------------------------------------------------------
    Task received: {
    'providerId': 26, 'providerName': 'aerial',
    'messageId': '98765434567889122324151455589817',
    'mobilenumber': '9189787654543', 'shortCode': '14879087654',
    'message':****', 'mms_urls': [],
    'duplicate_incoming_redis_key': 'incoming_smse57905bc96dd26c4d8ebf2c999a10c7e',
    'logger_key': '', "entry_id": "5008550xyz"
     }

-----------------------------------------
We process this payload and further create enrtry in celery_tasks to process it
to third party crm (SF<,zoho))
