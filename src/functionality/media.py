from urllib.parse import urlparse

import requests
from requests.adapters import HTTPAdapter
from retrying import retry
from sm_utils.utils import Singleton
from sm_utils.utils import function_logger

from src.config import attach_media_url, attach_media_url_bandwidth
from src.models.incoming_sms import get_apikey
from src.utils.config_loggers import log
from src.utils.constants import SCREEN_MAGIC_DOMAINS


class Request(object):
    __metaclass__ = Singleton

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({'content_type': 'application/json'})
        adapter = HTTPAdapter(pool_connections=2)
        self.session.mount('http', adapter)

    def post(self, url, payload):
        log.info('Inside function media.Request.post')
        response = self.session.post(url, json=payload)
        log.debug(f'media.Request.post response {response.__dict__}')
        response.raise_for_status()
        return response.json()


@retry(wait_random_min=1000, wait_random_max=5000, stop_max_attempt_number=3)
def _request(url, payload):
    return Request().post(url, payload)


# API for uploading attachments for provider 'Bandwidth' is different, because
# it needs account authentication.
def _get_upload_url(provider_name):
    if provider_name.lower() in ['bandwidth', 'bandwidthv2']:
        return attach_media_url_bandwidth

    return attach_media_url


def _upload(mms_url, api_key, provider_name):
    payload = dict(mms_url=mms_url, apikey=api_key, provider_name=provider_name)
    upload_url = _get_upload_url(provider_name)
    result = _request(upload_url, payload)
    if not result:
        log.error(f"Error in uploading MMS url to {attach_media_url}")
        raise ValueError("ERROR-MMS-URL-UPLOAD")
    else:
        log.info(f'_upload result: {result}')
    return result["mms_url"]


@function_logger(log)
def check_if_magic_s3_url(url=None):
    parse_url = urlparse(url)
    hostname = parse_url.hostname.lower() if parse_url else ''
    return any(hostname.endswith(item) for item in SCREEN_MAGIC_DOMAINS)


# Ideally, instead of calling app server's url, upload should be done here
# itself. For that to implement, s3 upload logic of 'attach_url' from
# smsMagicStories should be moved to sm-utils.
def upload_media(mms_urls, account_id, provider_name=None):
    log.info('Inside function upload_media function')
    api_key = get_apikey(account_id)
    uploaded_urls = []

    if not isinstance(mms_urls, list):
        mms_urls = [mms_urls]

    refined_list = [url for url in mms_urls if url]

    for url in refined_list:
        if check_if_magic_s3_url(url=url):
            _url = url
        else:
            _url = _upload(url, api_key, provider_name)

        if _url:
            uploaded_urls.append(_url)
    return uploaded_urls


if __name__ == "__main__":
    upload_media(["http://abc.com", "http://pqr.com"], 1)
