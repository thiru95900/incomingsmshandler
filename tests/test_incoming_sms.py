import unittest

from functionality.incoming_sms_handler import IncomingSMSHandler
from tests.test_factory import TestFactory

mms_url = "https://upload.wikimedia.org/wikipedia/commons/thumb/c/cf/" \
          "Johannes_Leendert_Scherpenisse%2C_Afb_A00771000799.jpg/" \
          "800px-Johannes_Leendert_Scherpenisse%2C_Afb_A00771000799.jpg"


class TestIncomingSMS(TestFactory):
    def setUp(self):
        pass

    def test_incoming_sms(self):
        data = {"totalParts": 3, "mobilenumber": "9922000602",
                "referenceId": 890, "partOrderNumber": 3, "isMultiPart": False,
                "providerId": 1, "messageId": 666, "message": "BKURL",
                "shortCode": "14242387011",
                # "mms_urls": [mms_url]
                }

        with IncomingSMSHandler(data) as hobj:
            hobj.process()
            print(hobj.params)


if __name__ == '__main__':
    suite = unittest.TestLoader().loadTestsFromTestCase(TestIncomingSMS)
    unittest.TextTestRunner(verbosity=2).run(suite)
