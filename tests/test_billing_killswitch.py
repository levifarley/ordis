import pytest
import time
from backend.billing_killswitch import BillingKillswitch
from backend.config import settings

def test_prompt_character_limit_exceeded():
    ks = BillingKillswitch()
    long_prompt = "a" * (settings.PROMPT_CHARACTER_LIMIT + 1)
    is_valid, msg = ks.validate_request(long_prompt, user_id="test_user_1")
    assert is_valid is False
    assert "maximum character boundary" in msg

def test_valid_prompt():
    ks = BillingKillswitch()
    is_valid, msg = ks.validate_request("What is Excalibur?", user_id="test_user_2")
    assert is_valid is True
    assert msg == ""

def test_cooldown_throttling():
    ks = BillingKillswitch()
    # First request succeeds
    valid1, _ = ks.validate_request("First prompt", user_id="test_user_cooldown")
    assert valid1 is True

    # Immediate second request fails due to cooldown
    valid2, msg2 = ks.validate_request("Second prompt", user_id="test_user_cooldown")
    assert valid2 is False
    assert "cooldown active" in msg2.lower()

def test_daily_quota_limit():
    ks = BillingKillswitch()
    user_id = "quota_test_user"

    # Simulate hitting daily quota cap
    ks.daily_counts[user_id] = (settings.MAX_DAILY_QUERIES, time.time())
    ks.last_request_time[user_id] = time.time() - 60  # Past cooldown

    valid, msg = ks.validate_request("Test prompt", user_id=user_id)
    assert valid is False
    assert "daily query quota cap" in msg.lower()

def test_circuit_breaker_tripping_and_reset():
    ks = BillingKillswitch()
    assert ks.is_circuit_open() is False

    # Simulate 3 consecutive cloud failures
    ks.record_cloud_failure()
    ks.record_cloud_failure()
    ks.record_cloud_failure()

    assert ks.is_circuit_open() is True

    # Reset circuit breaker
    ks.reset_circuit_breaker()
    assert ks.is_circuit_open() is False

def test_quota_status_structure():
    ks = BillingKillswitch()
    status = ks.get_quota_status("test_status_user")
    assert "daily_queries_used" in status
    assert "daily_quota_limit" in status
    assert "queries_remaining" in status
    assert "circuit_breaker_open" in status
