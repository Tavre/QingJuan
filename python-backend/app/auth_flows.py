from __future__ import annotations

import math
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass

TWO_FACTOR_SETUP_TTL_SECONDS = 10 * 60
TWO_FACTOR_CHALLENGE_TTL_SECONDS = 5 * 60
FLOW_MAX_ATTEMPTS = 5
TWO_FACTOR_FAILURE_LIMIT = 10
TWO_FACTOR_FAILURE_WINDOW_SECONDS = 15 * 60


class FlowNotFound(KeyError):
    pass


class FlowExpired(TimeoutError):
    pass


class FlowAttemptsExceeded(PermissionError):
    pass


class FlowInProgress(RuntimeError):
    pass


@dataclass(slots=True)
class TwoFactorSetup:
    setup_id: str
    user_id: str
    secret: str
    auth_epoch: int
    expires_at: float
    attempts_remaining: int = FLOW_MAX_ATTEMPTS


@dataclass(slots=True)
class TwoFactorChallenge:
    token: str
    user_id: str
    auth_epoch: int
    expires_at: float
    github_config_revision: int | None = None
    github_client_id: str | None = None
    attempts_remaining: int = FLOW_MAX_ATTEMPTS
    in_flight: bool = False


class TwoFactorSetupStore:
    def __init__(self) -> None:
        self._items: dict[str, TwoFactorSetup] = {}
        self._lock = threading.Lock()

    def create(
        self,
        user_id: str,
        secret: str,
        auth_epoch: int,
        *,
        now: float | None = None,
    ) -> TwoFactorSetup:
        timestamp = time.monotonic() if now is None else now
        setup = TwoFactorSetup(
            setup_id=secrets.token_urlsafe(32),
            user_id=user_id,
            secret=secret,
            auth_epoch=auth_epoch,
            expires_at=timestamp + TWO_FACTOR_SETUP_TTL_SECONDS,
        )
        with self._lock:
            self._cleanup(timestamp)
            for setup_id, existing in list(self._items.items()):
                if existing.user_id == user_id:
                    self._items.pop(setup_id, None)
            self._items[setup.setup_id] = setup
        return setup

    def reserve_attempt(
        self,
        setup_id: str,
        user_id: str,
        *,
        now: float | None = None,
    ) -> TwoFactorSetup:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            setup = self._items.get(setup_id)
            if setup is None or setup.user_id != user_id:
                self._cleanup(timestamp)
                raise FlowNotFound(setup_id)
            if setup.expires_at <= timestamp:
                self._items.pop(setup_id, None)
                raise FlowExpired(setup_id)
            if setup.attempts_remaining <= 0:
                self._items.pop(setup_id, None)
                raise FlowAttemptsExceeded(setup_id)
            setup.attempts_remaining -= 1
            return setup

    def consume(self, setup_id: str, user_id: str) -> TwoFactorSetup:
        with self._lock:
            setup = self._items.get(setup_id)
            if setup is None or setup.user_id != user_id:
                raise FlowNotFound(setup_id)
            self._items.pop(setup_id, None)
            return setup

    def discard(self, setup_id: str) -> None:
        with self._lock:
            self._items.pop(setup_id, None)

    def _cleanup(self, now: float) -> None:
        for setup_id, setup in list(self._items.items()):
            if setup.expires_at <= now:
                self._items.pop(setup_id, None)


class TwoFactorChallengeStore:
    def __init__(self) -> None:
        self._items: dict[str, TwoFactorChallenge] = {}
        self._lock = threading.Lock()

    def create(
        self,
        user_id: str,
        auth_epoch: int,
        *,
        github_config_revision: int | None = None,
        github_client_id: str | None = None,
        now: float | None = None,
    ) -> TwoFactorChallenge:
        timestamp = time.monotonic() if now is None else now
        challenge = TwoFactorChallenge(
            token=secrets.token_urlsafe(32),
            user_id=user_id,
            auth_epoch=auth_epoch,
            expires_at=timestamp + TWO_FACTOR_CHALLENGE_TTL_SECONDS,
            github_config_revision=github_config_revision,
            github_client_id=github_client_id,
        )
        with self._lock:
            self._cleanup(timestamp)
            for token, existing in list(self._items.items()):
                if existing.user_id == user_id:
                    self._items.pop(token, None)
            self._items[challenge.token] = challenge
        return challenge

    def reserve_attempt(
        self,
        token: str,
        *,
        now: float | None = None,
    ) -> TwoFactorChallenge:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            challenge = self._items.get(token)
            if challenge is None:
                self._cleanup(timestamp)
                raise FlowNotFound(token)
            if challenge.expires_at <= timestamp:
                self._items.pop(token, None)
                raise FlowExpired(token)
            if challenge.attempts_remaining <= 0:
                self._items.pop(token, None)
                raise FlowAttemptsExceeded(token)
            if challenge.in_flight:
                raise FlowInProgress(token)
            challenge.attempts_remaining -= 1
            challenge.in_flight = True
            return challenge

    def release_attempt(self, token: str) -> None:
        with self._lock:
            challenge = self._items.get(token)
            if challenge is not None:
                challenge.in_flight = False

    def consume(self, token: str) -> TwoFactorChallenge:
        with self._lock:
            challenge = self._items.pop(token, None)
        if challenge is None:
            raise FlowNotFound(token)
        return challenge

    def discard(self, token: str) -> None:
        with self._lock:
            self._items.pop(token, None)

    def _cleanup(self, now: float) -> None:
        for token, challenge in list(self._items.items()):
            if challenge.expires_at <= now:
                self._items.pop(token, None)


class TwoFactorFailureLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def reserve(self, key: str, *, now: float | None = None) -> int | None:
        timestamp = time.monotonic() if now is None else now
        with self._lock:
            attempts = self._active(key, timestamp)
            if len(attempts) >= TWO_FACTOR_FAILURE_LIMIT:
                return max(
                    1,
                    math.ceil(TWO_FACTOR_FAILURE_WINDOW_SECONDS - (timestamp - attempts[0])),
                )
            attempts.append(timestamp)
            return None

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)

    def _active(self, key: str, now: float) -> deque[float]:
        attempts = self._attempts.setdefault(key, deque())
        cutoff = now - TWO_FACTOR_FAILURE_WINDOW_SECONDS
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()
        return attempts
