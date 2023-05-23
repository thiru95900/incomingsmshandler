from src.functionality.incoming_sms_handler import IncomingSMSHandler
from src.models.incoming_sms import *
from src.utils.config_loggers import log, log_json
from src.utils.constants import MEXICO_INVALID_PREFIX, MEXICO_VALID_PREFIX


class IncomingWhatsappHandler(IncomingSMSHandler):
    """
    Class to handle whatsapp incoming messages we are overriding the base
    IncomingSMSHandler class to use all its functionality except keyword routing
    """

    def __init__(self, params):
        super(IncomingWhatsappHandler, self).__init__(params)
        self._handle_mexico_number(params)

    def _handle_shared_number(self):
        """
        If mobile number has sent some other keyword which was not set prior
        then update the keyword for the given mobile number find the keyword
        from last messages sent from that mobile number
        """
        if not is_shared_number(self.inbound_number_info):
            return
        self.keyword, self.sub_keyword = db_model.get_keyword_whatsapp_mapping(
            self.shortcode, self.mobile_number)

        log_json.debug(f"Inbound number: {self.shortcode} is shared number. "
                       f"keyword = {self.keyword} and sub_keyword = "
                       f"{self.sub_keyword}")

        message = self.message.lower().split()
        if len(message) == 2 and message[-1] != self.sub_keyword:
            account_config_details = db_model.get_incoming_config_by_shortcode(
                self.shortcode, self.message)
            if account_config_details:
                log.info(f"Account config details found after mapping whatsapp "
                         f"keyword: {account_config_details}")
                self.keyword, self.sub_keyword = account_config_details.get(
                    'keyword').split()
                # Insert a new record in whatsapp mapping
                params = {
                    "shortCode": self.shortcode,
                    "mobileNumber": self.mobile_number,
                    "keyword": self.keyword,
                    "subKeyword": self.sub_keyword
                }
                db_model.insert_keyword_whatsapp_mapping(**params)
                log.info("whatsapp mapping table updated")

        self.keyword = f"{self.keyword} {self.sub_keyword}"
        self.params['keyword'] = self.keyword

    def _handle_mexico_number(self, params):
        """
        We are handling this issue - SMRO-23542
        Reference - https://faq.whatsapp.com/1294841057948784
        """
        mobile = params['mobilenumber']
        log.info(f'Inside _handle_mexico_number with mobile: {mobile}')
        if mobile.startswith(MEXICO_INVALID_PREFIX) and len(mobile) == 13:
            log.info(f'Found mexico wrongly prefixed number: {mobile}')
            mobile = f'{MEXICO_VALID_PREFIX}{mobile[3:]}'
            log.info(f'Correct mexico prefixed number: {mobile}')
            self.mobile_number = mobile
            self.params['mobilenumber'] = mobile


if __name__ == '__main__':
    data = {
        "mobilenumber": "9922000602",
        "providerId": 1,
        "messageId": 111,
        "message": "SMS magic Beatles" * 10,
        "shortCode": "14242387011",
        "totalParts": 2
    }
    IncomingWhatsappHandler(data).process()
