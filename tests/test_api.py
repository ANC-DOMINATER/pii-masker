import io
import unittest
from fastapi.testclient import TestClient
from pii_masker.api.app import app

client = TestClient(app)

class TestFastAPIEndpoints(unittest.TestCase):
    def test_root_dashboard(self):
        response = client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("PII Masker", response.text)

    def test_health_endpoint(self):
        response = client.get("/api/v1/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("SSN", data["supported_entities"])

    def test_list_entities(self):
        response = client.get("/api/v1/entities")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("entities", data)

    def test_mask_endpoint(self):
        payload = {
            "text": "John Doe email is john@example.com and phone is 555-123-4567",
            "mask_format": "[{TYPE}]"
        }
        response = client.post("/api/v1/mask", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("[EMAIL]", data["masked_text"])
        self.assertIn("[PHONE_NUM]", data["masked_text"])
        self.assertIn("EMAIL", data["pii_dict"])

    def test_mask_batch_endpoint(self):
        payload = {
            "texts": [
                "SSN 123-45-6789",
                "Email test@org.com"
            ]
        }
        response = client.post("/api/v1/mask/batch", json=payload)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_processed"], 2)

    def test_mask_file_upload(self):
        file_content = b"Sample log file: User IP 192.168.1.100 SSN 999-88-7777"
        files = {"file": ("test.log", io.BytesIO(file_content), "text/plain")}
        response = client.post("/api/v1/mask/file", files=files)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["filename"], "test.log")
        self.assertIn("[SSN]", data["masked_text"])

if __name__ == "__main__":
    unittest.main()
