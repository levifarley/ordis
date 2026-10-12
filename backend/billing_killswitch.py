"""
===============================================================================
ORDIS Enterprise Cost Routing & Billing Killswitch Module
===============================================================================

Architectural Rationale:
------------------------
When operating in a hybrid deployment profile (Profile B: Cloud Enterprise), 
exposing public LLM endpoints (e.g., Google Gemini 1.5 Flash API) introduces 
unbounded cost risks from automated query abuse, context buffer overflow attacks,
or unexpected API rate spikes.

This module enforces multi-layered cost protection and circuit breaking:
1. Prompt Character Boundaries (250 char limit) to cap per-query token expenditure.
2. User Daily Quota Counters (300 queries/day) to prevent API credit exhaustion.
3. Cooldown Guards (10s inter-request delay) to mitigate automated spam vectors.
4. Dynamic Cost Circuit Breaker: Automatically trips if cloud API errors (429/503)
   exceed threshold, seamlessly routing subsequent traffic to zero-cost local Gemma.
"""

import time
import logging
from typing import Dict, Tuple
from backend.config import settings

logger = logging.getLogger("ordis.billing_killswitch")


class BillingKillswitch:
    """
    Enterprise Circuit Breaker & Cost Routing Safeguard.
    Manages daily query quotas, request cooldowns, and cloud-to-local model failover.
    """
    def __init__(self):
        self.daily_counts: Dict[str, Tuple[int, float]] = {}  # user_id -> (count, timestamp_day_start)
        self.last_request_time: Dict[str, float] = {}          # user_id -> timestamp
        self.cloud_error_count: int = 0
        self.circuit_open: bool = False
        self.circuit_tripped_at: float = 0.0
        self.circuit_cooldown_seconds: float = 300.0  # 5 minutes local fallback window

    def validate_request(self, prompt: str, user_id: str = "default") -> Tuple[bool, str]:
        """
        Validates request bounds (length, rate limit cooldown, daily quota).
        Returns (is_valid, error_message).
        """
        now = time.time()

        # 1. Prompt Character Limit Safeguard
        if len(prompt) > settings.PROMPT_CHARACTER_LIMIT:
            logger.warning(f"Cost Guardrail: Prompt length ({len(prompt)}) exceeds limit ({settings.PROMPT_CHARACTER_LIMIT}).")
            return False, f"Prompt exceeds maximum character boundary of {settings.PROMPT_CHARACTER_LIMIT} characters."

        # 2. Inter-Request Cooldown Safeguard
        last_time = self.last_request_time.get(user_id, 0.0)
        if now - last_time < settings.COOLDOWN_SECONDS:
            remaining = int(settings.COOLDOWN_SECONDS - (now - last_time))
            logger.info(f"Rate Guardrail: User {user_id} throttled. Cooldown remaining: {remaining}s.")
            return False, f"Rate limit cooldown active. Please wait {remaining} seconds before sending another message."

        # 3. Daily Quota Tracking & Enforcement
        count, day_start = self.daily_counts.get(user_id, (0, now))
        # Reset counter if 24 hours have elapsed
        if now - day_start >= 86400:
            count = 0
            day_start = now

        if count >= settings.MAX_DAILY_QUERIES:
            logger.warning(f"Quota Guardrail: User {user_id} exceeded daily query cap ({settings.MAX_DAILY_QUERIES}).")
            return False, f"Daily query quota cap of {settings.MAX_DAILY_QUERIES} queries reached. Resets in 24 hours."

        # Record valid request attempt
        self.daily_counts[user_id] = (count + 1, day_start)
        self.last_request_time[user_id] = now
        return True, ""

    def record_cloud_failure(self):
        """
        Records a cloud API error (e.g. 429 Rate Limit, 503 Over Capacity).
        Trips the cost circuit breaker if error threshold is exceeded.
        """
        self.cloud_error_count += 1
        logger.warning(f"Cloud API failure recorded. Current consecutive error count: {self.cloud_error_count}")
        if self.cloud_error_count >= 3 and not self.circuit_open:
            self.circuit_open = True
            self.circuit_tripped_at = time.time()
            logger.error("COST CIRCUIT BREAKER TRIPPED: Automatically routing all LLM inference to zero-cost Local Gemma Node.")

    def should_use_local_failover(self) -> bool:
        """
        Determines whether cloud routing should be bypassed in favor of local Gemma.
        Automatically resets the circuit breaker after cooldown period expires.
        """
        return self.is_circuit_open()

    def is_circuit_open(self) -> bool:
        """Checks if circuit breaker is currently open (forcing local failover)."""
        if self.circuit_open:
            if time.time() - self.circuit_tripped_at > self.circuit_cooldown_seconds:
                logger.info("Cost Circuit Breaker cooldown expired. Resetting to normal cloud/auto routing state.")
                self.reset_circuit_breaker()
                return False
            return True
        return False

    def reset_circuit_breaker(self):
        """Resets circuit breaker and cloud error tracking."""
        self.cloud_error_count = 0
        self.circuit_open = False
        self.circuit_tripped_at = 0.0

    def get_quota_status(self, user_id: str = "default") -> dict:
        """Returns current quota metrics for telemetry monitoring."""
        now = time.time()
        count, day_start = self.daily_counts.get(user_id, (0, now))
        if now - day_start >= 86400:
            count = 0
        return {
            "daily_queries_used": count,
            "daily_quota_limit": settings.MAX_DAILY_QUERIES,
            "queries_remaining": max(0, settings.MAX_DAILY_QUERIES - count),
            "circuit_breaker_open": self.is_circuit_open()
        }


# Singleton instance
billing_killswitch = BillingKillswitch()
