import os
import tempfile
import unittest
from datetime import datetime

from database import EmailDatabase
from filters import EmailFilter
from models import EmailMessage, FilterRule
from supplier_config import SupplierConfigCreate, SupplierConfigRepository


class EmailFilterTest(unittest.TestCase):
    def test_configured_supplier_condition_matches_only_supplier_email(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db = EmailDatabase(os.path.join(tmpdir, "mail_listener.db"))
            supplier_repository = SupplierConfigRepository(db)
            supplier_repository.create(SupplierConfigCreate(
                name="Supplier A",
                email="noc@supplier.example.com",
                can_reply_directly=True,
                cutover_extract_prompt="extract fields",
            ))

            email_filter = EmailFilter(supplier_repository)
            email_filter.add_rule(FilterRule(
                name="供应商配置邮箱邮件",
                conditions={"sender": {"type": "configured_supplier"}},
                action="api_forward",
            ))
            supplier_email = EmailMessage(
                uid=1,
                subject="cutover",
                sender="NOC@SUPPLIER.EXAMPLE.COM",
                recipients=["noc@example.com"],
                content="body",
                received_date=datetime.now(),
            )
            other_email = supplier_email.model_copy(update={
                "uid": 2,
                "sender": "other@example.com",
            })

            self.assertEqual(len(email_filter.filter_email(supplier_email)), 1)
            self.assertEqual(email_filter.filter_email(other_email), [])


if __name__ == "__main__":
    unittest.main()
