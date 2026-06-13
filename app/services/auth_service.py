from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from app.core.settings import AuthSettings
from app.services.postgres_snapshot_repository import PostgresSnapshotRepository

class AuthService:
    PASSWORD_HASH_ALGORITHM = "pbkdf2_sha256"
    PASSWORD_HASH_ITERATIONS = 260_000

    def __init__(self, repository: PostgresSnapshotRepository, settings: AuthSettings) -> None:
        self.repository = repository
        self.settings = settings

    def bootstrap(self) -> None:
        self.repository.ensure_default_users(
            bootstrap_admin_username=self.settings.bootstrap_admin_username,
            bootstrap_admin_password=self.settings.bootstrap_admin_password,
            bootstrap_admin_display_name=self.settings.bootstrap_admin_display_name,
        )

    def login(
        self,
        *,
        username: str,
        password: str,
        remember_me: bool = False,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> dict[str, Any]:
        user = self.repository.get_user_by_username(username)
        if not user:
            raise ValueError("用户名或密码错误")
        if not bool(user.get("is_active")):
            raise ValueError("账户已停用")
        if not self._verify_password(password=password, password_hash=str(user["password_hash"]), password_salt=str(user["password_salt"])):
            raise ValueError("用户名或密码错误")

        ttl_hours = self.settings.remember_me_ttl_hours if remember_me else self.settings.session_ttl_hours
        expires_at = datetime.now(timezone.utc) + timedelta(hours=ttl_hours)
        token = secrets.token_urlsafe(32)
        session = self.repository.create_user_session(
            user_id=int(user["user_id"]),
            session_token=token,
            expires_at=expires_at,
            ip_address=ip_address,
            user_agent=user_agent,
        )
        profile = self.repository.get_user_profile(int(user["user_id"]))
        return {
            "token": token,
            "expires_at": expires_at,
            "user": profile,
            "session": session,
        }

    def logout(self, token: str) -> None:
        if not token:
            return
        self.repository.revoke_user_session(token)

    def get_current_user(self, token: str) -> dict[str, Any]:
        session = self.repository.get_active_session(token)
        if not session:
            raise PermissionError("登录已失效")
        return self.repository.get_user_profile(int(session["user_id"]))

    def list_users(self) -> list[dict[str, Any]]:
        return self.repository.list_users()

    def list_permissions(self) -> list[dict[str, Any]]:
        return self.repository.list_permissions()

    def list_roles(self) -> list[dict[str, Any]]:
        return self.repository.list_roles()

    def create_user(
        self,
        *,
        actor_user_id: int,
        username: str,
        display_name: str,
        title: str | None,
        password: str,
        is_active: bool,
        permission_codes: list[str],
        role_codes: list[str],
    ) -> dict[str, Any]:
        password_salt = secrets.token_hex(16)
        password_hash = self._hash_password(password=password, password_salt=password_salt)
        return self.repository.create_user(
            username=username,
            display_name=display_name,
            title=title,
            password_hash=password_hash,
            password_salt=password_salt,
            is_active=is_active,
            permission_codes=[],
            role_codes=role_codes or ["viewer"],
            actor_user_id=actor_user_id,
        )

    def update_user_permissions(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        permission_codes: list[str],
        role_codes: list[str],
        is_active: bool,
        display_name: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        self.repository.update_user_profile(
            user_id=target_user_id,
            display_name=display_name,
            title=title,
            is_active=is_active,
        )
        self.repository.replace_user_permissions(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            permission_codes=[],
        )
        self.repository.replace_user_roles(
            actor_user_id=actor_user_id,
            target_user_id=target_user_id,
            role_codes=role_codes or ["viewer"],
        )
        return self.repository.get_user_profile(target_user_id)

    def update_personal_profile(
        self,
        *,
        user_id: int,
        display_name: str | None = None,
        title: str | None = None,
        password: str | None = None,
    ) -> dict[str, Any]:
        password_hash = None
        password_salt = None
        if password:
            password_salt = secrets.token_hex(16)
            password_hash = self._hash_password(password=password, password_salt=password_salt)
        self.repository.update_user_profile(
            user_id=user_id,
            display_name=display_name,
            title=title,
            password_hash=password_hash,
            password_salt=password_salt,
        )
        return self.repository.get_user_profile(user_id)

    def user_has_permission(self, user: dict[str, Any], permission_code: str) -> bool:
        if not permission_code:
            return True
        codes = set(user.get("permission_codes") or [])
        role_codes = set(user.get("role_codes") or [])
        return "admin" in role_codes or "admin" in codes or permission_code in codes

    def _hash_password(self, *, password: str, password_salt: str) -> str:
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            password_salt.encode("utf-8"),
            self.PASSWORD_HASH_ITERATIONS,
        ).hex()
        return f"{self.PASSWORD_HASH_ALGORITHM}${self.PASSWORD_HASH_ITERATIONS}${password_salt}${digest}"

    def _verify_password(self, *, password: str, password_hash: str, password_salt: str) -> bool:
        if password_hash.startswith(f"{self.PASSWORD_HASH_ALGORITHM}$"):
            parts = password_hash.split("$", 3)
            if len(parts) != 4:
                return False
            _algorithm, iterations_raw, salt, stored_digest = parts
            try:
                iterations = int(iterations_raw)
            except ValueError:
                return False
            expected_digest = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                iterations,
            ).hex()
            return hmac.compare_digest(expected_digest, stored_digest)

        legacy_expected = hashlib.sha256(f"{password_salt}:{password}".encode("utf-8")).hexdigest()
        return hmac.compare_digest(legacy_expected, password_hash)
