import unittest
from pii_masker.model import PIIMasker, MaskResult, EntityMatch

class TestPIIMaskerEngine(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.masker = PIIMasker()

    def test_ssn_masking(self):
        text = "User SSN is 123-45-6789."
        masked, pii_dict = self.masker.mask_pii(text)
        self.assertIn("[SSN]", masked)
        self.assertNotIn("123-45-6789", masked)
        self.assertIn("SSN", pii_dict)

    def test_email_and_phone_masking(self):
        text = "Contact user at john.doe@example.com or call +1-555-0199."
        res: MaskResult = self.masker.analyze_and_mask(text)
        self.assertIn("[EMAIL]", res.masked_text)
        self.assertIn("[PHONE_NUM]", res.masked_text)
        self.assertEqual(len(res.entities), 2)

    def test_custom_mask_format(self):
        text = "Secret credit card 4532-1234-5678-9012."
        masked, _ = self.masker.mask_pii(text, mask_format="[REDACTED_{TYPE}]")
        self.assertIn("[REDACTED_CREDIT_CARD]", masked)

    def test_empty_string(self):
        res = self.masker.analyze_and_mask("")
        self.assertEqual(res.masked_text, "")
        self.assertEqual(len(res.entities), 0)

if __name__ == "__main__":
    unittest.main()
