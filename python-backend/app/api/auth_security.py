from __future__ import annotations

import asyncio
import sqlite3
import threading
import time
from collections import deque
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from ..account_security import generate_recovery_code_material, verify_second_factor_code
from ..auth_flows import (
    TWO_FACTOR_CHALLENGE_TTL_SECONDS,
    TWO_FACTOR_SETUP_TTL_SECONDS,
    FlowAttemptsExceeded,
    FlowExpired,
    FlowInProgress,
    FlowNotFound,
    TwoFactorChallengeStore,
    TwoFactorFailureLimiter,
    TwoFactorSetupStore,
)
from ..db import (
    AuthenticationStateConflict,
    GitHubConfigurationConflict,
    UserSecurityState,
    bind_github_identity,
    count_user_recovery_codes,
    disable_user_two_factor,
    enable_user_two_factor,
    get_user_by_github_id,
    get_user_security_state,
    refresh_github_login,
    replace_user_recovery_codes,
    unbind_github_identity,
)
from ..github_auth import (
    GitHubDeviceFlowError,
    GitHubDeviceFlowStore,
    GitHubFlowCapacityExceeded,
    GitHubFlowExpired,
    GitHubFlowNotFound,
    fetch_github_identity,
    poll_github_device_token,
    start_github_device_authorization,
)
from ..models import UserRecord
from ..registration import load_registration_settings
from ..two_factor import (
    build_totp_uri,
    encrypt_totp_secret,
    generate_totp_secret,
    verify_totp_code,
)
from ..user_auth import (
    USER_TOKEN_HEADER,
    AuthenticatedUser,
    AuthenticationStateChanged,
    complete_authenticated_session,
    read_user_session,
    read_user_session_hash,
    require_multi_user_mode,
    verify_current_user_password_state,
)

router = APIRouter()

_GITHUB_START_LIMIT = 10
_GITHUB_START_WINDOW_SECONDS = 15 * 60
_PASSWORD_REAUTH_LIMIT = 5
_PASSWORD_REAUTH_WINDOW_SECONDS = 5 * 60


class AuthenticatedLoginResponse(BaseModel):
    requiresTwoFactor: Literal[False] = False
    token: str
    user: UserRecord


class TwoFactorRequiredResponse(BaseModel):
    requiresTwoFactor: Literal[True] = True
    challengeToken: str
    expiresInSeconds: int = TWO_FACTOR_CHALLENGE_TTL_SECONDS


PasswordLoginResponse = AuthenticatedLoginResponse | TwoFactorRequiredResponse


class TwoFactorLoginPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    challengeToken: str = Field(min_length=32, max_length=256)
    code: SecretStr = Field(min_length=6, max_length=32)


class PasswordConfirmationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    password: SecretStr = Field(min_length=1, max_length=256)


class PasswordAndCodePayload(PasswordConfirmationPayload):
    code: SecretStr = Field(min_length=6, max_length=32)


class TwoFactorSetupResponse(BaseModel):
    setupId: str
    secret: str
    otpauthUri: str
    expiresInSeconds: int = TWO_FACTOR_SETUP_TTL_SECONDS


class TwoFactorEnablePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    setupId: str = Field(min_length=32, max_length=256)
    code: SecretStr = Field(min_length=6, max_length=6)


class RecoveryCodesResponse(BaseModel):
    recoveryCodes: list[str]


class AccountSecurityResponse(BaseModel):
    github: dict[str, object]
    twoFactor: dict[str, object]


class GitHubDeviceStartPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    purpose: Literal["login", "bind"]
    password: SecretStr | None = Field(default=None, min_length=1, max_length=256)
    code: SecretStr | None = Field(default=None, min_length=6, max_length=32)


class GitHubDeviceStartResponse(BaseModel):
    flowId: str
    userCode: str
    verificationUri: str
    expiresInSeconds: int
    intervalSeconds: int


class GitHubDevicePollPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flowId: str = Field(min_length=32, max_length=256)


class GitHubPendingResponse(BaseModel):
    status: Literal["pending"] = "pending"
    retryAfterSeconds: int


class GitHubBoundResponse(BaseModel):
    status: Literal["bound"] = "bound"
    githubLogin: str


class GitHubAuthenticatedResponse(BaseModel):
    status: Literal["authenticated"] = "authenticated"
    token: str
    user: UserRecord


class GitHubTwoFactorResponse(BaseModel):
    status: Literal["twoFactorRequired"] = "twoFactorRequired"
    challengeToken: str
    expiresInSeconds: int = TWO_FACTOR_CHALLENGE_TTL_SECONDS


GitHubPollResponse = (
    GitHubPendingResponse | GitHubBoundResponse | GitHubAuthenticatedResponse | GitHubTwoFactorResponse
)


class GitHubUnbindPayload(PasswordConfirmationPayload):
    code: SecretStr | None = Field(default=None, min_length=6, max_length=32)


class WindowAttemptLimiter:
    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def reserve(self, key: str) -> int | None:
        with self._lock:
            now = time.monotonic()
            attempts = self._attempts.setdefault(key, deque())
            cutoff = now - self._window_seconds
            while attempts and attempts[0] <= cutoff:
                attempts.popleft()
            if len(attempts) >= self._limit:
                return max(1, int(self._window_seconds - (now - attempts[0])))
            attempts.append(now)
            return None

    def reset(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


async def finalize_or_challenge(
    request: Request,
    authenticated: AuthenticatedUser,
    *,
    github_config_revision: int | None = None,
    github_client_id: str | None = None,
) -> PasswordLoginResponse:
    if authenticated.two_factor_enabled:
        challenge = _challenge_store(request).create(
            authenticated.user.id,
            authenticated.auth_epoch,
            github_config_revision=github_config_revision,
            github_client_id=github_client_id,
        )
        return TwoFactorRequiredResponse(challengeToken=challenge.token)
    try:
        token, completed = await asyncio.to_thread(
            complete_authenticated_session,
            authenticated,
            github_config_revision=github_config_revision,
            github_client_id=github_client_id,
        )
    except AuthenticationStateChanged as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户认证状态已变更，请重新登录",
        ) from error
    except GitHubConfigurationConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub 登录配置已变更，请重新开始",
        ) from error
    return AuthenticatedLoginResponse(token=token, user=completed)


@router.post("/login/2fa", response_model=AuthenticatedLoginResponse)
async def post_login_two_factor(
    payload: TwoFactorLoginPayload,
    request: Request,
    response: Response,
) -> AuthenticatedLoginResponse:
    require_multi_user_mode()
    _no_store(response)
    try:
        challenge = _challenge_store(request).reserve_attempt(payload.challengeToken)
    except FlowExpired as error:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="二次验证挑战已过期") from error
    except (FlowNotFound, FlowAttemptsExceeded) as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="二次验证挑战无效") from error
    except FlowInProgress as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="二次验证正在处理中") from error
    state = await asyncio.to_thread(get_user_security_state, challenge.user_id)
    if (
        state is None
        or state.user.status != "active"
        or state.auth_epoch != challenge.auth_epoch
        or not state.totp_secret_encrypted
    ):
        _challenge_store(request).discard(payload.challengeToken)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="二次验证挑战已失效")
    if challenge.github_config_revision is not None:
        github_settings = await asyncio.to_thread(load_registration_settings)
        if (
            not github_settings.github_enabled
            or github_settings.github_client_id != challenge.github_client_id
            or github_settings.github_config_revision != challenge.github_config_revision
        ):
            _challenge_store(request).discard(payload.challengeToken)
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="GitHub 登录配置已变更，请重新开始",
            )
    limiter_key = _two_factor_limiter_key(request, challenge.user_id)
    retry_after = _two_factor_limiter(request).reserve(limiter_key)
    if retry_after is not None:
        _challenge_store(request).release_attempt(payload.challengeToken)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="二次验证失败次数过多，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
    code = payload.code.get_secret_value()
    try:
        valid = await asyncio.to_thread(verify_second_factor_code, challenge.user_id, code)
    except Exception:
        _challenge_store(request).release_attempt(payload.challengeToken)
        raise
    if not valid:
        if challenge.attempts_remaining <= 0:
            _challenge_store(request).discard(payload.challengeToken)
        else:
            _challenge_store(request).release_attempt(payload.challengeToken)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="动态验证码或恢复码无效",
        )
    _challenge_store(request).consume(payload.challengeToken)
    _two_factor_limiter(request).reset(limiter_key)
    state = await asyncio.to_thread(get_user_security_state, challenge.user_id)
    if (
        state is None
        or state.user.status != "active"
        or state.auth_epoch != challenge.auth_epoch
        or not state.totp_secret_encrypted
    ):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户账号不可用")
    authenticated = AuthenticatedUser(
        user=state.user,
        auth_epoch=challenge.auth_epoch,
        two_factor_enabled=True,
    )
    try:
        token, completed = await asyncio.to_thread(
            complete_authenticated_session,
            authenticated,
            github_config_revision=challenge.github_config_revision,
            github_client_id=challenge.github_client_id,
        )
    except AuthenticationStateChanged as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="二次验证挑战已失效",
        ) from error
    except GitHubConfigurationConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub 登录配置已变更，请重新开始",
        ) from error
    return AuthenticatedLoginResponse(token=token, user=completed)


@router.get("/account/security", response_model=AccountSecurityResponse)
async def get_account_security(request: Request, response: Response) -> AccountSecurityResponse:
    require_multi_user_mode()
    _no_store(response)
    user = read_user_session(request)
    settings, state, recovery_count = await asyncio.gather(
        asyncio.to_thread(load_registration_settings),
        asyncio.to_thread(get_user_security_state, user.id),
        asyncio.to_thread(count_user_recovery_codes, user.id),
    )
    if state is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户会话已失效")
    return AccountSecurityResponse(
        github={
            "available": settings.github_enabled and bool(settings.github_client_id),
            "bound": state.github_user_id is not None,
            "login": state.github_login,
        },
        twoFactor={
            "enabled": state.totp_secret_encrypted is not None,
            "recoveryCodesRemaining": recovery_count,
        },
    )


@router.post("/account/2fa/setup", response_model=TwoFactorSetupResponse)
async def post_two_factor_setup(
    payload: PasswordConfirmationPayload,
    request: Request,
    response: Response,
) -> TwoFactorSetupResponse:
    require_multi_user_mode()
    _no_store(response)
    user = read_user_session(request)
    state = await _require_current_password(request, user.id, payload.password.get_secret_value())
    if state.totp_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="二次验证已启用")
    secret = generate_totp_secret()
    try:
        await asyncio.to_thread(encrypt_totp_secret, secret)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="二次验证密钥服务不可用",
        ) from error
    setup = _setup_store(request).create(user.id, secret, state.auth_epoch)
    return TwoFactorSetupResponse(
        setupId=setup.setup_id,
        secret=secret,
        otpauthUri=build_totp_uri(secret, account_name=user.username),
    )


@router.post("/account/2fa/enable", response_model=RecoveryCodesResponse)
async def post_two_factor_enable(
    payload: TwoFactorEnablePayload,
    request: Request,
    response: Response,
) -> RecoveryCodesResponse:
    require_multi_user_mode()
    _no_store(response)
    user = read_user_session(request)
    try:
        setup = _setup_store(request).reserve_attempt(payload.setupId, user.id)
    except FlowExpired as error:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="二次验证设置已过期") from error
    except (FlowNotFound, FlowAttemptsExceeded) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="二次验证设置无效") from error
    code = payload.code.get_secret_value()
    counter = await asyncio.to_thread(verify_totp_code, setup.secret, code)
    if counter is None:
        if setup.attempts_remaining <= 0:
            _setup_store(request).discard(payload.setupId)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="动态验证码无效")
    try:
        encrypted_secret = await asyncio.to_thread(encrypt_totp_secret, setup.secret)
    except (RuntimeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="二次验证密钥服务不可用",
        ) from error
    recovery_codes, recovery_hashes = generate_recovery_code_material()
    try:
        enabled = await asyncio.to_thread(
            enable_user_two_factor,
            user.id,
            encrypted_secret=encrypted_secret,
            accepted_counter=counter,
            recovery_code_hashes=recovery_hashes,
            keep_session_hash=read_user_session_hash(request),
            expected_auth_epoch=setup.auth_epoch,
        )
    except AuthenticationStateConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户认证状态已变更，请重新设置",
        ) from error
    if not enabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="二次验证已启用")
    _setup_store(request).consume(payload.setupId, user.id)
    return RecoveryCodesResponse(recoveryCodes=recovery_codes)


@router.post("/account/2fa/disable", status_code=status.HTTP_204_NO_CONTENT)
async def post_two_factor_disable(
    payload: PasswordAndCodePayload,
    request: Request,
) -> Response:
    require_multi_user_mode()
    user = read_user_session(request)
    auth_state = await _require_password_and_second_factor(payload, request, user)
    try:
        disabled = await asyncio.to_thread(
            disable_user_two_factor,
            user.id,
            keep_session_hash=read_user_session_hash(request),
            expected_auth_epoch=auth_state.auth_epoch,
        )
    except AuthenticationStateConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户认证状态已变更",
        ) from error
    if not disabled:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="二次验证尚未启用")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _no_store(response)
    return response


@router.post("/account/2fa/recovery-codes", response_model=RecoveryCodesResponse)
async def post_recovery_codes(
    payload: PasswordAndCodePayload,
    request: Request,
    response: Response,
) -> RecoveryCodesResponse:
    require_multi_user_mode()
    _no_store(response)
    user = read_user_session(request)
    auth_state = await _require_password_and_second_factor(payload, request, user)
    codes, hashes = generate_recovery_code_material()
    try:
        replaced = await asyncio.to_thread(
            replace_user_recovery_codes,
            user.id,
            hashes,
            expected_auth_epoch=auth_state.auth_epoch,
            keep_session_hash=read_user_session_hash(request),
        )
    except AuthenticationStateConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户认证状态已变更",
        ) from error
    if not replaced:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="二次验证尚未启用")
    return RecoveryCodesResponse(recoveryCodes=codes)


@router.post("/github/device/start", response_model=GitHubDeviceStartResponse)
async def post_github_device_start(
    payload: GitHubDeviceStartPayload,
    request: Request,
    response: Response,
) -> GitHubDeviceStartResponse:
    require_multi_user_mode()
    _no_store(response)
    settings = await asyncio.to_thread(load_registration_settings)
    if not settings.github_enabled or not settings.github_client_id:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GitHub 登录尚未启用")
    user_id: str | None = None
    bind_auth_epoch: int | None = None
    if payload.purpose == "bind":
        user = read_user_session(request)
        if payload.password is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前密码错误")
        state = await _require_current_password(
            request,
            user.id,
            payload.password.get_secret_value(),
        )
        if state.github_user_id is not None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前账号已绑定 GitHub")
        if state.totp_secret_encrypted:
            if payload.code is None:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="请输入动态验证码或恢复码",
                )
            await _require_second_factor(request, user.id, payload.code.get_secret_value())
        user_id = user.id
        bind_auth_epoch = state.auth_epoch
        start_limiter_key = f"bind:{user.id}:{_client_host(request)}"
    elif request.headers.get(USER_TOKEN_HEADER, "").strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub 登录流程不接受已登录会话")
    else:
        start_limiter_key = f"login:{_client_host(request)}"
    retry_after = _github_start_limiter(request).reserve(start_limiter_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub 验证流程创建过于频繁",
            headers={"Retry-After": str(retry_after)},
        )
    try:
        authorization = await start_github_device_authorization(settings.github_client_id)
    except GitHubDeviceFlowError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub 认证服务暂不可用",
        ) from error
    try:
        flow = _github_flow_store(request).create(
            purpose=payload.purpose,
            user_id=user_id,
            device_code=authorization.device_code,
            client_id=settings.github_client_id,
            config_revision=settings.github_config_revision,
            auth_epoch=bind_auth_epoch,
            expires_in=authorization.expires_in,
            interval=authorization.interval,
            owner_key=start_limiter_key,
        )
    except GitHubFlowCapacityExceeded as error:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="GitHub 验证流程创建过于频繁",
        ) from error
    return GitHubDeviceStartResponse(
        flowId=flow.flow_id,
        userCode=authorization.user_code,
        verificationUri=authorization.verification_uri,
        expiresInSeconds=authorization.expires_in,
        intervalSeconds=authorization.interval,
    )


@router.post("/github/device/poll", response_model=GitHubPollResponse)
async def post_github_device_poll(
    payload: GitHubDevicePollPayload,
    request: Request,
    response: Response,
) -> GitHubPollResponse:
    require_multi_user_mode()
    _no_store(response)
    store = _github_flow_store(request)
    try:
        flow, retry_after = store.reserve_poll(payload.flowId)
    except GitHubFlowExpired as error:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="GitHub 验证流程已过期") from error
    except GitHubFlowNotFound as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="GitHub 验证流程不存在") from error
    settings = await asyncio.to_thread(load_registration_settings)
    if (
        not settings.github_enabled
        or not settings.github_client_id
        or settings.github_client_id != flow.client_id
        or settings.github_config_revision != flow.config_revision
    ):
        store.discard(payload.flowId)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GitHub 登录配置已变更，请重新开始")
    if flow.purpose == "bind":
        user = read_user_session(request)
        if user.id != flow.user_id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="GitHub 绑定流程不属于当前用户")
    if retry_after is not None:
        return GitHubPendingResponse(retryAfterSeconds=retry_after)
    try:
        token_result = await poll_github_device_token(flow.client_id, flow.device_code)
    except GitHubDeviceFlowError as error:
        store.release_poll(payload.flowId)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub 认证服务暂不可用",
        ) from error
    except BaseException:
        store.release_poll(payload.flowId)
        raise
    if token_result.status == "pending":
        store.release_poll(payload.flowId)
        return GitHubPendingResponse(retryAfterSeconds=flow.interval)
    if token_result.status == "slow_down":
        return GitHubPendingResponse(retryAfterSeconds=store.slow_down(payload.flowId))
    if token_result.status in {"expired", "denied", "disabled"}:
        store.discard(payload.flowId)
        status_code = status.HTTP_410_GONE if token_result.status == "expired" else status.HTTP_403_FORBIDDEN
        raise HTTPException(status_code=status_code, detail="GitHub 验证未完成或已被拒绝")
    access_token = token_result.access_token
    if access_token is None:
        store.discard(payload.flowId)
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail="GitHub 认证响应无效")
    latest_settings = await asyncio.to_thread(load_registration_settings)
    if (
        not latest_settings.github_enabled
        or not latest_settings.github_client_id
        or latest_settings.github_client_id != flow.client_id
        or latest_settings.github_config_revision != flow.config_revision
    ):
        store.discard(payload.flowId)
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="GitHub 登录配置已变更，请重新开始")
    try:
        store.consume(payload.flowId)
    except GitHubFlowNotFound as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="GitHub 验证流程已完成或失效"
        ) from error
    try:
        identity = await fetch_github_identity(access_token)
    except GitHubDeviceFlowError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="GitHub 用户身份暂时无法读取",
        ) from error
    post_identity_settings = await asyncio.to_thread(load_registration_settings)
    if (
        not post_identity_settings.github_enabled
        or post_identity_settings.github_client_id != flow.client_id
        or post_identity_settings.github_config_revision != flow.config_revision
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="GitHub 登录配置已变更，请重新开始",
        )
    if flow.purpose == "bind":
        try:
            bound = await asyncio.to_thread(
                bind_github_identity,
                flow.user_id,
                identity.user_id,
                identity.login,
                expected_auth_epoch=flow.auth_epoch,
                expected_config_revision=flow.config_revision,
                expected_client_id=flow.client_id,
                keep_session_hash=read_user_session_hash(request),
            )
        except sqlite3.IntegrityError as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="该 GitHub 账号已绑定其他用户"
            ) from error
        except AuthenticationStateConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="用户认证状态已变更",
            ) from error
        except GitHubConfigurationConflict as error:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="GitHub 登录配置已变更，请重新开始",
            ) from error
        if bound is None:
            state = await asyncio.to_thread(get_user_security_state, flow.user_id)
            if state is None:
                raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="用户不存在")
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="当前账号已绑定 GitHub")
        return GitHubBoundResponse(githubLogin=identity.login)
    github_user = await asyncio.to_thread(get_user_by_github_id, identity.user_id)
    if github_user is None or github_user.status != "active":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="GitHub 账号未绑定可用的本地账号")
    refreshed_user = await asyncio.to_thread(
        refresh_github_login,
        identity.user_id,
        identity.login,
    )
    if refreshed_user is not None:
        github_user = refreshed_user
    github_state = await asyncio.to_thread(get_user_security_state, github_user.id)
    if (
        github_state is None
        or github_state.user.status != "active"
        or github_state.github_user_id != identity.user_id
    ):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="GitHub 账号未绑定可用的本地账号")
    auth_result = await finalize_or_challenge(
        request,
        AuthenticatedUser(
            user=github_state.user,
            auth_epoch=github_state.auth_epoch,
            two_factor_enabled=bool(github_state.totp_secret_encrypted),
        ),
        github_config_revision=flow.config_revision,
        github_client_id=flow.client_id,
    )
    if isinstance(auth_result, TwoFactorRequiredResponse):
        return GitHubTwoFactorResponse(challengeToken=auth_result.challengeToken)
    return GitHubAuthenticatedResponse(token=auth_result.token, user=auth_result.user)


@router.post("/account/github/unbind", status_code=status.HTTP_204_NO_CONTENT)
async def post_github_unbind(payload: GitHubUnbindPayload, request: Request) -> Response:
    require_multi_user_mode()
    user = read_user_session(request)
    state = await _require_current_password(request, user.id, payload.password.get_secret_value())
    if state.github_user_id is None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="尚未绑定 GitHub 账号")
    if state.totp_secret_encrypted:
        if payload.code is None:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="请输入动态验证码或恢复码")
        await _require_second_factor(request, user.id, payload.code.get_secret_value())
    try:
        unbound = await asyncio.to_thread(
            unbind_github_identity,
            user.id,
            expected_auth_epoch=state.auth_epoch,
            keep_session_hash=read_user_session_hash(request),
        )
    except AuthenticationStateConflict as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="用户认证状态已变更",
        ) from error
    if not unbound:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="尚未绑定 GitHub 账号")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _no_store(response)
    return response


async def _require_password_and_second_factor(
    payload: PasswordAndCodePayload,
    request: Request,
    user: UserRecord,
) -> UserSecurityState:
    state = await _require_current_password(request, user.id, payload.password.get_secret_value())
    if not state.totp_secret_encrypted:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="二次验证尚未启用")
    await _require_second_factor(request, user.id, payload.code.get_secret_value())
    return state


async def _require_second_factor(request: Request, user_id: str, code: str) -> None:
    limiter_key = _two_factor_limiter_key(request, user_id)
    retry_after = _two_factor_limiter(request).reserve(limiter_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="二次验证失败次数过多，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
    if not await asyncio.to_thread(verify_second_factor_code, user_id, code):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="动态验证码或恢复码无效；密钥轮换后可使用恢复码",
        )
    _two_factor_limiter(request).reset(limiter_key)


def _setup_store(request: Request) -> TwoFactorSetupStore:
    store = getattr(request.app.state, "two_factor_setup_store", None)
    if not isinstance(store, TwoFactorSetupStore):
        store = TwoFactorSetupStore()
        request.app.state.two_factor_setup_store = store
    return store


def _challenge_store(request: Request) -> TwoFactorChallengeStore:
    store = getattr(request.app.state, "two_factor_challenge_store", None)
    if not isinstance(store, TwoFactorChallengeStore):
        store = TwoFactorChallengeStore()
        request.app.state.two_factor_challenge_store = store
    return store


def _two_factor_limiter(request: Request) -> TwoFactorFailureLimiter:
    limiter = getattr(request.app.state, "two_factor_failure_limiter", None)
    if not isinstance(limiter, TwoFactorFailureLimiter):
        limiter = TwoFactorFailureLimiter()
        request.app.state.two_factor_failure_limiter = limiter
    return limiter


def _github_flow_store(request: Request) -> GitHubDeviceFlowStore:
    store = getattr(request.app.state, "github_device_flow_store", None)
    if not isinstance(store, GitHubDeviceFlowStore):
        store = GitHubDeviceFlowStore()
        request.app.state.github_device_flow_store = store
    return store


def _github_start_limiter(request: Request) -> WindowAttemptLimiter:
    limiter = getattr(request.app.state, "github_start_limiter", None)
    if not isinstance(limiter, WindowAttemptLimiter):
        limiter = WindowAttemptLimiter(
            limit=_GITHUB_START_LIMIT,
            window_seconds=_GITHUB_START_WINDOW_SECONDS,
        )
        request.app.state.github_start_limiter = limiter
    return limiter


def _password_reauth_limiter(request: Request) -> WindowAttemptLimiter:
    limiter = getattr(request.app.state, "password_reauth_limiter", None)
    if not isinstance(limiter, WindowAttemptLimiter):
        limiter = WindowAttemptLimiter(
            limit=_PASSWORD_REAUTH_LIMIT,
            window_seconds=_PASSWORD_REAUTH_WINDOW_SECONDS,
        )
        request.app.state.password_reauth_limiter = limiter
    return limiter


async def _require_current_password(
    request: Request,
    user_id: str,
    password: str,
) -> UserSecurityState:
    limiter_key = f"{user_id}:{_client_host(request)}"
    limiter = _password_reauth_limiter(request)
    retry_after = limiter.reserve(limiter_key)
    if retry_after is not None:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="当前密码验证失败次数过多，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )
    state = await asyncio.to_thread(verify_current_user_password_state, user_id, password)
    if state is None:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="当前密码错误")
    limiter.reset(limiter_key)
    return state


def _two_factor_limiter_key(request: Request, user_id: str) -> str:
    return f"{user_id}:{_client_host(request)}"


def _client_host(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
