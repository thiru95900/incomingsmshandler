import unittest
import uuid
from datetime import datetime

from sm_models.account import IncomingConfig, Account
from sm_models.inbound_numbers import InboundNumber

from utils.database import session


class TestFactory(unittest.TestCase):

    def setUp(self):
        super(TestFactory, self).setUp()
        self.account_id = self.create_account()
        self.short_code = self.add_inbound_number_details()
        self.incoming_config_id = self.add_incoming_config(self.account_id)

    def tearDown(self):
        super(TestFactory, self).tearDown()
        session.rollback()
        session.remove()

    @staticmethod
    def create_account():
        params = dict(id=123456789, company_name='SMS_Magic', contact_name='PK',
                      phone_number=8390886493,
                      email_id='cicd1@screen-magic.com', api_key=uuid.uuid4(),
                      created_on=datetime.now())
        obj = Account(**params)
        session.add(obj)
        session.flush()
        return obj.id

    @staticmethod
    def add_inbound_number_details():
        inbound_number_params = dict(id=123456789, short_code=787878123,
                                     country_id=80,
                                     incoming_provider_id=5, is_mms=0,
                                     inbound_number_type=1)
        obj = InboundNumber(**inbound_number_params)
        session.add(obj)
        session.flush()
        return obj.short_code

    @staticmethod
    def add_incoming_config(account_id):
        incoming_config_params = dict(id=123456789, account_id=account_id,
                                      short_code=787878123, push_to_sf=1,
                                      country_id=80)
        incoming_config_obj = IncomingConfig(**incoming_config_params)
        session.add(incoming_config_obj)
        session.flush()
        return incoming_config_obj.id
