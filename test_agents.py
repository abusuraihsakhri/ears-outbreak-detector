"""Tests for the EARS Outbreak Detector agents module."""

import unittest
import warnings

from agents.models import (
    SystemTaskPayload,
    ConsensusDossier,
    AgentAlert,
    UrgencyLevel,
    SystemIntegrityStatus,
)
from agents.base import (
    PHIGuard,
    SecurityException,
    AuditLogger,
    AuditTrail,
    assert_no_phi,
)
from agents.supervisor import SystemSupervisor


class TestSystemTaskPayload(unittest.TestCase):
    def test_create_minimal_payload(self):
        payload = SystemTaskPayload(
            task_id="TASK-001",
            target_identifier="TARGET-01",
            primary_metric=15.0,
        )
        self.assertEqual(payload.task_id, "TASK-001")
        self.assertEqual(payload.target_identifier, "TARGET-01")
        self.assertEqual(payload.primary_metric, 15.0)
        self.assertEqual(payload.secondary_metric, 0.0)
        self.assertEqual(payload.status_descriptor, "NOMINAL")
        self.assertFalse(payload.is_critical_flag)

    def test_create_full_payload(self):
        payload = SystemTaskPayload(
            task_id="TASK-002",
            target_identifier="SPECIMEN-123",
            primary_metric=30.0,
            secondary_metric=15.0,
            status_descriptor="DISCORDANT",
            is_critical_flag=True,
        )
        self.assertEqual(payload.primary_metric, 30.0)
        self.assertTrue(payload.is_critical_flag)


class TestPHIGuard(unittest.TestCase):
    def test_clean_text_passes(self):
        PHIGuard.assert_no_phi("Normal clinical observation with no identifiers")

    def test_mrn_detected(self):
        with self.assertRaises(SecurityException):
            PHIGuard.assert_no_phi("Patient MRN-12345678 test")

    def test_ssn_detected(self):
        with self.assertRaises(SecurityException):
            PHIGuard.assert_no_phi("SSN: 123-45-6789")

    def test_phone_detected(self):
        with self.assertRaises(SecurityException):
            PHIGuard.assert_no_phi("Call 555-123-4567")

    def test_email_detected(self):
        with self.assertRaises(SecurityException):
            PHIGuard.assert_no_phi("Email: patient@example.com")

    def test_john_doe_detected(self):
        with self.assertRaises(SecurityException):
            PHIGuard.assert_no_phi("Patient John Doe admitted")

    def test_redact_phi(self):
        redacted = PHIGuard.redact_phi("Patient MRN-12345678 and SSN 123-45-6789")
        self.assertNotIn("12345678", redacted)
        self.assertNotIn("123-45-6789", redacted)
        self.assertIn("[REDACTED_IDENTIFIER]", redacted)

    def test_empty_text_passes(self):
        PHIGuard.assert_no_phi("")

    def test_none_text_passes(self):
        assert_no_phi(None)


class TestAuditTrail(unittest.TestCase):
    def test_log_creates_entry(self):
        trail = AuditTrail(secret_key="test-key")
        entry = trail.log("test_actor", "test_tier", "TEST_EVENT", {"key": "value"})
        self.assertIn("audit_id", entry)
        self.assertIn("current_hash", entry)
        self.assertEqual(len(trail.get_trail()), 1)

    def test_integrity_verified(self):
        trail = AuditTrail(secret_key="test-key")
        trail.log("actor1", "tier1", "EVENT1", {"a": 1})
        trail.log("actor2", "tier2", "EVENT2", {"b": 2})
        trail.log("actor3", "tier3", "EVENT3", {"c": 3})
        self.assertTrue(trail.verify_integrity())

    def test_chained_hashes(self):
        trail = AuditTrail(secret_key="test-key")
        trail.log("actor1", "tier1", "EVENT1", {"a": 1})
        trail.log("actor2", "tier2", "EVENT2", {"b": 2})
        logs = trail.get_trail()
        self.assertEqual(logs[1]["prev_hash"], logs[0]["current_hash"])

    def test_no_phi_in_audit_details(self):
        trail = AuditTrail(secret_key="test-key")
        with self.assertRaises(SecurityException):
            trail.log("actor", "tier", "EVENT", {"data": "MRN-12345678"})

    def test_random_key_when_no_secret(self):
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)
            trail = AuditTrail()
            entry = trail.log("actor", "tier", "EVENT", {"key": "value"})
            self.assertIn("current_hash", entry)


class TestSystemSupervisor(unittest.TestCase):
    def setUp(self):
        self.supervisor = SystemSupervisor(model_provider="mock")

    def test_process_task_returns_dossier(self):
        payload = SystemTaskPayload(
            task_id="TASK-TEST-001",
            target_identifier="TARGET-01",
            primary_metric=10.0,
            secondary_metric=5.0,
            status_descriptor="NOMINAL",
            is_critical_flag=False,
        )
        dossier = self.supervisor.process_task(payload)
        self.assertIsInstance(dossier, ConsensusDossier)
        self.assertEqual(dossier.task_id, "TASK-TEST-001")
        self.assertEqual(dossier.overall_urgency, UrgencyLevel.ROUTINE)
        self.assertEqual(dossier.integrity_status, SystemIntegrityStatus.VALIDATED)

    def test_critical_flag_triggers_critical_urgency(self):
        payload = SystemTaskPayload(
            task_id="TASK-CRIT-001",
            target_identifier="TARGET-01",
            primary_metric=10.0,
            secondary_metric=5.0,
            status_descriptor="NOMINAL",
            is_critical_flag=True,
        )
        dossier = self.supervisor.process_task(payload)
        self.assertEqual(dossier.overall_urgency, UrgencyLevel.CRITICAL_STAT)
        self.assertGreater(dossier.critical_alerts_count, 0)

    def test_high_primary_metric_triggers_elevated(self):
        payload = SystemTaskPayload(
            task_id="TASK-ELEV-001",
            target_identifier="TARGET-01",
            primary_metric=30.0,
            secondary_metric=5.0,
            status_descriptor="NOMINAL",
            is_critical_flag=False,
        )
        dossier = self.supervisor.process_task(payload)
        self.assertEqual(dossier.overall_urgency, UrgencyLevel.ELEVATED)

    def test_discordant_descriptor_triggers_alert(self):
        payload = SystemTaskPayload(
            task_id="TASK-DISC-001",
            target_identifier="TARGET-01",
            primary_metric=10.0,
            secondary_metric=5.0,
            status_descriptor="DISCORDANT_ANOMALY",
            is_critical_flag=False,
        )
        dossier = self.supervisor.process_task(payload)
        self.assertEqual(dossier.overall_urgency, UrgencyLevel.ELEVATED)

    def test_dossier_stored_in_registry(self):
        payload = SystemTaskPayload(
            task_id="TASK-REG-001",
            target_identifier="TARGET-01",
            primary_metric=10.0,
        )
        dossier = self.supervisor.process_task(payload)
        self.assertIn(dossier.dossier_id, self.supervisor.dossier_registry)

    def test_audit_hash_present(self):
        payload = SystemTaskPayload(
            task_id="TASK-AUDIT-001",
            target_identifier="TARGET-01",
            primary_metric=10.0,
        )
        dossier = self.supervisor.process_task(payload)
        self.assertTrue(len(dossier.audit_hash) > 0)

    def test_phi_in_task_id_raises(self):
        payload = SystemTaskPayload(
            task_id="MRN-12345678",
            target_identifier="TARGET-01",
            primary_metric=10.0,
        )
        with self.assertRaises(SecurityException):
            self.supervisor.process_task(payload)

    def test_query_supervisory_chat(self):
        result = self.supervisor.query_supervisory_chat("What is the status?")
        self.assertIsInstance(result, str)
        self.assertIn("Ears Outbreak Detector", result)


class TestAuditLogger(unittest.TestCase):
    def test_get_trail_returns_list(self):
        trail = AuditLogger.get_trail()
        self.assertIsInstance(trail, list)

    def test_verify_integrity_returns_bool(self):
        result = AuditLogger.verify_integrity()
        self.assertIsInstance(result, bool)


if __name__ == "__main__":
    unittest.main()
