import unittest
import sys
import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

# Для единообразия с существующими тестами добавляем в sys.path каталог 'uk_management_bot'
sys.path.append(os.path.join(os.path.dirname(__file__), 'uk_management_bot'))

from database.session import Base  # noqa: E402
from database.models.user import User  # noqa: E402
from database.models.shift import Shift  # noqa: E402
from services.shift_service import ShiftService  # noqa: E402


engine = create_engine("sqlite:///:memory:", echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class TestShiftService(unittest.TestCase):
    def setUp(self):
        Base.metadata.create_all(bind=engine)
        self.db = SessionLocal()
        self.executor = User(telegram_id=1001, role="executor", status="approved", language="ru")
        self.manager = User(telegram_id=2002, role="manager", status="approved", language="ru")
        self.applicant = User(telegram_id=3003, role="applicant", status="approved", language="ru")
        self.db.add_all([self.executor, self.manager, self.applicant])
        self.db.commit()
        self.service = ShiftService(self.db)

    def tearDown(self):
        self.db.close()
        Base.metadata.drop_all(bind=engine)

    def test_start_shift_success(self):
        res = self.service.start_shift(self.executor.telegram_id)
        self.assertTrue(res["success"])  # noqa
        active = self.service.get_active_shift(self.executor.telegram_id)
        self.assertIsNotNone(active)

    def test_start_shift_twice_fails(self):
        self.service.start_shift(self.executor.telegram_id)
        res = self.service.start_shift(self.executor.telegram_id)
        self.assertFalse(res["success"])  # noqa

    def test_start_shift_applicant_denied(self):
        res = self.service.start_shift(self.applicant.telegram_id)
        self.assertFalse(res["success"])  # noqa

    def test_end_shift_success(self):
        self.service.start_shift(self.executor.telegram_id)
        res = self.service.end_shift(self.executor.telegram_id)
        self.assertTrue(res["success"])  # noqa
        active = self.service.get_active_shift(self.executor.telegram_id)
        self.assertIsNone(active)

    def test_end_shift_without_active(self):
        res = self.service.end_shift(self.executor.telegram_id)
        self.assertFalse(res["success"])  # noqa

    def test_force_end_shift_by_manager(self):
        self.service.start_shift(self.executor.telegram_id)
        res = self.service.force_end_shift(self.manager.telegram_id, self.executor.telegram_id)
        self.assertTrue(res["success"])  # noqa
        self.assertIsNone(self.service.get_active_shift(self.executor.telegram_id))

    def test_force_end_shift_denied(self):
        self.service.start_shift(self.executor.telegram_id)
        res = self.service.force_end_shift(self.executor.telegram_id, self.executor.telegram_id)
        self.assertFalse(res["success"])  # noqa

    def test_list_shifts_and_stats(self):
        self.service.start_shift(self.executor.telegram_id)
        self.service.end_shift(self.executor.telegram_id)
        shifts = self.service.list_shifts(telegram_id=self.executor.telegram_id)
        self.assertGreaterEqual(len(shifts), 1)
        stats = self.service.get_shift_stats(telegram_id=self.executor.telegram_id)
        self.assertGreaterEqual(stats.get("total_shifts", 0), 1)


if __name__ == "__main__":
    unittest.main()


