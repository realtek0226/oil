from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import pbkdf2_hmac, sha256
from pathlib import Path
from typing import Any

from sqlalchemy import bindparam, create_engine, text
from sqlalchemy.engine import Engine

from app.core.settings import DatabaseSettings


SOURCE_DEFINITIONS: dict[str, dict[str, Any]] = {
    "oilchem_refinedoil_channel": {
        "source_name": "OilChem refined-oil channel",
        "source_type": "news_web",
        "priority": 30,
    },
    "oilchem_shandong_spot_daily_report": {
        "source_name": "OilChem Shandong spot daily report",
        "source_type": "member_web",
        "priority": 4,
    },
    "cnenergy_oil_gas_fulltext": {
        "source_name": "CnEnergy oil-gas fulltext",
        "source_type": "news_web",
        "priority": 20,
    },
    "jlc_refinedoil_hot_browser": {
        "source_name": "JLC refined-oil hot browser",
        "source_type": "browser_scrape",
        "priority": 10,
    },
    "jlc_refinedoil_archive_browser": {
        "source_name": "JLC refined-oil archive browser",
        "source_type": "browser_scrape",
        "priority": 12,
    },
    "ndrc_refined_oil_policy": {
        "source_name": "NDRC refined-oil policy",
        "source_type": "policy_web",
        "priority": 5,
    },
    "jinshi_crude_news": {
        "source_name": "Jinshi crude news",
        "source_type": "news_api",
        "priority": 15,
    },
    "brent_daily_report": {
        "source_name": "Brent daily report",
        "source_type": "forecast_api",
        "priority": 8,
    },
    "wind_brent_settlement": {
        "source_name": "Wind Brent settlement history",
        "source_type": "market_api",
        "priority": 2,
    },
    "eta_market_snapshot": {
        "source_name": "ETA market snapshot",
        "source_type": "market_api",
        "priority": 3,
    },
    "local_market_snapshot": {
        "source_name": "Local market snapshot",
        "source_type": "market_snapshot",
        "priority": 7,
    },
    "oilchem_production_sales_ratio": {
        "source_name": "OilChem production-sales ratio",
        "source_type": "member_web",
        "priority": 6,
    },
    "oilchem_weekly_refinery_metrics": {
        "source_name": "OilChem weekly refinery metrics",
        "source_type": "member_web",
        "priority": 6,
    },
    "oilchem_refinery_maintenance_plan": {
        "source_name": "OilChem refinery maintenance plan",
        "source_type": "member_web",
        "priority": 6,
    },
    "oilchem_main_refinery_maintenance_plan": {
        "source_name": "OilChem main refinery maintenance plan",
        "source_type": "member_web",
        "priority": 6,
    },
    "oilchem_refinery_inventory": {
        "source_name": "OilChem refinery inventory",
        "source_type": "member_web",
        "priority": 6,
    },
    "oilchem_refined_oil_price_center": {
        "source_name": "OilChem refined oil price center",
        "source_type": "member_api",
        "priority": 3,
    },
    "oilchem_openapi_inventory": {
        "source_name": "OilChem OpenAPI purchased inventory",
        "source_type": "market_api",
        "priority": 3,
    },
    "ganglian_excel_import": {
        "source_name": "Ganglian Excel import",
        "source_type": "manual_excel",
        "priority": 2,
    },
    "manual_prediction_template": {
        "source_name": "Manual prediction template",
        "source_type": "manual",
        "priority": 2,
    },
}

DEFAULT_PERMISSION_DEFINITIONS: list[dict[str, str]] = [
    {
        "permission_code": "workbench.view",
        "permission_name": "研究台访问",
        "module_code": "workbench",
        "description": "查看首页研究台、价格快照、晨报和预测结论。",
    },
    {
        "permission_code": "policy.view",
        "permission_name": "政策事件访问",
        "module_code": "policy",
        "description": "查看政策与事件资讯页面。",
    },
    {
        "permission_code": "agents.view",
        "permission_name": "智能体管理访问",
        "module_code": "agents",
        "description": "查看智能体状态、关系图和运行输出。",
    },
    {
        "permission_code": "chat.use",
        "permission_name": "模型对话",
        "module_code": "workbench",
        "description": "在首页右侧发起模型对话和再预测。",
    },
    {
        "permission_code": "briefing.generate",
        "permission_name": "晨报生成",
        "module_code": "workbench",
        "description": "手动生成或重生成晨报。",
    },
    {
        "permission_code": "profile.view",
        "permission_name": "个人中心访问",
        "module_code": "profile",
        "description": "查看和修改个人资料。",
    },
    {
        "permission_code": "permissions.manage",
        "permission_name": "权限管理",
        "module_code": "permissions",
        "description": "查看用户列表并配置用户权限。",
    },
]

DEFAULT_ROLE_DEFINITIONS: list[dict[str, Any]] = [
    {
        "role_code": "admin",
        "role_name": "系统管理员",
        "description": "拥有全部模块权限，可管理用户、角色模板和系统配置。",
        "permission_codes": [item["permission_code"] for item in DEFAULT_PERMISSION_DEFINITIONS],
    },
    {
        "role_code": "researcher",
        "role_name": "研究员",
        "description": "可查看研究台、政策事件和智能体运行，并使用模型对话生成研究结论。",
        "permission_codes": [
            "workbench.view",
            "policy.view",
            "agents.view",
            "chat.use",
            "briefing.generate",
            "profile.view",
        ],
    },
    {
        "role_code": "trader",
        "role_name": "交易操作",
        "description": "可查看研究台、政策事件并使用模型对话，适合日常经营决策。",
        "permission_codes": [
            "workbench.view",
            "policy.view",
            "chat.use",
            "profile.view",
        ],
    },
    {
        "role_code": "viewer",
        "role_name": "只读观察",
        "description": "只查看首页研究结论和个人中心，不可生成晨报或发起模型对话。",
        "permission_codes": [
            "workbench.view",
            "profile.view",
        ],
    },
]


@dataclass
class RefinedNewsLoadResult:
    items: list[dict[str, Any]]
    source_counts: dict[str, int]
    archive_start: date | None
    archive_end: date | None


@dataclass
class PolicyLoadResult:
    items: list[dict[str, Any]]
    source_counts: dict[str, int]
    archive_start: date | None
    archive_end: date | None


@dataclass
class ReportLoadResult:
    items: list[dict[str, Any]]
    source_counts: dict[str, int]
    archive_start: date | None
    archive_end: date | None


class PostgresSnapshotRepository:
    def __init__(self, settings: DatabaseSettings) -> None:
        self.settings = settings
        self.engine: Engine | None = None
        if settings.url.strip():
            self.engine = create_engine(
                settings.url,
                future=True,
                pool_pre_ping=True,
                echo=settings.echo,
            )

    @property
    def enabled(self) -> bool:
        return self.engine is not None

    def ensure_schema(self, schema_sql_path: str = "sql/v1_schema.sql") -> None:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        sql_path = Path(schema_sql_path)
        sql = sql_path.read_text(encoding="utf-8")
        with self.engine.begin() as connection:
            connection.exec_driver_sql(sql)

    def ensure_default_users(
        self,
        *,
        bootstrap_admin_username: str,
        bootstrap_admin_password: str,
        bootstrap_admin_display_name: str,
    ) -> None:
        if not self.engine:
            return
        with self.engine.begin() as connection:
            self._ensure_permissions(connection)
            self._ensure_roles(connection)
            self._migrate_user_roles(connection, bootstrap_admin_username=bootstrap_admin_username)
            user_count = int(
                connection.execute(text(f"select count(*) from {self._fqtn('app_user')}")).scalar_one()
            )
            if user_count > 0:
                return

            password_salt = sha256(f"{bootstrap_admin_username}:seed".encode("utf-8")).hexdigest()[:32]
            password_hash = self._build_password_hash(bootstrap_admin_password, password_salt)
            user_id = int(
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('app_user')} (
                            username,
                            display_name,
                            title,
                            password_hash,
                            password_salt,
                            is_active
                        )
                        values (
                            :username,
                            :display_name,
                            :title,
                            :password_hash,
                            :password_salt,
                            true
                        )
                        returning user_id
                        """
                    ),
                    {
                        "username": bootstrap_admin_username,
                        "display_name": bootstrap_admin_display_name,
                        "title": "系统管理员",
                        "password_hash": password_hash,
                        "password_salt": password_salt,
                    },
                ).scalar_one()
            )
            all_codes = [item["permission_code"] for item in DEFAULT_PERMISSION_DEFINITIONS]
            self._replace_user_permissions(connection, actor_user_id=user_id, target_user_id=user_id, permission_codes=all_codes)
            self._replace_user_roles(connection, actor_user_id=user_id, target_user_id=user_id, role_codes=["admin"])

    def get_user_by_username(self, username: str) -> dict[str, Any] | None:
        if not self.engine:
            return None
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    f"""
                    select user_id, username, display_name, title, password_hash, password_salt, is_active
                    from {self._fqtn('app_user')}
                    where lower(username) = lower(:username)
                    limit 1
                    """
                ),
                {"username": username},
            ).mappings().first()
        return dict(row) if row else None

    def get_user_profile(self, user_id: int) -> dict[str, Any]:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    f"""
                    select
                        u.user_id,
                        u.username,
                        u.display_name,
                        u.title,
                        u.is_active,
                        u.created_at,
                        u.updated_at,
                        u.last_login_at
                    from {self._fqtn('app_user')} u
                    where u.user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            ).mappings().first()
            if not row:
                raise KeyError(f"User not found: {user_id}")
            payload = dict(row)
            payload["permission_codes"] = self._load_user_permission_codes(connection, user_id)
            payload["permissions"] = self._load_user_permissions(connection, user_id)
            payload["role_codes"] = self._load_user_role_codes(connection, user_id)
            payload["roles"] = self._load_user_roles(connection, user_id)
            return payload

    def list_users(self) -> list[dict[str, Any]]:
        if not self.engine:
            return []
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    select
                        u.user_id,
                        u.username,
                        u.display_name,
                        u.title,
                        u.is_active,
                        u.created_at,
                        u.updated_at,
                        u.last_login_at
                    from {self._fqtn('app_user')} u
                    order by u.user_id asc
                    """
                )
            ).mappings().all()
            return [
                {
                    **dict(row),
                    "permission_codes": self._load_user_permission_codes(connection, int(row["user_id"])),
                    "permissions": self._load_user_permissions(connection, int(row["user_id"])),
                    "role_codes": self._load_user_role_codes(connection, int(row["user_id"])),
                    "roles": self._load_user_roles(connection, int(row["user_id"])),
                }
                for row in rows
            ]

    def list_permissions(self) -> list[dict[str, Any]]:
        if not self.engine:
            return []
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    select permission_code, permission_name, module_code, description
                    from {self._fqtn('app_permission')}
                    order by module_code, permission_code
                    """
                )
            ).mappings().all()
        return [dict(row) for row in rows]

    def list_roles(self) -> list[dict[str, Any]]:
        if not self.engine:
            return []
        with self.engine.begin() as connection:
            self._ensure_permissions(connection)
            self._ensure_roles(connection)
            rows = connection.execute(
                text(
                    f"""
                    select
                        r.role_id,
                        r.role_code,
                        r.role_name,
                        r.description,
                        r.is_system,
                        r.is_active,
                        r.created_at,
                        r.updated_at
                    from {self._fqtn('app_role')} r
                    where r.is_active = true
                    order by r.role_id asc
                    """
                )
            ).mappings().all()
            return [
                {
                    **dict(row),
                    "permission_codes": self._load_role_permission_codes(connection, int(row["role_id"])),
                    "permissions": self._load_role_permissions(connection, int(row["role_id"])),
                }
                for row in rows
            ]

    def create_user(
        self,
        *,
        username: str,
        display_name: str,
        title: str | None,
        password_hash: str,
        password_salt: str,
        is_active: bool,
        permission_codes: list[str],
        role_codes: list[str],
        actor_user_id: int,
    ) -> dict[str, Any]:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        with self.engine.begin() as connection:
            user_id = int(
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('app_user')} (
                            username,
                            display_name,
                            title,
                            password_hash,
                            password_salt,
                            is_active
                        )
                        values (
                            :username,
                            :display_name,
                            :title,
                            :password_hash,
                            :password_salt,
                            :is_active
                        )
                        returning user_id
                        """
                    ),
                    {
                        "username": username,
                        "display_name": display_name,
                        "title": title,
                        "password_hash": password_hash,
                        "password_salt": password_salt,
                        "is_active": is_active,
                    },
                ).scalar_one()
            )
            self._replace_user_permissions(
                connection,
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                permission_codes=permission_codes,
            )
            self._replace_user_roles(
                connection,
                actor_user_id=actor_user_id,
                target_user_id=user_id,
                role_codes=role_codes,
            )
        return self.get_user_profile(user_id)

    def create_user_session(
        self,
        *,
        user_id: int,
        session_token: str,
        expires_at: datetime,
        ip_address: str | None,
        user_agent: str | None,
    ) -> dict[str, Any]:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        token_hash = self._hash_session_token(session_token)
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('app_user_session')} (
                        user_id,
                        session_token_hash,
                        expires_at,
                        ip_address,
                        user_agent
                    )
                    values (
                        :user_id,
                        :session_token_hash,
                        :expires_at,
                        :ip_address,
                        :user_agent
                    )
                    returning session_id, expires_at, created_at
                    """
                ),
                {
                    "user_id": user_id,
                    "session_token_hash": token_hash,
                    "expires_at": expires_at,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                },
            ).mappings().first()
            connection.execute(
                text(
                    f"""
                    update {self._fqtn('app_user')}
                    set last_login_at = now(), updated_at = now()
                    where user_id = :user_id
                    """
                ),
                {"user_id": user_id},
            )
        return dict(row or {})

    def get_active_session(self, session_token: str) -> dict[str, Any] | None:
        if not self.engine:
            return None
        token_hash = self._hash_session_token(session_token)
        with self.engine.begin() as connection:
            row = connection.execute(
                text(
                    f"""
                    select
                        s.session_id,
                        s.user_id,
                        s.expires_at,
                        s.revoked_at,
                        u.is_active
                    from {self._fqtn('app_user_session')} s
                    join {self._fqtn('app_user')} u
                      on u.user_id = s.user_id
                    where s.session_token_hash = :session_token_hash
                      and s.revoked_at is null
                      and s.expires_at > now()
                      and u.is_active = true
                    limit 1
                    """
                ),
                {"session_token_hash": token_hash},
            ).mappings().first()
            if not row:
                return None
            connection.execute(
                text(
                    f"""
                    update {self._fqtn('app_user_session')}
                    set last_seen_at = now()
                    where session_id = :session_id
                    """
                ),
                {"session_id": row["session_id"]},
            )
        return dict(row)

    def revoke_user_session(self, session_token: str) -> None:
        if not self.engine or not session_token:
            return
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    update {self._fqtn('app_user_session')}
                    set revoked_at = now()
                    where session_token_hash = :session_token_hash
                      and revoked_at is null
                    """
                ),
                {"session_token_hash": self._hash_session_token(session_token)},
            )

    def save_usage_log(
        self,
        *,
        user_id: int | None,
        username: str | None,
        action: str,
        method: str | None,
        path: str,
        status_code: int | None,
        ip_address: str | None,
        user_agent: str | None,
        duration_ms: int | None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        if not self.engine:
            return
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('app_usage_log')} (
                        user_id,
                        username,
                        action,
                        method,
                        path,
                        status_code,
                        ip_address,
                        user_agent,
                        duration_ms,
                        detail
                    )
                    values (
                        :user_id,
                        :username,
                        :action,
                        :method,
                        :path,
                        :status_code,
                        :ip_address,
                        :user_agent,
                        :duration_ms,
                        cast(:detail as jsonb)
                    )
                    """
                ),
                {
                    "user_id": user_id,
                    "username": username,
                    "action": action[:64],
                    "method": method,
                    "path": path[:256],
                    "status_code": status_code,
                    "ip_address": ip_address,
                    "user_agent": user_agent[:256] if user_agent else None,
                    "duration_ms": duration_ms,
                    "detail": json.dumps(detail or {}, ensure_ascii=False),
                },
            )

    def list_usage_logs(
        self,
        *,
        limit: int = 100,
        user_id: int | None = None,
        action: str | None = None,
    ) -> list[dict[str, Any]]:
        if not self.engine:
            return []
        filters = []
        params: dict[str, Any] = {"limit": max(1, min(int(limit), 500))}
        if user_id is not None:
            filters.append("user_id = :user_id")
            params["user_id"] = user_id
        if action:
            filters.append("action = :action")
            params["action"] = action
        where_clause = f"where {' and '.join(filters)}" if filters else ""
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    select
                        usage_id,
                        user_id,
                        username,
                        action,
                        method,
                        path,
                        status_code,
                        ip_address,
                        user_agent,
                        duration_ms,
                        detail,
                        created_at
                    from {self._fqtn('app_usage_log')}
                    {where_clause}
                    order by created_at desc
                    limit :limit
                    """
                ),
                params,
            ).mappings().all()
        return [dict(row) for row in rows]

    def update_user_profile(
        self,
        *,
        user_id: int,
        display_name: str | None = None,
        title: str | None = None,
        is_active: bool | None = None,
        password_hash: str | None = None,
        password_salt: str | None = None,
    ) -> None:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        assignments = ["updated_at = now()"]
        params: dict[str, Any] = {"user_id": user_id}
        if display_name is not None:
            assignments.append("display_name = :display_name")
            params["display_name"] = display_name
        if title is not None:
            assignments.append("title = :title")
            params["title"] = title
        if is_active is not None:
            assignments.append("is_active = :is_active")
            params["is_active"] = is_active
        if password_hash is not None and password_salt is not None:
            assignments.append("password_hash = :password_hash")
            assignments.append("password_salt = :password_salt")
            params["password_hash"] = password_hash
            params["password_salt"] = password_salt
        if len(assignments) == 1:
            return
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    f"""
                    update {self._fqtn('app_user')}
                    set {", ".join(assignments)}
                    where user_id = :user_id
                    """
                ),
                params,
            )

    def replace_user_permissions(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        permission_codes: list[str],
    ) -> None:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        with self.engine.begin() as connection:
            self._replace_user_permissions(
                connection,
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                permission_codes=permission_codes,
            )

    def replace_user_roles(
        self,
        *,
        actor_user_id: int,
        target_user_id: int,
        role_codes: list[str],
    ) -> None:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        with self.engine.begin() as connection:
            self._replace_user_roles(
                connection,
                actor_user_id=actor_user_id,
                target_user_id=target_user_id,
                role_codes=role_codes,
            )

    def save_refined_news_items(self, snapshot_date: date, items: list[dict[str, Any]]) -> int:
        if not self.engine or not items:
            return 0

        saved = 0
        seen_record_ids: set[tuple[str, str]] = set()
        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {self._source_code_for_item(item) for item in items})
            for item in items:
                source_code = self._source_code_for_item(item)
                payload = dict(item)
                payload["snapshot_date"] = snapshot_date.isoformat()
                publish_time = self._normalize_timestamp(
                    item.get("publish_time") or item.get("publish_date"),
                    fallback_date=snapshot_date,
                )
                title = str(item.get("headline") or item.get("title") or "").strip()
                content = str(item.get("content") or item.get("summary") or title).strip()
                source_record_id = self._build_source_record_id(item, publish_time)
                record_key = (source_code, source_record_id)
                if record_key in seen_record_ids:
                    continue
                seen_record_ids.add(record_key)
                if self._raw_record_exists(
                    connection,
                    table_name="ods_raw_news",
                    source_id=source_ids[source_code],
                    source_record_id=source_record_id,
                ):
                    continue
                payload_hash = self._payload_hash(payload)
                result = connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_news')} (
                            source_id,
                            source_record_id,
                            publish_time,
                            title,
                            content,
                            author,
                            payload,
                            payload_hash,
                            dt
                        )
                        values (
                            :source_id,
                            :source_record_id,
                            :publish_time,
                            :title,
                            :content,
                            :author,
                            cast(:payload as jsonb),
                            :payload_hash,
                            :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    {
                        "source_id": source_ids[source_code],
                        "source_record_id": source_record_id,
                        "publish_time": publish_time,
                        "title": title or None,
                        "content": content or title,
                        "author": item.get("author"),
                        "payload": json.dumps(payload, ensure_ascii=False),
                        "payload_hash": payload_hash,
                        "dt": snapshot_date,
                    },
                )
                saved += int(result.rowcount or 0)
        return saved

    def save_policy_items(self, snapshot_date: date, items: list[dict[str, Any]]) -> int:
        if not self.engine or not items:
            return 0

        saved = 0
        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {"ndrc_refined_oil_policy"})
            source_id = source_ids["ndrc_refined_oil_policy"]
            for item in items:
                payload = dict(item)
                payload["snapshot_date"] = snapshot_date.isoformat()
                source_record_id = self._build_policy_record_id(item)
                if self._raw_record_exists(
                    connection,
                    table_name="ods_raw_market",
                    source_id=source_id,
                    source_record_id=source_record_id,
                ):
                    continue
                payload_hash = self._payload_hash(payload)
                source_event_time = self._normalize_timestamp(
                    item.get("effective_time") or item.get("publish_date"),
                    fallback_date=snapshot_date,
                )
                result = connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id,
                            source_record_id,
                            topic,
                            source_event_time,
                            payload,
                            payload_hash,
                            dt
                        )
                        values (
                            :source_id,
                            :source_record_id,
                            :topic,
                            :source_event_time,
                            cast(:payload as jsonb),
                            :payload_hash,
                            :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "policy_notice",
                        "source_event_time": source_event_time,
                        "payload": json.dumps(payload, ensure_ascii=False),
                        "payload_hash": payload_hash,
                        "dt": snapshot_date,
                    },
                )
                saved += int(result.rowcount or 0)
        return saved

    def save_jinshi_news_items(self, snapshot_date: date, items: list[dict[str, Any]]) -> int:
        normalized_items = []
        for item in items:
            normalized = dict(item)
            normalized.setdefault("source", "jinshi_crude_news")
            normalized_items.append(normalized)
        return self.save_refined_news_items(snapshot_date=snapshot_date, items=normalized_items)

    def save_brent_report(self, snapshot_date: date, report_payload: dict[str, Any] | None) -> int:
        if not self.engine or not report_payload:
            return 0

        payload = dict(report_payload)
        payload["snapshot_date"] = snapshot_date.isoformat()
        report_date = self._extract_item_date(payload) or snapshot_date
        source_record_id = self._build_report_record_id(payload)
        payload_hash = self._payload_hash(payload)

        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {"brent_daily_report"})
            result = connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('ods_raw_forecast')} (
                        source_id,
                        report_date,
                        report_title,
                        source_record_id,
                        payload,
                        markdown_body,
                        payload_hash,
                        dt
                    )
                    values (
                        :source_id,
                        :report_date,
                        :report_title,
                        :source_record_id,
                        cast(:payload as jsonb),
                        :markdown_body,
                        :payload_hash,
                        :dt
                    )
                    on conflict (source_id, source_record_id, payload_hash) do nothing
                    """
                ),
                {
                    "source_id": source_ids["brent_daily_report"],
                    "report_date": report_date,
                    "report_title": payload.get("title"),
                    "source_record_id": source_record_id,
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "markdown_body": payload.get("markdown"),
                    "payload_hash": payload_hash,
                    "dt": snapshot_date,
                },
            )
        return int(result.rowcount or 0)

    def save_market_snapshot(
        self,
        *,
        snapshot_date: date,
        latest_prices: dict[str, float | None],
        mode: str,
        reason: str | None,
    ) -> int:
        if not self.engine:
            return 0

        payload = {
            "snapshot_date": snapshot_date.isoformat(),
            "market_data_mode": mode,
            "market_data_reason": reason,
            "latest_prices": latest_prices,
        }
        payload_hash = self._payload_hash(payload)
        source_record_id = f"local-market-snapshot-{snapshot_date.isoformat()}-{payload_hash[:12]}"
        now = datetime.now(timezone.utc)

        indicator_rows = []
        for indicator_code, value in latest_prices.items():
            indicator_rows.append(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": indicator_code,
                    "category": "market_snapshot",
                    "sub_category": "refined_oil",
                    "unit": self._default_unit_for_indicator(indicator_code),
                    "freq": "snapshot",
                    "value_type": "number",
                    "fill_policy_default": "last",
                    "description": f"Auto persisted snapshot for {indicator_code}",
                    "entity_code": self._entity_code_for_indicator(indicator_code),
                    "entity_name": self._entity_name_for_indicator(indicator_code),
                    "entity_type": "market_region",
                    "region_level": self._entity_region_level(indicator_code),
                    "product_family": "GASOLINE_92" if "gas92" in indicator_code else "CRUDE",
                    "observation_time": now,
                    "publish_time": now,
                    "value_num": value,
                    "unit_value": self._default_unit_for_indicator(indicator_code),
                    "source_record_id": source_record_id,
                    "quality_flag": "ok" if value is not None else "fallback",
                    "dt": snapshot_date,
                }
            )

        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {"local_market_snapshot"})
            source_id = source_ids["local_market_snapshot"]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, indicator_rows)
            connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('ods_raw_market')} (
                        source_id,
                        source_record_id,
                        topic,
                        source_event_time,
                        payload,
                        payload_hash,
                        dt
                    )
                    values (
                        :source_id,
                        :source_record_id,
                        :topic,
                        :source_event_time,
                        cast(:payload as jsonb),
                        :payload_hash,
                        :dt
                    )
                    on conflict (source_id, source_record_id, payload_hash) do nothing
                    """
                ),
                {
                    "source_id": source_id,
                    "source_record_id": source_record_id,
                    "topic": "market_snapshot",
                    "source_event_time": now,
                    "payload": json.dumps(payload, ensure_ascii=False),
                    "payload_hash": payload_hash,
                    "dt": snapshot_date,
                },
            )
            rows = list(
                connection.execute(
                    text(
                        f"""
                        select
                            i.indicator_id,
                            i.indicator_code,
                            e.entity_id,
                            e.entity_code
                        from {self._fqtn('dim_indicator')} i
                        join {self._fqtn('dim_entity')} e
                          on 1 = 1
                        where i.indicator_code in :indicator_codes
                          and e.entity_code in :entity_codes
                        """
                    ).bindparams(
                        bindparam("indicator_codes", expanding=True),
                        bindparam("entity_codes", expanding=True),
                    ),
                    {
                        "indicator_codes": [row["indicator_code"] for row in indicator_rows],
                        "entity_codes": [row["entity_code"] for row in indicator_rows],
                    },
                ).mappings()
            )
            indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
            entity_id_map = {str(row["entity_code"]): int(row["entity_id"]) for row in rows}

            ts_rows = []
            for row in indicator_rows:
                indicator_id = indicator_id_map.get(row["indicator_code"])
                entity_id = entity_id_map.get(row["entity_code"])
                if not indicator_id or not entity_id:
                    continue
                ts_rows.append(
                    {
                        "indicator_id": indicator_id,
                        "entity_id": entity_id,
                        "observation_time": row["observation_time"],
                        "publish_time": row["publish_time"],
                        "freq": "snapshot",
                        "value_num": row["value_num"],
                        "value_text": None,
                        "unit": row["unit_value"],
                        "currency": "CNY" if row["indicator_code"] != "brent_active_settlement" else "USD",
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "is_final": True,
                        "revision_no": 1,
                        "quality_flag": row["quality_flag"],
                        "effective_from": row["publish_time"],
                        "effective_to": None,
                        "dt": row["dt"],
                    }
                )
            if ts_rows:
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('fact_market_timeseries')} (
                            indicator_id,
                            entity_id,
                            observation_time,
                            publish_time,
                            freq,
                            value_num,
                            value_text,
                            unit,
                            currency,
                            source_id,
                            source_record_id,
                            is_final,
                            revision_no,
                            quality_flag,
                            effective_from,
                            effective_to,
                            dt
                        )
                        values (
                            :indicator_id,
                            :entity_id,
                            :observation_time,
                            :publish_time,
                            :freq,
                            :value_num,
                            :value_text,
                            :unit,
                            :currency,
                            :source_id,
                            :source_record_id,
                            :is_final,
                            :revision_no,
                            :quality_flag,
                            :effective_from,
                            :effective_to,
                            :dt
                        )
                        on conflict (indicator_id, entity_id, observation_time, revision_no, source_id) do nothing
                        """
                    ),
                    ts_rows,
                )
        return len(indicator_rows)

    def delete_market_timeseries_by_source(self, source_code: str) -> dict[str, int]:
        if not self.engine:
            return {"fact_market_timeseries": 0, "ods_raw_market": 0}
        with self.engine.begin() as connection:
            source_id = connection.execute(
                text(
                    f"""
                    select source_id
                    from {self._fqtn('dim_source')}
                    where source_code = :source_code
                    """
                ),
                {"source_code": source_code},
            ).scalar_one_or_none()
            if source_id is None:
                return {"fact_market_timeseries": 0, "ods_raw_market": 0}
            fact_result = connection.execute(
                text(
                    f"""
                    delete from {self._fqtn('fact_market_timeseries')}
                    where source_id = :source_id
                    """
                ),
                {"source_id": source_id},
            )
            ods_result = connection.execute(
                text(
                    f"""
                    delete from {self._fqtn('ods_raw_market')}
                    where source_id = :source_id
                    """
                ),
                {"source_id": source_id},
            )
        return {
            "fact_market_timeseries": int(fact_result.rowcount or 0),
            "ods_raw_market": int(ods_result.rowcount or 0),
        }

    def save_wind_brent_settlement_records(self, records: list[dict[str, Any]]) -> int:
        if not self.engine or not records:
            return 0
        now = datetime.now(timezone.utc)
        indicator_rows = [
            {
                "indicator_code": "brent_active_settlement",
                "indicator_name": "Brent futures active settlement",
                "category": "crude",
                "sub_category": "wind_settlement",
                "unit": "美元/桶",
                "freq": "daily",
                "value_type": "number",
                "fill_policy_default": "latest_available",
                "description": "Wind /wsd B.IPE settle history",
                "entity_code": "BRENT",
                "entity_name": "Brent",
                "entity_type": "commodity",
                "region_level": "global",
                "product_family": "CRUDE",
            }
        ]
        with self.engine.begin() as connection:
            source_id = self._ensure_source_ids(connection, {"wind_brent_settlement"})["wind_brent_settlement"]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, indicator_rows)
            ids = connection.execute(
                text(
                    f"""
                    select i.indicator_id, e.entity_id
                    from {self._fqtn('dim_indicator')} i
                    join {self._fqtn('dim_entity')} e on e.entity_code = 'BRENT'
                    where i.indicator_code = 'brent_active_settlement'
                    """
                )
            ).mappings().first()
            if not ids:
                return 0
            indicator_id = int(ids["indicator_id"])
            entity_id = int(ids["entity_id"])
            raw_rows: list[dict[str, Any]] = []
            ts_rows: list[dict[str, Any]] = []
            for record in records:
                observation_date = self._coerce_date(record.get("date"))
                value = record.get("settle")
                if observation_date is None or value is None:
                    continue
                payload = {
                    "code": record.get("code") or "B.IPE",
                    "date": observation_date.isoformat(),
                    "settle": float(value),
                    "raw": record.get("raw") or {},
                }
                source_record_id = f"wind_brent_settlement:B.IPE:{observation_date.isoformat()}"
                payload_hash = self._payload_hash(payload)
                raw_rows.append(
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "brent_settlement",
                        "source_event_time": datetime.combine(observation_date, time(0, 0)),
                        "payload": json.dumps(payload, ensure_ascii=False, default=str),
                        "payload_hash": payload_hash,
                        "dt": observation_date,
                    }
                )
                ts_rows.append(
                    {
                        "indicator_id": indicator_id,
                        "entity_id": entity_id,
                        "observation_time": datetime.combine(observation_date, time(0, 0)),
                        "publish_time": now,
                        "freq": "daily",
                        "value_num": float(value),
                        "value_text": None,
                        "unit": "美元/桶",
                        "currency": "USD",
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "is_final": True,
                        "revision_no": 1,
                        "quality_flag": "ok",
                        "effective_from": now,
                        "effective_to": None,
                        "dt": observation_date,
                    }
                )
            if raw_rows:
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id, source_record_id, topic, source_event_time,
                            payload, payload_hash, dt
                        )
                        values (
                            :source_id, :source_record_id, :topic, :source_event_time,
                            cast(:payload as jsonb), :payload_hash, :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    raw_rows,
                )
            if not ts_rows:
                return 0
            result = connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('fact_market_timeseries')} (
                        indicator_id, entity_id, observation_time, publish_time, freq,
                        value_num, value_text, unit, currency, source_id, source_record_id,
                        is_final, revision_no, quality_flag, effective_from, effective_to, dt
                    )
                    values (
                        :indicator_id, :entity_id, :observation_time, :publish_time, :freq,
                        :value_num, :value_text, :unit, :currency, :source_id, :source_record_id,
                        :is_final, :revision_no, :quality_flag, :effective_from, :effective_to, :dt
                    )
                    on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                    do update set
                        publish_time = excluded.publish_time,
                        value_num = excluded.value_num,
                        source_record_id = excluded.source_record_id,
                        quality_flag = excluded.quality_flag,
                        effective_from = excluded.effective_from,
                        dt = excluded.dt
                    """
                ),
                ts_rows,
            )
            return int(result.rowcount or 0)

    def save_oilchem_price_records(self, records: list[dict[str, Any]]) -> int:
        if not self.engine or not records:
            return 0
        now = datetime.now(timezone.utc)
        indicator_rows = []
        for record in records:
            indicator_code = str(record.get("indicator_code") or "")
            region_code = str(record.get("region_code") or "")
            if not indicator_code or not region_code:
                continue
            product = str(record.get("product") or "")
            region = str(record.get("region") or "")
            indicator_rows.append(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": f"隆众{region}{product}库提现汇价",
                    "category": "refined_oil",
                    "sub_category": "oilchem_price_center",
                    "unit": str(record.get("unit") or "元/吨"),
                    "freq": "daily",
                    "value_type": "number",
                    "fill_policy_default": "latest_available",
                    "description": "隆众价格中心汽柴油库提现汇价",
                    "entity_code": region_code,
                    "entity_name": region,
                    "entity_type": "market_region",
                    "region_level": "country" if region_code == "NATIONAL" else "province" if region_code == "SHANDONG" else "macro_region",
                    "product_family": "GASOLINE_92" if "gas92" in indicator_code else "DIESEL",
                }
            )

        if not indicator_rows:
            return 0

        saved = 0
        with self.engine.begin() as connection:
            source_id = self._ensure_source_ids(connection, {"oilchem_refined_oil_price_center"})[
                "oilchem_refined_oil_price_center"
            ]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, indicator_rows)
            rows = list(
                connection.execute(
                    text(
                        f"""
                        select
                            i.indicator_id,
                            i.indicator_code,
                            e.entity_id,
                            e.entity_code
                        from {self._fqtn('dim_indicator')} i
                        join {self._fqtn('dim_entity')} e on 1 = 1
                        where i.indicator_code in :indicator_codes
                          and e.entity_code in :entity_codes
                        """
                    ).bindparams(
                        bindparam("indicator_codes", expanding=True),
                        bindparam("entity_codes", expanding=True),
                    ),
                    {
                        "indicator_codes": [row["indicator_code"] for row in indicator_rows],
                        "entity_codes": [row["entity_code"] for row in indicator_rows],
                    },
                ).mappings()
            )
            indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
            entity_id_map = {str(row["entity_code"]): int(row["entity_id"]) for row in rows}

            raw_rows: list[dict[str, Any]] = []
            ts_rows: list[dict[str, Any]] = []
            for record in records:
                observation_date = self._extract_item_date(record) or date.today()
                publish_time = self._normalize_timestamp(record.get("publish_time"), fallback_date=observation_date)
                indicator_code = str(record.get("indicator_code") or "")
                region_code = str(record.get("region_code") or "")
                source_record_id = (
                    f"oilchem_price:{record.get('product_code')}:{region_code}:{observation_date.isoformat()}"
                )
                payload_hash = self._payload_hash(record)
                raw_rows.append(
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "oilchem_price_center",
                        "source_event_time": publish_time,
                        "payload": json.dumps(record, ensure_ascii=False, default=str),
                        "payload_hash": payload_hash,
                        "dt": observation_date,
                    }
                )
                value = record.get("price")
                if value is None:
                    continue
                indicator_id = indicator_id_map.get(indicator_code)
                entity_id = entity_id_map.get(region_code)
                if not indicator_id or not entity_id:
                    continue
                ts_rows.append(
                    {
                        "indicator_id": indicator_id,
                        "entity_id": entity_id,
                        "observation_time": datetime.combine(observation_date, time(0, 0)),
                        "publish_time": publish_time,
                        "freq": "daily",
                        "value_num": float(value),
                        "value_text": record.get("price_text"),
                        "unit": str(record.get("unit") or "元/吨"),
                        "currency": "CNY",
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "is_final": True,
                        "revision_no": 1,
                        "quality_flag": "ok",
                        "effective_from": publish_time,
                        "effective_to": None,
                        "dt": observation_date,
                    }
                )
            if raw_rows:
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id, source_record_id, topic, source_event_time,
                            payload, payload_hash, dt
                        )
                        values (
                            :source_id, :source_record_id, :topic, :source_event_time,
                            cast(:payload as jsonb), :payload_hash, :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    raw_rows,
                )
            if ts_rows:
                result = connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('fact_market_timeseries')} (
                            indicator_id, entity_id, observation_time, publish_time, freq,
                            value_num, value_text, unit, currency, source_id, source_record_id,
                            is_final, revision_no, quality_flag, effective_from, effective_to, dt
                        )
                        values (
                            :indicator_id, :entity_id, :observation_time, :publish_time, :freq,
                            :value_num, :value_text, :unit, :currency, :source_id, :source_record_id,
                            :is_final, :revision_no, :quality_flag, :effective_from, :effective_to, :dt
                        )
                        on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                        do update set
                            publish_time = excluded.publish_time,
                            value_num = excluded.value_num,
                            value_text = excluded.value_text,
                            source_record_id = excluded.source_record_id,
                            quality_flag = excluded.quality_flag,
                            effective_from = excluded.effective_from,
                            dt = excluded.dt
                        """
                    ),
                    ts_rows,
                )
                saved = int(result.rowcount or 0)
        return saved

    def save_oilchem_production_sales_records(self, records: list[dict[str, Any]]) -> int:
        if not self.engine or not records:
            return 0

        indicator_meta = {
            "oilchem_sd_gasoline_production_sales_ratio": {
                "indicator_name": "山东地炼汽油日度产销率",
                "entity_code": "SHANDONG_REFINERY_GASOLINE",
                "entity_name": "山东地炼汽油",
                "value_field": "gasoline_ratio",
            },
            "oilchem_sd_diesel_production_sales_ratio": {
                "indicator_name": "山东地炼柴油日度产销率",
                "entity_code": "SHANDONG_REFINERY_DIESEL",
                "entity_name": "山东地炼柴油",
                "value_field": "diesel_ratio",
            },
        }
        indicator_rows = [
            {
                "indicator_code": code,
                "indicator_name": str(meta["indicator_name"]).replace("山东地炼", entity_name),
                "category": "refined_oil",
                "sub_category": "production_sales_ratio",
                "unit": "%",
                "freq": "daily",
                "value_type": "number",
                "fill_policy_default": "latest_available",
                "description": "隆众资讯山东地炼成品油日度产销率",
                "entity_code": meta["entity_code"],
                "entity_name": meta["entity_name"],
                "entity_type": "refinery_group",
                "region_level": "province",
                "product_family": "GASOLINE_92" if "gasoline" in code else "DIESEL",
            }
            for code, meta in indicator_meta.items()
        ]

        saved = 0
        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {"oilchem_production_sales_ratio"})
            source_id = source_ids["oilchem_production_sales_ratio"]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, indicator_rows)
            rows = list(
                connection.execute(
                    text(
                        f"""
                        select
                            i.indicator_id,
                            i.indicator_code,
                            e.entity_id,
                            e.entity_code
                        from {self._fqtn('dim_indicator')} i
                        join {self._fqtn('dim_entity')} e
                          on 1 = 1
                        where i.indicator_code in :indicator_codes
                          and e.entity_code in :entity_codes
                        """
                    ).bindparams(
                        bindparam("indicator_codes", expanding=True),
                        bindparam("entity_codes", expanding=True),
                    ),
                    {
                        "indicator_codes": list(indicator_meta.keys()),
                        "entity_codes": [meta["entity_code"] for meta in indicator_meta.values()],
                    },
                ).mappings()
            )
            indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
            entity_id_map = {str(row["entity_code"]): int(row["entity_id"]) for row in rows}

            for record in records:
                observation_date = self._extract_item_date(record) or date.today()
                publish_time = self._normalize_timestamp(record.get("publish_time"), fallback_date=observation_date)
                source_record_id = str(record.get("url") or f"oilchem_production_sales_ratio:{observation_date}")
                payload_hash = self._payload_hash(record)
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id,
                            source_record_id,
                            topic,
                            source_event_time,
                            payload,
                            payload_hash,
                            dt
                        )
                        values (
                            :source_id,
                            :source_record_id,
                            :topic,
                            :source_event_time,
                            cast(:payload as jsonb),
                            :payload_hash,
                            :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "production_sales_ratio",
                        "source_event_time": publish_time,
                        "payload": json.dumps(record, ensure_ascii=False),
                        "payload_hash": payload_hash,
                        "dt": observation_date,
                    },
                )
                for indicator_code, meta in indicator_meta.items():
                    value = record.get(meta["value_field"])
                    if value is None:
                        continue
                    indicator_id = indicator_id_map.get(indicator_code)
                    entity_id = entity_id_map.get(meta["entity_code"])
                    if not indicator_id or not entity_id:
                        continue
                    result = connection.execute(
                        text(
                            f"""
                            insert into {self._fqtn('fact_market_timeseries')} (
                                indicator_id,
                                entity_id,
                                observation_time,
                                publish_time,
                                freq,
                                value_num,
                                value_text,
                                unit,
                                currency,
                                source_id,
                                source_record_id,
                                is_final,
                                revision_no,
                                quality_flag,
                                effective_from,
                                effective_to,
                                dt
                            )
                            values (
                                :indicator_id,
                                :entity_id,
                                :observation_time,
                                :publish_time,
                                :freq,
                                :value_num,
                                :value_text,
                                :unit,
                                :currency,
                                :source_id,
                                :source_record_id,
                                :is_final,
                                :revision_no,
                                :quality_flag,
                                :effective_from,
                                :effective_to,
                                :dt
                            )
                            on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                            do update set
                                publish_time = excluded.publish_time,
                                value_num = excluded.value_num,
                                source_record_id = excluded.source_record_id,
                                quality_flag = excluded.quality_flag,
                                effective_from = excluded.effective_from,
                                dt = excluded.dt
                            """
                        ),
                        {
                            "indicator_id": indicator_id,
                            "entity_id": entity_id,
                            "observation_time": datetime.combine(observation_date, time(0, 0)),
                            "publish_time": publish_time,
                            "freq": "daily",
                            "value_num": float(value),
                            "value_text": None,
                            "unit": "%",
                            "currency": None,
                            "source_id": source_id,
                            "source_record_id": source_record_id,
                            "is_final": True,
                            "revision_no": 1,
                            "quality_flag": "ok",
                            "effective_from": publish_time,
                            "effective_to": None,
                            "dt": observation_date,
                        },
                    )
                    saved += int(result.rowcount or 0)
        return saved

    def save_oilchem_weekly_metric_records(self, records: list[dict[str, Any]]) -> int:
        if not self.engine or not records:
            return 0

        indicator_meta = {
            "oilchem_shandong_cdu_utilization_weekly": {
                "indicator_name": "山东地炼常减压周均产能利用率",
                "sub_category": "capacity_utilization",
                "unit": "%",
                "currency": None,
                "value_field": "capacity_utilization",
            },
            "oilchem_shandong_cdu_utilization_wow_pct": {
                "indicator_name": "山东地炼常减压周均产能利用率环比",
                "sub_category": "capacity_utilization",
                "unit": "%",
                "currency": None,
                "value_field": "capacity_utilization_wow_pct",
            },
            "oilchem_shandong_cdu_utilization_yoy_pct": {
                "indicator_name": "山东地炼常减压周均产能利用率同比",
                "sub_category": "capacity_utilization",
                "unit": "%",
                "currency": None,
                "value_field": "capacity_utilization_yoy_pct",
            },
            "oilchem_shandong_cdu_utilization_ex_large_weekly": {
                "indicator_name": "山东地炼常减压周均产能利用率（不含大炼化）",
                "sub_category": "capacity_utilization",
                "unit": "%",
                "currency": None,
                "value_field": "capacity_utilization_ex_large",
            },
            "oilchem_shandong_cdu_utilization_ex_large_wow_pct": {
                "indicator_name": "山东地炼常减压周均产能利用率环比（不含大炼化）",
                "sub_category": "capacity_utilization",
                "unit": "%",
                "currency": None,
                "value_field": "capacity_utilization_ex_large_wow_pct",
            },
            "oilchem_shandong_cdu_utilization_ex_large_yoy_pct": {
                "indicator_name": "山东地炼常减压周均产能利用率同比（不含大炼化）",
                "sub_category": "capacity_utilization",
                "unit": "%",
                "currency": None,
                "value_field": "capacity_utilization_ex_large_yoy_pct",
            },
            "oilchem_shandong_comprehensive_refining_profit_weekly": {
                "indicator_name": "山东地炼综合装置炼油利润",
                "sub_category": "refining_profit",
                "unit": "元/吨",
                "currency": "CNY",
                "value_field": "refining_profit",
            },
            "oilchem_shandong_comprehensive_refining_profit_wow_pct": {
                "indicator_name": "山东地炼综合装置炼油利润环比",
                "sub_category": "refining_profit",
                "unit": "%",
                "currency": None,
                "value_field": "refining_profit_wow_pct",
            },
            "oilchem_shandong_comprehensive_refining_profit_yoy_pct": {
                "indicator_name": "山东地炼综合装置炼油利润同比",
                "sub_category": "refining_profit",
                "unit": "%",
                "currency": None,
                "value_field": "refining_profit_yoy_pct",
            },
            "oilchem_shandong_crude_cost_weekly": {
                "indicator_name": "山东地炼原油周均成本",
                "sub_category": "refining_cost",
                "unit": "元/吨",
                "currency": "CNY",
                "value_field": "crude_cost",
            },
            "oilchem_shandong_crude_cost_change_weekly": {
                "indicator_name": "山东地炼原油周均成本变动",
                "sub_category": "refining_cost",
                "unit": "元/吨",
                "currency": "CNY",
                "value_field": "crude_cost_change",
            },
            "oilchem_shandong_comprehensive_revenue_weekly": {
                "indicator_name": "山东地炼综合收入",
                "sub_category": "refining_revenue",
                "unit": "元/吨",
                "currency": "CNY",
                "value_field": "comprehensive_revenue",
            },
            "oilchem_shandong_comprehensive_revenue_change_weekly": {
                "indicator_name": "山东地炼综合收入变动",
                "sub_category": "refining_revenue",
                "unit": "元/吨",
                "currency": "CNY",
                "value_field": "comprehensive_revenue_change",
            },
        }
        indicator_rows = [
            {
                "indicator_code": code,
                "indicator_name": meta["indicator_name"],
                "category": "refined_oil",
                "sub_category": meta["sub_category"],
                "unit": meta["unit"],
                "freq": "weekly",
                "value_type": "number",
                "fill_policy_default": "latest_available",
                "description": "隆众资讯山东地炼周度产能利用率与炼油利润指标",
                "entity_code": "SHANDONG_REFINERY",
                "entity_name": "山东地炼",
                "entity_type": "refinery_group",
                "region_level": "province",
                "product_family": "REFINED_OIL",
            }
            for code, meta in indicator_meta.items()
        ]

        saved = 0
        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {"oilchem_weekly_refinery_metrics"})
            source_id = source_ids["oilchem_weekly_refinery_metrics"]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, indicator_rows)
            rows = list(
                connection.execute(
                    text(
                        f"""
                        select
                            i.indicator_id,
                            i.indicator_code,
                            e.entity_id,
                            e.entity_code
                        from {self._fqtn('dim_indicator')} i
                        join {self._fqtn('dim_entity')} e
                          on 1 = 1
                        where i.indicator_code in :indicator_codes
                          and e.entity_code = :entity_code
                        """
                    ).bindparams(bindparam("indicator_codes", expanding=True)),
                    {
                        "indicator_codes": list(indicator_meta.keys()),
                        "entity_code": "SHANDONG_REFINERY",
                    },
                ).mappings()
            )
            indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
            entity_id = int(rows[0]["entity_id"]) if rows else None

            for record in records:
                observation_date = self._extract_item_date(record) or date.today()
                publish_time = self._normalize_timestamp(record.get("publish_time"), fallback_date=observation_date)
                source_record_id = str(
                    record.get("url")
                    or f"oilchem_weekly_refinery_metrics:{record.get('metric_type')}:{observation_date}"
                )
                payload_hash = self._payload_hash(record)
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id,
                            source_record_id,
                            topic,
                            source_event_time,
                            payload,
                            payload_hash,
                            dt
                        )
                        values (
                            :source_id,
                            :source_record_id,
                            :topic,
                            :source_event_time,
                            cast(:payload as jsonb),
                            :payload_hash,
                            :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "weekly_refinery_metrics",
                        "source_event_time": publish_time,
                        "payload": json.dumps(record, ensure_ascii=False),
                        "payload_hash": payload_hash,
                        "dt": observation_date,
                    },
                )
                if not entity_id:
                    continue
                for indicator_code, meta in indicator_meta.items():
                    value = record.get(meta["value_field"])
                    if value is None:
                        continue
                    indicator_id = indicator_id_map.get(indicator_code)
                    if not indicator_id:
                        continue
                    result = connection.execute(
                        text(
                            f"""
                            insert into {self._fqtn('fact_market_timeseries')} (
                                indicator_id,
                                entity_id,
                                observation_time,
                                publish_time,
                                freq,
                                value_num,
                                value_text,
                                unit,
                                currency,
                                source_id,
                                source_record_id,
                                is_final,
                                revision_no,
                                quality_flag,
                                effective_from,
                                effective_to,
                                dt
                            )
                            values (
                                :indicator_id,
                                :entity_id,
                                :observation_time,
                                :publish_time,
                                :freq,
                                :value_num,
                                :value_text,
                                :unit,
                                :currency,
                                :source_id,
                                :source_record_id,
                                :is_final,
                                :revision_no,
                                :quality_flag,
                                :effective_from,
                                :effective_to,
                                :dt
                            )
                            on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                            do update set
                                publish_time = excluded.publish_time,
                                value_num = excluded.value_num,
                                source_record_id = excluded.source_record_id,
                                quality_flag = excluded.quality_flag,
                                effective_from = excluded.effective_from,
                                dt = excluded.dt
                            """
                        ),
                        {
                            "indicator_id": indicator_id,
                            "entity_id": entity_id,
                            "observation_time": datetime.combine(observation_date, time(0, 0)),
                            "publish_time": publish_time,
                            "freq": "weekly",
                            "value_num": float(value),
                            "value_text": None,
                            "unit": meta["unit"],
                            "currency": meta["currency"],
                            "source_id": source_id,
                            "source_record_id": source_record_id,
                            "is_final": True,
                            "revision_no": 1,
                            "quality_flag": "ok",
                            "effective_from": publish_time,
                            "effective_to": None,
                            "dt": observation_date,
                        },
                    )
                    saved += int(result.rowcount or 0)
        return saved

    def save_oilchem_maintenance_plan_records(
        self,
        records: list[dict[str, Any]],
        *,
        source_code: str = "oilchem_refinery_maintenance_plan",
        entity_code: str = "SHANDONG_REFINERY",
        entity_name: str = "山东地炼",
        indicator_prefix: str = "oilchem_shandong_maintenance",
    ) -> int:
        if not self.engine or not records:
            return 0

        indicator_meta = {
            f"{indicator_prefix}_active_capacity": {
                "indicator_name": "山东地炼当前检修产能",
                "unit": "万吨/年",
                "value_field": "active_capacity",
            },
            f"{indicator_prefix}_active_count": {
                "indicator_name": "山东地炼当前检修装置数量",
                "unit": "个",
                "value_field": "active_count",
            },
            f"{indicator_prefix}_next_30d_start_capacity": {
                "indicator_name": "山东地炼未来30天新增检修产能",
                "unit": "万吨/年",
                "value_field": "next_30d_start_capacity",
            },
            f"{indicator_prefix}_next_30d_start_count": {
                "indicator_name": "山东地炼未来30天新增检修装置数量",
                "unit": "个",
                "value_field": "next_30d_start_count",
            },
            f"{indicator_prefix}_next_30d_end_capacity": {
                "indicator_name": "山东地炼未来30天复产产能",
                "unit": "万吨/年",
                "value_field": "next_30d_end_capacity",
            },
            f"{indicator_prefix}_next_30d_end_count": {
                "indicator_name": "山东地炼未来30天复产装置数量",
                "unit": "个",
                "value_field": "next_30d_end_count",
            },
        }
        indicator_rows = [
            {
                "indicator_code": code,
                "indicator_name": meta["indicator_name"],
                "category": "refined_oil",
                "sub_category": "maintenance_plan",
                "unit": meta["unit"],
                "freq": "weekly",
                "value_type": "number",
                "fill_policy_default": "latest_available",
                "description": f"隆众资讯{entity_name}装置检修计划表聚合指标",
                "entity_code": entity_code,
                "entity_name": entity_name,
                "entity_type": "refinery_group",
                "region_level": "country" if entity_code == "MAIN_REFINERY" else "province",
                "product_family": "REFINED_OIL",
            }
            for code, meta in indicator_meta.items()
        ]

        saved = 0
        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {source_code})
            source_id = source_ids[source_code]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, indicator_rows)
            rows = list(
                connection.execute(
                    text(
                        f"""
                        select
                            i.indicator_id,
                            i.indicator_code,
                            e.entity_id,
                            e.entity_code
                        from {self._fqtn('dim_indicator')} i
                        join {self._fqtn('dim_entity')} e
                          on 1 = 1
                        where i.indicator_code in :indicator_codes
                          and e.entity_code = :entity_code
                        """
                    ).bindparams(bindparam("indicator_codes", expanding=True)),
                    {
                        "indicator_codes": list(indicator_meta.keys()),
                        "entity_code": entity_code,
                    },
                ).mappings()
            )
            indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
            entity_id = int(rows[0]["entity_id"]) if rows else None

            for record in records:
                observation_date = self._extract_item_date(record) or date.today()
                publish_time = self._normalize_timestamp(record.get("publish_time"), fallback_date=observation_date)
                source_record_id = str(record.get("url") or f"{source_code}:{observation_date}")
                payload_hash = self._payload_hash(record)
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id,
                            source_record_id,
                            topic,
                            source_event_time,
                            payload,
                            payload_hash,
                            dt
                        )
                        values (
                            :source_id,
                            :source_record_id,
                            :topic,
                            :source_event_time,
                            cast(:payload as jsonb),
                            :payload_hash,
                            :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "refinery_maintenance_plan",
                        "source_event_time": publish_time,
                        "payload": json.dumps(record, ensure_ascii=False),
                        "payload_hash": payload_hash,
                        "dt": observation_date,
                    },
                )
                if not entity_id:
                    continue
                for indicator_code, meta in indicator_meta.items():
                    value = record.get(meta["value_field"])
                    if value is None:
                        continue
                    indicator_id = indicator_id_map.get(indicator_code)
                    if not indicator_id:
                        continue
                    result = connection.execute(
                        text(
                            f"""
                            insert into {self._fqtn('fact_market_timeseries')} (
                                indicator_id,
                                entity_id,
                                observation_time,
                                publish_time,
                                freq,
                                value_num,
                                value_text,
                                unit,
                                currency,
                                source_id,
                                source_record_id,
                                is_final,
                                revision_no,
                                quality_flag,
                                effective_from,
                                effective_to,
                                dt
                            )
                            values (
                                :indicator_id,
                                :entity_id,
                                :observation_time,
                                :publish_time,
                                :freq,
                                :value_num,
                                :value_text,
                                :unit,
                                :currency,
                                :source_id,
                                :source_record_id,
                                :is_final,
                                :revision_no,
                                :quality_flag,
                                :effective_from,
                                :effective_to,
                                :dt
                            )
                            on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                            do update set
                                publish_time = excluded.publish_time,
                                value_num = excluded.value_num,
                                source_record_id = excluded.source_record_id,
                                quality_flag = excluded.quality_flag,
                                effective_from = excluded.effective_from,
                                dt = excluded.dt
                            """
                        ),
                        {
                            "indicator_id": indicator_id,
                            "entity_id": entity_id,
                            "observation_time": datetime.combine(observation_date, time(0, 0)),
                            "publish_time": publish_time,
                            "freq": "weekly",
                            "value_num": float(value),
                            "value_text": None,
                            "unit": meta["unit"],
                            "currency": None,
                            "source_id": source_id,
                            "source_record_id": source_record_id,
                            "is_final": True,
                            "revision_no": 1,
                            "quality_flag": "ok",
                            "effective_from": publish_time,
                            "effective_to": None,
                            "dt": observation_date,
                        },
                    )
                    saved += int(result.rowcount or 0)
        return saved

    def save_oilchem_inventory_records(self, records: list[dict[str, Any]]) -> int:
        if not self.engine or not records:
            return 0

        indicator_meta = {
            "oilchem_shandong_refinery_product_inventory_total": {
                "indicator_name": "山东独立炼厂汽柴油库存总量",
                "unit": "万吨",
                "value_field": "total_inventory",
            },
            "oilchem_shandong_refinery_gasoline_inventory": {
                "indicator_name": "山东独立炼厂汽油库存",
                "unit": "万吨",
                "value_field": "gasoline_inventory",
            },
            "oilchem_shandong_refinery_gasoline_inventory_change_mom": {
                "indicator_name": "山东独立炼厂汽油库存环比",
                "unit": "万吨",
                "value_field": "gasoline_inventory_change_mom",
            },
            "oilchem_shandong_refinery_gasoline_inventory_capacity_rate": {
                "indicator_name": "山东独立炼厂汽油库容率",
                "unit": "%",
                "value_field": "gasoline_inventory_capacity_rate",
            },
            "oilchem_shandong_refinery_diesel_inventory": {
                "indicator_name": "山东独立炼厂柴油库存",
                "unit": "万吨",
                "value_field": "diesel_inventory",
            },
            "oilchem_shandong_refinery_diesel_inventory_change_mom": {
                "indicator_name": "山东独立炼厂柴油库存环比",
                "unit": "万吨",
                "value_field": "diesel_inventory_change_mom",
            },
            "oilchem_shandong_refinery_diesel_inventory_capacity_rate": {
                "indicator_name": "山东独立炼厂柴油库容率",
                "unit": "%",
                "value_field": "diesel_inventory_capacity_rate",
            },
        }
        indicator_rows = [
            {
                "indicator_code": code,
                "indicator_name": meta["indicator_name"],
                "category": "refined_oil",
                "sub_category": "refinery_inventory",
                "unit": meta["unit"],
                "freq": "monthly",
                "value_type": "number",
                "fill_policy_default": "latest_available",
                "description": "隆众资讯山东独立炼厂成品油库存统计正文解析指标",
                "entity_code": "SHANDONG_REFINERY",
                "entity_name": "山东独立炼厂",
                "entity_type": "refinery_group",
                "region_level": "province",
                "product_family": "REFINED_OIL",
            }
            for code, meta in indicator_meta.items()
        ]

        saved = 0
        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {"oilchem_refinery_inventory"})
            source_id = source_ids["oilchem_refinery_inventory"]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, indicator_rows)
            rows = list(
                connection.execute(
                    text(
                        f"""
                        select
                            i.indicator_id,
                            i.indicator_code,
                            e.entity_id,
                            e.entity_code
                        from {self._fqtn('dim_indicator')} i
                        join {self._fqtn('dim_entity')} e
                          on 1 = 1
                        where i.indicator_code in :indicator_codes
                          and e.entity_code = :entity_code
                        """
                    ).bindparams(bindparam("indicator_codes", expanding=True)),
                    {
                        "indicator_codes": list(indicator_meta.keys()),
                        "entity_code": "SHANDONG_REFINERY",
                    },
                ).mappings()
            )
            indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
            entity_id = int(rows[0]["entity_id"]) if rows else None

            for record in records:
                observation_date = self._extract_item_date(record) or date.today()
                publish_time = self._normalize_timestamp(record.get("publish_time"), fallback_date=observation_date)
                source_record_id = str(record.get("url") or f"oilchem_refinery_inventory:{observation_date}")
                payload_hash = self._payload_hash(record)
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id,
                            source_record_id,
                            topic,
                            source_event_time,
                            payload,
                            payload_hash,
                            dt
                        )
                        values (
                            :source_id,
                            :source_record_id,
                            :topic,
                            :source_event_time,
                            cast(:payload as jsonb),
                            :payload_hash,
                            :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "refinery_inventory",
                        "source_event_time": publish_time,
                        "payload": json.dumps(record, ensure_ascii=False),
                        "payload_hash": payload_hash,
                        "dt": observation_date,
                    },
                )
                if not entity_id:
                    continue
                for indicator_code, meta in indicator_meta.items():
                    value = record.get(meta["value_field"])
                    if value is None:
                        continue
                    indicator_id = indicator_id_map.get(indicator_code)
                    if not indicator_id:
                        continue
                    result = connection.execute(
                        text(
                            f"""
                            insert into {self._fqtn('fact_market_timeseries')} (
                                indicator_id,
                                entity_id,
                                observation_time,
                                publish_time,
                                freq,
                                value_num,
                                value_text,
                                unit,
                                currency,
                                source_id,
                                source_record_id,
                                is_final,
                                revision_no,
                                quality_flag,
                                effective_from,
                                effective_to,
                                dt
                            )
                            values (
                                :indicator_id,
                                :entity_id,
                                :observation_time,
                                :publish_time,
                                :freq,
                                :value_num,
                                :value_text,
                                :unit,
                                :currency,
                                :source_id,
                                :source_record_id,
                                :is_final,
                                :revision_no,
                                :quality_flag,
                                :effective_from,
                                :effective_to,
                                :dt
                            )
                            on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                            do update set
                                publish_time = excluded.publish_time,
                                value_num = excluded.value_num,
                                source_record_id = excluded.source_record_id,
                                quality_flag = excluded.quality_flag,
                                effective_from = excluded.effective_from,
                                dt = excluded.dt
                            """
                        ),
                        {
                            "indicator_id": indicator_id,
                            "entity_id": entity_id,
                            "observation_time": datetime.combine(observation_date, time(0, 0)),
                            "publish_time": publish_time,
                            "freq": "monthly",
                            "value_num": float(value),
                            "value_text": None,
                            "unit": meta["unit"],
                            "currency": None,
                            "source_id": source_id,
                            "source_record_id": source_record_id,
                            "is_final": True,
                            "revision_no": 1,
                            "quality_flag": "ok",
                            "effective_from": publish_time,
                            "effective_to": None,
                            "dt": observation_date,
                        },
                    )
                    saved += int(result.rowcount or 0)
        return saved

    def save_oilchem_openapi_inventory_records(self, records: list[dict[str, Any]]) -> int:
        if not self.engine or not records:
            return 0

        indicator_rows: list[dict[str, Any]] = []
        entity_rows: list[dict[str, Any]] = []
        indicator_seen: set[str] = set()
        entity_seen: set[str] = set()
        normalized_records: list[dict[str, Any]] = []

        for record in records:
            project_quota_id = str(record.get("project_quota_id") or "").strip()
            quota_sample_id = str(record.get("quota_sample_id") or "").strip()
            if not project_quota_id or not quota_sample_id:
                continue
            indicator_code = f"oilchem_openapi_inventory_{project_quota_id}"
            sample_id = str(record.get("sample_id") or quota_sample_id).strip()
            entity_code = f"OILCHEM_REGION_{sample_id or quota_sample_id}"
            breed_name = str(record.get("breed_name") or "")
            quota_name = str(record.get("quota_name") or "库存量")
            custom = str(record.get("custom") or "").strip()
            sample_name = str(record.get("sample_name") or entity_code)
            unit = str(record.get("unit_name") or "万吨")
            freq = str(record.get("freq_label") or "weekly")
            product_family = "GASOLINE" if "汽油" in breed_name else "DIESEL" if "柴油" in breed_name else "REFINED_OIL"
            region_level = "province" if "山东" in sample_name else "region"

            if indicator_code not in indicator_seen:
                indicator_seen.add(indicator_code)
                display_name = f"{breed_name}{quota_name}"
                if custom:
                    display_name = f"{display_name}（{custom}）"
                indicator_rows.append(
                    {
                        "indicator_code": indicator_code,
                        "indicator_name": display_name,
                        "category": "refined_oil",
                        "sub_category": "purchased_inventory",
                        "unit": unit,
                        "freq": freq,
                        "value_type": "number",
                        "fill_policy_default": "latest_available",
                        "description": "隆众 OpenAPI 已购库存调研指标",
                    }
                )
            if entity_code not in entity_seen:
                entity_seen.add(entity_code)
                entity_rows.append(
                    {
                        "entity_code": entity_code,
                        "entity_name": sample_name,
                        "entity_type": "region",
                        "region_level": region_level,
                        "product_family": product_family,
                    }
                )
            normalized_records.append(
                {
                    **record,
                    "indicator_code": indicator_code,
                    "entity_code": entity_code,
                    "unit": unit,
                    "freq": freq,
                }
            )

        if not normalized_records:
            return 0

        saved = 0
        with self.engine.begin() as connection:
            source_ids = self._ensure_source_ids(connection, {"oilchem_openapi_inventory"})
            source_id = source_ids["oilchem_openapi_inventory"]
            self._ensure_indicators(connection, indicator_rows)
            self._ensure_entities(connection, entity_rows)
            rows = connection.execute(
                text(
                    f"""
                    select i.indicator_id, i.indicator_code
                    from {self._fqtn('dim_indicator')} i
                    where i.indicator_code in :indicator_codes
                    """
                ).bindparams(bindparam("indicator_codes", expanding=True)),
                {"indicator_codes": sorted(indicator_seen)},
            ).mappings().all()
            indicator_id_map = {str(row["indicator_code"]): int(row["indicator_id"]) for row in rows}
            entity_rows_db = connection.execute(
                text(
                    f"""
                    select e.entity_id, e.entity_code
                    from {self._fqtn('dim_entity')} e
                    where e.entity_code in :entity_codes
                    """
                ).bindparams(bindparam("entity_codes", expanding=True)),
                {"entity_codes": sorted(entity_seen)},
            ).mappings().all()
            entity_id_map = {str(row["entity_code"]): int(row["entity_id"]) for row in entity_rows_db}

            for record in normalized_records:
                value = record.get("value")
                if value is None:
                    continue
                observation_date = self._coerce_date(
                    record.get("observation_date") or record.get("period_end") or record.get("period_start")
                ) or date.today()
                publish_time = self._normalize_timestamp(record.get("publish_time"), fallback_date=observation_date)
                source_record_id = (
                    f"oilchem_openapi_inventory:{record.get('project_quota_id')}:"
                    f"{record.get('quota_sample_id')}:{observation_date.isoformat()}"
                )
                payload_hash = self._payload_hash(record)
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('ods_raw_market')} (
                            source_id,
                            source_record_id,
                            topic,
                            source_event_time,
                            payload,
                            payload_hash,
                            dt
                        )
                        values (
                            :source_id,
                            :source_record_id,
                            :topic,
                            :source_event_time,
                            cast(:payload as jsonb),
                            :payload_hash,
                            :dt
                        )
                        on conflict (source_id, source_record_id, payload_hash) do nothing
                        """
                    ),
                    {
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "topic": "purchased_inventory",
                        "source_event_time": publish_time,
                        "payload": json.dumps(record, ensure_ascii=False),
                        "payload_hash": payload_hash,
                        "dt": observation_date,
                    },
                )
                indicator_id = indicator_id_map.get(str(record["indicator_code"]))
                entity_id = entity_id_map.get(str(record["entity_code"]))
                if not indicator_id or not entity_id:
                    continue
                result = connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('fact_market_timeseries')} (
                            indicator_id,
                            entity_id,
                            observation_time,
                            publish_time,
                            freq,
                            value_num,
                            value_text,
                            unit,
                            currency,
                            source_id,
                            source_record_id,
                            is_final,
                            revision_no,
                            quality_flag,
                            effective_from,
                            effective_to,
                            dt
                        )
                        values (
                            :indicator_id,
                            :entity_id,
                            :observation_time,
                            :publish_time,
                            :freq,
                            :value_num,
                            :value_text,
                            :unit,
                            :currency,
                            :source_id,
                            :source_record_id,
                            :is_final,
                            :revision_no,
                            :quality_flag,
                            :effective_from,
                            :effective_to,
                            :dt
                        )
                        on conflict (indicator_id, entity_id, observation_time, revision_no, source_id)
                        do update set
                            publish_time = excluded.publish_time,
                            value_num = excluded.value_num,
                            source_record_id = excluded.source_record_id,
                            quality_flag = excluded.quality_flag,
                            effective_from = excluded.effective_from,
                            dt = excluded.dt
                        """
                    ),
                    {
                        "indicator_id": indicator_id,
                        "entity_id": entity_id,
                        "observation_time": datetime.combine(observation_date, time(0, 0)),
                        "publish_time": publish_time,
                        "freq": record.get("freq") or "weekly",
                        "value_num": float(value),
                        "value_text": None,
                        "unit": record.get("unit") or "万吨",
                        "currency": None,
                        "source_id": source_id,
                        "source_record_id": source_record_id,
                        "is_final": True,
                        "revision_no": 1,
                        "quality_flag": "ok",
                        "effective_from": publish_time,
                        "effective_to": None,
                        "dt": observation_date,
                    },
                )
                saved += int(result.rowcount or 0)
        return saved

    def load_oilchem_openapi_inventory_records(
        self,
        *,
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        if not self.engine:
            return []
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    select
                        i.indicator_code,
                        i.indicator_name,
                        e.entity_code,
                        e.entity_name,
                        f.observation_time,
                        f.publish_time,
                        f.value_num,
                        f.unit,
                        f.freq,
                        f.source_record_id,
                        f.dt
                    from {self._fqtn('fact_market_timeseries')} f
                    join {self._fqtn('dim_indicator')} i
                      on i.indicator_id = f.indicator_id
                    join {self._fqtn('dim_entity')} e
                      on e.entity_id = f.entity_id
                    join {self._fqtn('dim_source')} ds
                      on ds.source_id = f.source_id
                    where ds.source_code = 'oilchem_openapi_inventory'
                      and f.dt between :start_date and :end_date
                    order by f.dt desc, i.indicator_code asc, e.entity_code asc
                    """
                ),
                {"start_date": start_date, "end_date": end_date},
            ).mappings().all()
        return [
            {
                "indicator_code": str(row["indicator_code"]),
                "indicator_name": str(row["indicator_name"]),
                "entity_code": str(row["entity_code"]),
                "entity_name": str(row["entity_name"]),
                "observation_time": row["observation_time"],
                "publish_time": row["publish_time"],
                "value": float(row["value_num"]) if row["value_num"] is not None else None,
                "unit": str(row["unit"] or ""),
                "freq": str(row["freq"] or ""),
                "source_record_id": str(row["source_record_id"]),
                "dt": row["dt"],
                "project_quota_id": self._extract_project_quota_id(str(row["indicator_code"])),
            }
            for row in rows
        ]

    def list_freight_settings(self) -> list[dict[str, Any]]:
        if not self.engine:
            return []
        with self.engine.begin() as connection:
            self._ensure_freight_settings(connection)
            rows = connection.execute(
                text(
                    f"""
                    select region_code, region_name, freight_value, unit, source_type, updated_by, updated_at
                    from {self._fqtn('regional_freight_setting')}
                    order by region_code asc
                    """
                )
            ).mappings().all()
        return [
            {
                "region_code": str(row["region_code"]),
                "region_name": str(row["region_name"]),
                "freight_value": float(row["freight_value"]),
                "unit": str(row["unit"]),
                "source_type": str(row["source_type"]),
                "updated_by": row["updated_by"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def upsert_freight_setting(
        self,
        *,
        region_code: str,
        region_name: str,
        freight_value: float,
        updated_by: str | None,
    ) -> dict[str, Any]:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        with self.engine.begin() as connection:
            self._ensure_freight_settings(connection)
            row = connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('regional_freight_setting')} (
                        region_code, region_name, freight_value, unit, source_type, updated_by
                    )
                    values (
                        :region_code, :region_name, :freight_value, '元/吨', 'manual', :updated_by
                    )
                    on conflict (region_code) do update
                    set
                        region_name = excluded.region_name,
                        freight_value = excluded.freight_value,
                        unit = excluded.unit,
                        source_type = excluded.source_type,
                        updated_by = excluded.updated_by,
                        updated_at = now()
                    returning region_code, region_name, freight_value, unit, source_type, updated_by, updated_at
                    """
                ),
                {
                    "region_code": region_code,
                    "region_name": region_name,
                    "freight_value": freight_value,
                    "updated_by": updated_by,
                },
            ).mappings().one()
        return {
            "region_code": str(row["region_code"]),
            "region_name": str(row["region_name"]),
            "freight_value": float(row["freight_value"]),
            "unit": str(row["unit"]),
            "source_type": str(row["source_type"]),
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }

    def save_prediction_run(self, prediction: Any) -> int | None:
        if not self.engine:
            return None
        payload = prediction.model_dump(mode="json") if hasattr(prediction, "model_dump") else dict(prediction)
        input_hash = (payload.get("raw_context") or {}).get("input_hash")
        entity_row = {
            "entity_code": payload.get("entity_code") or payload.get("region_code") or "UNKNOWN",
            "entity_name": payload.get("region_code") or payload.get("entity_code") or "UNKNOWN",
            "entity_type": "prediction_target",
            "region_level": "region",
            "product_family": payload.get("product_code") or "GASOLINE_92",
        }
        probabilities = (payload.get("raw_context") or {}).get("probabilities") or {}
        prediction_type = "point" if payload.get("product_code") != "GASOLINE_92_SPREAD" else "range"
        with self.engine.begin() as connection:
            self._ensure_prediction_extensions(connection)
            self._ensure_entities(connection, [entity_row])
            entity_id = connection.execute(
                text(f"select entity_id from {self._fqtn('dim_entity')} where entity_code = :entity_code"),
                {"entity_code": entity_row["entity_code"]},
            ).scalar_one()
            if input_hash:
                existing_id = connection.execute(
                    text(f"select prediction_id from {self._fqtn('prediction_run')} where input_hash = :input_hash"),
                    {"input_hash": input_hash},
                ).scalar()
                if existing_id:
                    return int(existing_id)
            prediction_id = connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('prediction_run')} (
                        run_id, entity_id, product_code, region_code, horizon, prediction_type,
                        as_of_time, target_start_time, target_end_time, direction_label,
                        prob_up, prob_flat, prob_down, point_value, range_lower, range_upper,
                        confidence_label, confidence_score, degrade_flag, degrade_reason,
                        publish_status, published_at, input_hash, model_version,
                        runtime_control_snapshot, raw_context
                    )
                    values (
                        :run_id, :entity_id, :product_code, :region_code, :horizon, :prediction_type,
                        cast(:as_of_time as timestamptz), cast(:target_start_time as timestamptz), cast(:target_end_time as timestamptz), :direction_label,
                        :prob_up, :prob_flat, :prob_down, :point_value, :range_lower, :range_upper,
                        :confidence_label, :confidence_score, :degrade_flag, :degrade_reason,
                        'published', now(), :input_hash, :model_version,
                        cast(:runtime_control_snapshot as jsonb), cast(:raw_context as jsonb)
                    )
                    returning prediction_id
                    """
                ),
                {
                    "run_id": payload.get("run_id"),
                    "entity_id": int(entity_id),
                    "product_code": payload.get("product_code"),
                    "region_code": payload.get("region_code"),
                    "horizon": payload.get("horizon"),
                    "prediction_type": prediction_type,
                    "as_of_time": payload.get("as_of_date"),
                    "target_start_time": payload.get("target_date"),
                    "target_end_time": payload.get("target_date"),
                    "direction_label": payload.get("direction_label"),
                    "prob_up": probabilities.get("up"),
                    "prob_flat": probabilities.get("flat"),
                    "prob_down": probabilities.get("down"),
                    "point_value": payload.get("point_value"),
                    "range_lower": payload.get("range_lower"),
                    "range_upper": payload.get("range_upper"),
                    "confidence_label": payload.get("confidence_label"),
                    "confidence_score": payload.get("confidence_score"),
                    "degrade_flag": payload.get("degrade_flag"),
                    "degrade_reason": payload.get("degrade_reason"),
                    "input_hash": input_hash,
                    "model_version": "expert-prior-fixed-mapping-v2",
                    "runtime_control_snapshot": json.dumps((payload.get("raw_context") or {}).get("runtime_controls") or {}, ensure_ascii=False),
                    "raw_context": json.dumps(payload.get("raw_context") or {}, ensure_ascii=False),
                },
            ).scalar_one()
            factor_rows = []
            for item in payload.get("factor_breakdown") or []:
                factor_rows.append(
                    {
                        "prediction_id": int(prediction_id),
                        "factor_group": item.get("factor_group") or item.get("factor_name") or "unknown",
                        "factor_name": item.get("factor_name") or "unknown",
                        "factor_value": item.get("factor_value"),
                        "factor_score": item.get("factor_score"),
                        "weight": item.get("weight"),
                        "contribution": item.get("contribution"),
                        "evidence_ref": json.dumps(item.get("evidence") or [], ensure_ascii=False),
                    }
                )
            if factor_rows:
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('prediction_factor_breakdown')} (
                            prediction_id, factor_group, factor_name, factor_value,
                            factor_score, weight, contribution, evidence_ref
                        )
                        values (
                            :prediction_id, :factor_group, :factor_name, :factor_value,
                            :factor_score, :weight, :contribution, cast(:evidence_ref as jsonb)
                        )
                        """
                    ),
                    factor_rows,
                )
            agent_rows = []
            for claim in payload.get("agent_claims") or []:
                agent_rows.append(
                    {
                        "run_id": payload.get("run_id"),
                        "agent_name": claim.get("agent_name") or "unknown",
                        "input_context": json.dumps(payload.get("raw_context") or {}, ensure_ascii=False),
                        "claim_json": json.dumps(claim, ensure_ascii=False),
                        "status": "success",
                        "started_at": datetime.now(timezone.utc),
                        "finished_at": datetime.now(timezone.utc),
                    }
                )
            if agent_rows:
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('agent_run_log')} (
                            run_id, agent_name, input_context, claim_json,
                            status, started_at, finished_at
                        )
                        values (
                            :run_id, :agent_name, cast(:input_context as jsonb), cast(:claim_json as jsonb),
                            :status, :started_at, :finished_at
                        )
                        """
                    ),
                    agent_rows,
                )
            label_rows = []
            labels = (payload.get("raw_context") or {}).get("llm_extracted_labels") or {}
            if isinstance(labels, dict):
                for label_type, label_payload in labels.items():
                    if not label_payload:
                        continue
                    label_rows.append(
                        {
                            "prediction_id": int(prediction_id),
                            "run_id": payload.get("run_id"),
                            "label_type": str(label_type),
                            "label_payload": json.dumps(label_payload, ensure_ascii=False),
                            "source": (label_payload or {}).get("source") if isinstance(label_payload, dict) else None,
                        }
                    )
            if label_rows:
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('prediction_llm_label')} (
                            prediction_id, run_id, label_type, label_payload, source
                        )
                        values (
                            :prediction_id, :run_id, :label_type, cast(:label_payload as jsonb), :source
                        )
                        """
                    ),
                    label_rows,
                )
        return int(prediction_id)

    def _ensure_prediction_extensions(self, connection: Any) -> None:
        connection.execute(text(f"alter table {self._fqtn('prediction_run')} add column if not exists input_hash varchar(64)"))
        connection.execute(text(f"alter table {self._fqtn('prediction_run')} add column if not exists model_version varchar(64)"))
        connection.execute(text(f"alter table {self._fqtn('prediction_run')} add column if not exists runtime_control_snapshot jsonb"))
        connection.execute(text(f"alter table {self._fqtn('prediction_run')} add column if not exists raw_context jsonb"))
        connection.execute(
            text(
                f"""
                create table if not exists {self._fqtn('prediction_llm_label')} (
                    label_id bigint generated by default as identity primary key,
                    prediction_id bigint not null references {self._fqtn('prediction_run')}(prediction_id) on delete cascade,
                    run_id varchar(128) not null,
                    label_type varchar(64) not null,
                    label_payload jsonb not null,
                    source varchar(64),
                    created_at timestamptz not null default now()
                )
                """
            )
        )
        connection.execute(
            text(
                f"""
                create index if not exists idx_prediction_llm_label_run
                on {self._fqtn('prediction_llm_label')} (run_id)
                """
            )
        )
        connection.execute(
            text(
                f"""
                create index if not exists idx_prediction_llm_label_type
                on {self._fqtn('prediction_llm_label')} (label_type)
                """
            )
        )
        connection.execute(
            text(
                f"""
                create unique index if not exists idx_prediction_run_input_hash
                on {self._fqtn('prediction_run')} (input_hash)
                where input_hash is not null
                """
            )
        )

    def load_refined_news_items(self, start_date: date, end_date: date) -> RefinedNewsLoadResult:
        return self._load_news_items_by_sources(
            start_date=start_date,
            end_date=end_date,
            source_codes=[
                "oilchem_refinedoil_channel",
                "oilchem_shandong_spot_daily_report",
                "cnenergy_oil_gas_fulltext",
                "jlc_refinedoil_hot_browser",
                "jlc_refinedoil_archive_browser",
            ],
        )

    def load_policy_items(self, start_date: date, end_date: date) -> PolicyLoadResult:
        if not self.engine:
            return PolicyLoadResult(items=[], source_counts={}, archive_start=None, archive_end=None)

        start_ts, end_ts_exclusive = self._build_datetime_range(start_date, end_date)
        statement = text(
            f"""
            select
                ds.source_code,
                m.source_event_time,
                m.payload
            from {self._fqtn('ods_raw_market')} m
            join {self._fqtn('dim_source')} ds
              on ds.source_id = m.source_id
            where m.topic = 'policy_notice'
              and m.source_event_time >= :start_ts
              and m.source_event_time < :end_ts_exclusive
            order by m.source_event_time desc
            """
        )

        items: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        archive_dates: list[date] = []
        with self.engine.begin() as connection:
            rows = connection.execute(
                statement,
                {
                    "start_ts": start_ts,
                    "end_ts_exclusive": end_ts_exclusive,
                },
            ).mappings()
            for row in rows:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                item = dict(payload or {})
                item.setdefault("source", row["source_code"])
                event_time = row["source_event_time"]
                if isinstance(event_time, datetime):
                    event_date = event_time.date()
                    archive_dates.append(event_date)
                    item.setdefault("effective_time", event_time.strftime("%Y-%m-%d %H:%M"))
                else:
                    event_date = self._extract_item_date(item)
                    if event_date is not None:
                        archive_dates.append(event_date)
                items.append(item)
                source_code = str(row["source_code"])
                source_counts[source_code] = source_counts.get(source_code, 0) + 1

        return PolicyLoadResult(
            items=items,
            source_counts=source_counts,
            archive_start=min(archive_dates) if archive_dates else None,
            archive_end=max(archive_dates) if archive_dates else None,
        )

    def load_jinshi_news_items(self, start_date: date, end_date: date) -> RefinedNewsLoadResult:
        return self._load_news_items_by_sources(
            start_date=start_date,
            end_date=end_date,
            source_codes=["jinshi_crude_news"],
        )

    def load_brent_reports(self, start_date: date, end_date: date) -> ReportLoadResult:
        if not self.engine:
            return ReportLoadResult(items=[], source_counts={}, archive_start=None, archive_end=None)

        statement = text(
            f"""
            select
                ds.source_code,
                f.report_date,
                f.report_title,
                f.payload,
                f.markdown_body
            from {self._fqtn('ods_raw_forecast')} f
            join {self._fqtn('dim_source')} ds
              on ds.source_id = f.source_id
            where f.report_date between :start_date and :end_date
              and ds.source_code = 'brent_daily_report'
            order by f.report_date desc
            """
        )

        items: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        archive_dates: list[date] = []
        with self.engine.begin() as connection:
            rows = connection.execute(
                statement,
                {
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).mappings()
            for row in rows:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                item = dict(payload or {})
                item.setdefault("source", row["source_code"])
                item.setdefault("title", row["report_title"])
                item.setdefault("markdown", row["markdown_body"])
                report_date = row["report_date"]
                if isinstance(report_date, date):
                    item.setdefault("report_date", report_date.isoformat())
                    archive_dates.append(report_date)
                items.append(item)
                source_code = str(row["source_code"])
                source_counts[source_code] = source_counts.get(source_code, 0) + 1

        return ReportLoadResult(
            items=items,
            source_counts=source_counts,
            archive_start=min(archive_dates) if archive_dates else None,
            archive_end=max(archive_dates) if archive_dates else None,
        )

    def load_latest_raw_market_payloads(
        self,
        *,
        source_codes: list[str],
        end_date: date,
        limit_per_source: int = 1,
        lookback_days: int = 90,
    ) -> dict[str, list[dict[str, Any]]]:
        if not self.engine or not source_codes:
            return {}
        start_date = end_date - timedelta(days=lookback_days)
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    select source_code, payload, source_event_time, dt
                    from (
                        select
                            ds.source_code,
                            m.payload,
                            m.source_event_time,
                            m.dt,
                            row_number() over (
                                partition by ds.source_code
                                order by m.dt desc, m.source_event_time desc
                            ) as rn
                        from {self._fqtn('ods_raw_market')} m
                        join {self._fqtn('dim_source')} ds
                          on ds.source_id = m.source_id
                        where ds.source_code in :source_codes
                          and m.dt between :start_date and :end_date
                    ) ranked
                    where rn <= :limit_per_source
                    order by source_code, dt desc, source_event_time desc
                    """
                ).bindparams(bindparam("source_codes", expanding=True)),
                {
                    "source_codes": source_codes,
                    "start_date": start_date,
                    "end_date": end_date,
                    "limit_per_source": limit_per_source,
                },
            ).mappings().all()
        payloads: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            source_code = str(row["source_code"])
            raw_payload = row["payload"]
            if isinstance(raw_payload, str):
                try:
                    item = json.loads(raw_payload)
                except json.JSONDecodeError:
                    item = {"raw_payload": raw_payload}
            else:
                item = dict(raw_payload or {})
            item.setdefault("source", source_code)
            if row["dt"] and not item.get("observation_date"):
                item["observation_date"] = row["dt"].isoformat()
            if row["source_event_time"] and not item.get("publish_time"):
                item["publish_time"] = row["source_event_time"].isoformat()
            payloads.setdefault(source_code, []).append(item)
        return payloads

    def load_market_timeseries_values(
        self,
        *,
        source_code: str,
        indicator_codes: list[str],
        start_date: date,
        end_date: date,
    ) -> list[dict[str, Any]]:
        if not self.engine or not indicator_codes:
            return []
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"""
                    select
                        i.indicator_code,
                        e.entity_code,
                        f.observation_time,
                        f.publish_time,
                        f.value_num,
                        f.dt
                    from {self._fqtn('fact_market_timeseries')} f
                    join {self._fqtn('dim_indicator')} i
                      on i.indicator_id = f.indicator_id
                    join {self._fqtn('dim_entity')} e
                      on e.entity_id = f.entity_id
                    join {self._fqtn('dim_source')} ds
                      on ds.source_id = f.source_id
                    where ds.source_code = :source_code
                      and i.indicator_code in :indicator_codes
                      and f.dt between :start_date and :end_date
                    order by f.dt asc, i.indicator_code asc, f.publish_time desc
                    """
                ).bindparams(bindparam("indicator_codes", expanding=True)),
                {
                    "source_code": source_code,
                    "indicator_codes": indicator_codes,
                    "start_date": start_date,
                    "end_date": end_date,
                },
            ).mappings().all()
        return [
            {
                "indicator_code": str(row["indicator_code"]),
                "entity_code": str(row["entity_code"]),
                "observation_time": row["observation_time"],
                "publish_time": row["publish_time"],
                "value_num": float(row["value_num"]) if row["value_num"] is not None else None,
                "dt": row["dt"],
            }
            for row in rows
        ]

    def _load_news_items_by_sources(
        self,
        start_date: date,
        end_date: date,
        source_codes: list[str],
    ) -> RefinedNewsLoadResult:
        if not self.engine:
            return RefinedNewsLoadResult(items=[], source_counts={}, archive_start=None, archive_end=None)

        start_ts, end_ts_exclusive = self._build_datetime_range(start_date, end_date)
        statement = (
            text(
                f"""
                select
                    ds.source_code,
                    n.publish_time,
                    n.title,
                    n.content,
                    n.payload
                from {self._fqtn('ods_raw_news')} n
                join {self._fqtn('dim_source')} ds
                  on ds.source_id = n.source_id
                where n.publish_time >= :start_ts
                  and n.publish_time < :end_ts_exclusive
                  and ds.source_code in :source_codes
                order by n.publish_time desc
                """
            ).bindparams(bindparam("source_codes", expanding=True))
        )

        items: list[dict[str, Any]] = []
        source_counts: dict[str, int] = {}
        archive_dates: list[date] = []
        with self.engine.begin() as connection:
            rows = connection.execute(
                statement,
                {
                    "start_ts": start_ts,
                    "end_ts_exclusive": end_ts_exclusive,
                    "source_codes": source_codes,
                },
            ).mappings()
            for row in rows:
                payload = row["payload"]
                if isinstance(payload, str):
                    payload = json.loads(payload)
                item = dict(payload or {})
                item.setdefault("source", row["source_code"])
                item.setdefault("headline", row["title"])
                item.setdefault("title", row["title"])
                item.setdefault("content", row["content"])
                publish_time = row["publish_time"]
                if isinstance(publish_time, datetime):
                    item.setdefault("publish_time", publish_time.strftime("%Y-%m-%d %H:%M"))
                    archive_dates.append(publish_time.date())
                items.append(item)
                source_code = str(row["source_code"])
                source_counts[source_code] = source_counts.get(source_code, 0) + 1

        return RefinedNewsLoadResult(
            items=items,
            source_counts=source_counts,
            archive_start=min(archive_dates) if archive_dates else None,
            archive_end=max(archive_dates) if archive_dates else None,
        )

    def _ensure_source_ids(self, connection: Any, source_codes: set[str]) -> dict[str, int]:
        normalized_codes = sorted(code for code in source_codes if code)
        if not normalized_codes:
            return {}

        seed_rows = []
        for code in normalized_codes:
            meta = SOURCE_DEFINITIONS.get(
                code,
                {
                    "source_name": code,
                    "source_type": "custom",
                    "priority": 100,
                },
            )
            seed_rows.append(
                {
                    "source_code": code,
                    "source_name": meta["source_name"],
                    "source_type": meta["source_type"],
                    "priority": meta["priority"],
                }
            )

        connection.execute(
            text(
                f"""
                insert into {self._fqtn('dim_source')} (
                    source_code,
                    source_name,
                    source_type,
                    priority
                )
                values (
                    :source_code,
                    :source_name,
                    :source_type,
                    :priority
                )
                on conflict (source_code) do update
                set
                    source_name = excluded.source_name,
                    source_type = excluded.source_type,
                    priority = excluded.priority,
                    updated_at = now()
                """
            ),
            seed_rows,
        )

        rows = connection.execute(
            text(
                f"""
                select source_id, source_code
                from {self._fqtn('dim_source')}
                where source_code in :source_codes
                """
            ).bindparams(bindparam("source_codes", expanding=True)),
            {"source_codes": normalized_codes},
        ).mappings()
        return {str(row["source_code"]): int(row["source_id"]) for row in rows}

    def _ensure_indicators(self, connection: Any, rows: list[dict[str, Any]]) -> None:
        seed_rows = []
        seen: set[str] = set()
        for row in rows:
            indicator_code = str(row["indicator_code"])
            if indicator_code in seen:
                continue
            seen.add(indicator_code)
            seed_rows.append(
                {
                    "indicator_code": indicator_code,
                    "indicator_name": row["indicator_name"],
                    "category": row["category"],
                    "sub_category": row["sub_category"],
                    "unit": row["unit"],
                    "freq": row["freq"],
                    "value_type": row["value_type"],
                    "fill_policy_default": row["fill_policy_default"],
                    "description": row["description"],
                }
            )
        if not seed_rows:
            return
        connection.execute(
            text(
                f"""
                insert into {self._fqtn('dim_indicator')} (
                    indicator_code,
                    indicator_name,
                    category,
                    sub_category,
                    unit,
                    freq,
                    value_type,
                    fill_policy_default,
                    description
                )
                values (
                    :indicator_code,
                    :indicator_name,
                    :category,
                    :sub_category,
                    :unit,
                    :freq,
                    :value_type,
                    :fill_policy_default,
                    :description
                )
                on conflict (indicator_code) do update
                set
                    indicator_name = excluded.indicator_name,
                    category = excluded.category,
                    sub_category = excluded.sub_category,
                    unit = excluded.unit,
                    freq = excluded.freq,
                    value_type = excluded.value_type,
                    fill_policy_default = excluded.fill_policy_default,
                    description = excluded.description,
                    updated_at = now()
                """
            ),
            seed_rows,
        )

    def _ensure_entities(self, connection: Any, rows: list[dict[str, Any]]) -> None:
        seed_rows = []
        seen: set[str] = set()
        for row in rows:
            entity_code = str(row["entity_code"])
            if entity_code in seen:
                continue
            seen.add(entity_code)
            seed_rows.append(
                {
                    "entity_type": row["entity_type"],
                    "entity_code": entity_code,
                    "entity_name": row["entity_name"],
                    "region_level": row["region_level"],
                    "product_family": row["product_family"],
                }
            )
        if not seed_rows:
            return
        connection.execute(
            text(
                f"""
                insert into {self._fqtn('dim_entity')} (
                    entity_type,
                    entity_code,
                    entity_name,
                    region_level,
                    product_family
                )
                values (
                    :entity_type,
                    :entity_code,
                    :entity_name,
                    :region_level,
                    :product_family
                )
                on conflict (entity_code) do update
                set
                    entity_name = excluded.entity_name,
                    region_level = excluded.region_level,
                    product_family = excluded.product_family,
                    updated_at = now()
                """
            ),
            seed_rows,
        )

    def _ensure_permissions(self, connection: Any) -> None:
        connection.execute(
            text(
                f"""
                insert into {self._fqtn('app_permission')} (
                    permission_code,
                    permission_name,
                    module_code,
                    description
                )
                values (
                    :permission_code,
                    :permission_name,
                    :module_code,
                    :description
                )
                on conflict (permission_code) do update
                set
                    permission_name = excluded.permission_name,
                    module_code = excluded.module_code,
                    description = excluded.description
                """
            ),
            DEFAULT_PERMISSION_DEFINITIONS,
        )

    def list_freight_components(self, defaults: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not self.engine:
            return defaults
        with self.engine.begin() as connection:
            self._ensure_freight_components(connection)
            self._seed_freight_components(connection, defaults)
            rows = connection.execute(
                text(
                    f"""
                    select region_code, region_name, component_key, short_name, route_name,
                           freight_value, unit, display_order, updated_by, updated_at
                    from {self._fqtn('regional_freight_component')}
                    order by region_code asc, display_order asc, component_key asc
                    """
                )
            ).mappings().all()
        return [
            {
                "region_code": str(row["region_code"]),
                "region_name": str(row["region_name"]),
                "component_key": str(row["component_key"]),
                "short_name": str(row["short_name"] or ""),
                "route_name": str(row["route_name"]),
                "freight_value": float(row["freight_value"]),
                "unit": str(row["unit"]),
                "display_order": int(row["display_order"] or 0),
                "updated_by": row["updated_by"],
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def upsert_freight_component(
        self,
        *,
        defaults: list[dict[str, Any]],
        component_key: str,
        freight_value: float,
        updated_by: str | None,
    ) -> dict[str, Any]:
        if not self.engine:
            raise RuntimeError("Database repository is not configured.")
        matched = next((item for item in defaults if item["component_key"] == component_key), None)
        if not matched:
            raise ValueError(f"Unsupported freight component: {component_key}")
        with self.engine.begin() as connection:
            self._ensure_freight_components(connection)
            self._seed_freight_components(connection, defaults)
            row = connection.execute(
                text(
                    f"""
                    update {self._fqtn('regional_freight_component')}
                    set freight_value = :freight_value,
                        unit = '?/?',
                        updated_by = :updated_by,
                        updated_at = now()
                    where component_key = :component_key
                    returning region_code, region_name, component_key, short_name, route_name,
                              freight_value, unit, display_order, updated_by, updated_at
                    """
                ),
                {
                    "component_key": component_key,
                    "freight_value": freight_value,
                    "updated_by": updated_by,
                },
            ).mappings().one()
        return {
            "region_code": str(row["region_code"]),
            "region_name": str(row["region_name"]),
            "component_key": str(row["component_key"]),
            "short_name": str(row["short_name"] or ""),
            "route_name": str(row["route_name"]),
            "freight_value": float(row["freight_value"]),
            "unit": str(row["unit"]),
            "display_order": int(row["display_order"] or 0),
            "updated_by": row["updated_by"],
            "updated_at": row["updated_at"],
        }

    def _ensure_freight_components(self, connection: Any) -> None:
        connection.execute(
            text(
                f"""
                create table if not exists {self._fqtn('regional_freight_component')} (
                    component_key varchar(96) primary key,
                    region_code varchar(64) not null,
                    region_name varchar(128) not null,
                    short_name varchar(128),
                    route_name varchar(256) not null,
                    freight_value numeric(20, 6) not null,
                    unit varchar(32) not null default '?/?',
                    display_order integer not null default 0,
                    updated_by varchar(64),
                    updated_at timestamptz not null default now(),
                    created_at timestamptz not null default now()
                )
                """
            )
        )
        connection.execute(
            text(
                f"""
                create index if not exists idx_regional_freight_component_region
                on {self._fqtn('regional_freight_component')} (region_code, display_order)
                """
            )
        )

    def _seed_freight_components(self, connection: Any, defaults: list[dict[str, Any]]) -> None:
        for index, item in enumerate(defaults, start=1):
            connection.execute(
                text(
                    f"""
                    insert into {self._fqtn('regional_freight_component')} (
                        component_key, region_code, region_name, short_name, route_name,
                        freight_value, unit, display_order, updated_by
                    )
                    values (
                        :component_key, :region_code, :region_name, :short_name, :route_name,
                        :freight_value, '?/?', :display_order, 'system_seed'
                    )
                    on conflict (component_key) do update
                    set region_code = excluded.region_code,
                        region_name = excluded.region_name,
                        short_name = excluded.short_name,
                        route_name = excluded.route_name,
                        unit = coalesce({self._fqtn('regional_freight_component')}.unit, excluded.unit),
                        display_order = excluded.display_order
                    """
                ),
                {
                    "component_key": item["component_key"],
                    "region_code": item["region_code"],
                    "region_name": item["region_name"],
                    "short_name": item.get("short_name"),
                    "route_name": item["route_name"],
                    "freight_value": item["freight_value"],
                    "display_order": index,
                },
            )

    def _ensure_freight_settings(self, connection: Any) -> None:
        connection.execute(
            text(
                f"""
                create table if not exists {self._fqtn('regional_freight_setting')} (
                    region_code varchar(64) primary key,
                    region_name varchar(128) not null,
                    freight_value numeric(20, 6) not null,
                    unit varchar(32) not null default '元/吨',
                    source_type varchar(32) not null default 'manual',
                    updated_by varchar(64),
                    updated_at timestamptz not null default now(),
                    created_at timestamptz not null default now()
                )
                """
            )
        )
        connection.execute(
            text(f"alter table {self._fqtn('regional_freight_setting')} add column if not exists unit varchar(32)")
        )
        connection.execute(
            text(f"alter table {self._fqtn('regional_freight_setting')} add column if not exists source_type varchar(32)")
        )
        connection.execute(
            text(f"alter table {self._fqtn('regional_freight_setting')} add column if not exists updated_by varchar(64)")
        )
        connection.execute(
            text(f"alter table {self._fqtn('regional_freight_setting')} add column if not exists updated_at timestamptz")
        )
        connection.execute(
            text(f"alter table {self._fqtn('regional_freight_setting')} add column if not exists created_at timestamptz")
        )
        connection.execute(
            text(
                f"""
                update {self._fqtn('regional_freight_setting')}
                set
                    unit = coalesce(unit, '元/吨'),
                    source_type = coalesce(source_type, 'manual'),
                    updated_at = coalesce(updated_at, now()),
                    created_at = coalesce(created_at, now())
                where unit is null
                   or source_type is null
                   or updated_at is null
                   or created_at is null
                """
            )
        )
        connection.execute(
            text(
                f"""
                create index if not exists idx_regional_freight_updated
                on {self._fqtn('regional_freight_setting')} (updated_at desc)
                """
            )
        )

    def _ensure_roles(self, connection: Any) -> None:
        self._ensure_permissions(connection)
        for role in DEFAULT_ROLE_DEFINITIONS:
            role_id = int(
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('app_role')} (
                            role_code,
                            role_name,
                            description,
                            is_system,
                            is_active
                        )
                        values (
                            :role_code,
                            :role_name,
                            :description,
                            true,
                            true
                        )
                        on conflict (role_code) do update
                        set
                            role_name = excluded.role_name,
                            description = excluded.description,
                            is_system = true,
                            is_active = true,
                            updated_at = now()
                        returning role_id
                        """
                    ),
                    {
                        "role_code": role["role_code"],
                        "role_name": role["role_name"],
                        "description": role["description"],
                    },
                ).scalar_one()
            )
            permission_codes = sorted({code for code in role["permission_codes"] if code})
            connection.execute(
                text(f"delete from {self._fqtn('app_role_permission')} where role_id = :role_id"),
                {"role_id": role_id},
            )
            permission_rows = connection.execute(
                text(
                    f"""
                    select permission_id
                    from {self._fqtn('app_permission')}
                    where permission_code in :permission_codes
                    """
                ).bindparams(bindparam("permission_codes", expanding=True)),
                {"permission_codes": permission_codes},
            ).mappings().all()
            if permission_rows:
                connection.execute(
                    text(
                        f"""
                        insert into {self._fqtn('app_role_permission')} (
                            role_id,
                            permission_id
                        )
                        values (
                            :role_id,
                            :permission_id
                        )
                        on conflict (role_id, permission_id) do nothing
                        """
                    ),
                    [{"role_id": role_id, "permission_id": int(row["permission_id"])} for row in permission_rows],
                )

    def _migrate_user_roles(self, connection: Any, *, bootstrap_admin_username: str) -> None:
        users = connection.execute(
            text(
                f"""
                select user_id, username
                from {self._fqtn('app_user')}
                order by user_id asc
                """
            )
        ).mappings().all()
        for user in users:
            user_id = int(user["user_id"])
            role_count = int(
                connection.execute(
                    text(f"select count(*) from {self._fqtn('app_user_role')} where user_id = :user_id"),
                    {"user_id": user_id},
                ).scalar_one()
            )
            if role_count > 0:
                continue
            permission_codes = set(self._load_direct_user_permission_codes(connection, user_id))
            if str(user["username"]).lower() == bootstrap_admin_username.lower() or "permissions.manage" in permission_codes:
                role_codes = ["admin"]
            elif {"agents.view", "briefing.generate"} & permission_codes:
                role_codes = ["researcher"]
            elif "chat.use" in permission_codes:
                role_codes = ["trader"]
            else:
                role_codes = ["viewer"]
            self._replace_user_roles(connection, actor_user_id=user_id, target_user_id=user_id, role_codes=role_codes)

    def _load_direct_user_permission_codes(self, connection: Any, user_id: int) -> list[str]:
        rows = connection.execute(
            text(
                f"""
                select p.permission_code
                from {self._fqtn('app_user_permission')} up
                join {self._fqtn('app_permission')} p
                  on p.permission_id = up.permission_id
                where up.user_id = :user_id
                """
            ),
            {"user_id": user_id},
        ).scalars().all()
        return [str(row) for row in rows]

    def _load_user_permission_codes(self, connection: Any, user_id: int) -> list[str]:
        rows = connection.execute(
            text(
                f"""
                select distinct p.permission_code
                from {self._fqtn('app_user_permission')} up
                join {self._fqtn('app_permission')} p
                  on p.permission_id = up.permission_id
                where up.user_id = :user_id
                union
                select distinct p.permission_code
                from {self._fqtn('app_user_role')} ur
                join {self._fqtn('app_role_permission')} rp
                  on rp.role_id = ur.role_id
                join {self._fqtn('app_permission')} p
                  on p.permission_id = rp.permission_id
                join {self._fqtn('app_role')} r
                  on r.role_id = ur.role_id
                where ur.user_id = :user_id
                  and r.is_active = true
                order by permission_code
                """
            ),
            {"user_id": user_id},
        ).scalars().all()
        return [str(row) for row in rows]

    def _load_user_permissions(self, connection: Any, user_id: int) -> list[dict[str, Any]]:
        rows = connection.execute(
            text(
                f"""
                select distinct p.permission_code, p.permission_name, p.module_code, p.description
                from {self._fqtn('app_user_permission')} up
                join {self._fqtn('app_permission')} p
                  on p.permission_id = up.permission_id
                where up.user_id = :user_id
                union
                select distinct p.permission_code, p.permission_name, p.module_code, p.description
                from {self._fqtn('app_user_role')} ur
                join {self._fqtn('app_role_permission')} rp
                  on rp.role_id = ur.role_id
                join {self._fqtn('app_permission')} p
                  on p.permission_id = rp.permission_id
                join {self._fqtn('app_role')} r
                  on r.role_id = ur.role_id
                where ur.user_id = :user_id
                  and r.is_active = true
                order by module_code, permission_code
                """
            ),
            {"user_id": user_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def _load_user_role_codes(self, connection: Any, user_id: int) -> list[str]:
        rows = connection.execute(
            text(
                f"""
                select r.role_code
                from {self._fqtn('app_user_role')} ur
                join {self._fqtn('app_role')} r
                  on r.role_id = ur.role_id
                where ur.user_id = :user_id
                  and r.is_active = true
                order by r.role_id asc
                """
            ),
            {"user_id": user_id},
        ).scalars().all()
        return [str(row) for row in rows]

    def _load_user_roles(self, connection: Any, user_id: int) -> list[dict[str, Any]]:
        rows = connection.execute(
            text(
                f"""
                select
                    r.role_id,
                    r.role_code,
                    r.role_name,
                    r.description,
                    r.is_system,
                    r.is_active
                from {self._fqtn('app_user_role')} ur
                join {self._fqtn('app_role')} r
                  on r.role_id = ur.role_id
                where ur.user_id = :user_id
                  and r.is_active = true
                order by r.role_id asc
                """
            ),
            {"user_id": user_id},
        ).mappings().all()
        return [
            {
                **dict(row),
                "permission_codes": self._load_role_permission_codes(connection, int(row["role_id"])),
                "permissions": self._load_role_permissions(connection, int(row["role_id"])),
            }
            for row in rows
        ]

    def _load_role_permission_codes(self, connection: Any, role_id: int) -> list[str]:
        rows = connection.execute(
            text(
                f"""
                select p.permission_code
                from {self._fqtn('app_role_permission')} rp
                join {self._fqtn('app_permission')} p
                  on p.permission_id = rp.permission_id
                where rp.role_id = :role_id
                order by p.permission_code
                """
            ),
            {"role_id": role_id},
        ).scalars().all()
        return [str(row) for row in rows]

    def _load_role_permissions(self, connection: Any, role_id: int) -> list[dict[str, Any]]:
        rows = connection.execute(
            text(
                f"""
                select p.permission_code, p.permission_name, p.module_code, p.description
                from {self._fqtn('app_role_permission')} rp
                join {self._fqtn('app_permission')} p
                  on p.permission_id = rp.permission_id
                where rp.role_id = :role_id
                order by p.module_code, p.permission_code
                """
            ),
            {"role_id": role_id},
        ).mappings().all()
        return [dict(row) for row in rows]

    def _replace_user_permissions(
        self,
        connection: Any,
        *,
        actor_user_id: int,
        target_user_id: int,
        permission_codes: list[str],
    ) -> None:
        self._ensure_permissions(connection)
        normalized_codes = sorted({code for code in permission_codes if code})
        connection.execute(
            text(f"delete from {self._fqtn('app_user_permission')} where user_id = :user_id"),
            {"user_id": target_user_id},
        )
        if not normalized_codes:
            return
        permission_rows = connection.execute(
            text(
                f"""
                select permission_id, permission_code
                from {self._fqtn('app_permission')}
                where permission_code in :permission_codes
                """
            ).bindparams(bindparam("permission_codes", expanding=True)),
            {"permission_codes": normalized_codes},
        ).mappings().all()
        if not permission_rows:
            return
        connection.execute(
            text(
                f"""
                insert into {self._fqtn('app_user_permission')} (
                    user_id,
                    permission_id,
                    granted_by
                )
                values (
                    :user_id,
                    :permission_id,
                    :granted_by
                )
                on conflict (user_id, permission_id) do nothing
                """
            ),
            [
                {
                    "user_id": target_user_id,
                    "permission_id": int(row["permission_id"]),
                    "granted_by": actor_user_id,
                }
                for row in permission_rows
            ],
        )

    def _replace_user_roles(
        self,
        connection: Any,
        *,
        actor_user_id: int,
        target_user_id: int,
        role_codes: list[str],
    ) -> None:
        self._ensure_roles(connection)
        normalized_codes = sorted({code for code in role_codes if code})
        connection.execute(
            text(f"delete from {self._fqtn('app_user_role')} where user_id = :user_id"),
            {"user_id": target_user_id},
        )
        if not normalized_codes:
            return
        role_rows = connection.execute(
            text(
                f"""
                select role_id, role_code
                from {self._fqtn('app_role')}
                where role_code in :role_codes
                  and is_active = true
                """
            ).bindparams(bindparam("role_codes", expanding=True)),
            {"role_codes": normalized_codes},
        ).mappings().all()
        if not role_rows:
            return
        connection.execute(
            text(
                f"""
                insert into {self._fqtn('app_user_role')} (
                    user_id,
                    role_id,
                    granted_by
                )
                values (
                    :user_id,
                    :role_id,
                    :granted_by
                )
                on conflict (user_id, role_id) do nothing
                """
            ),
            [
                {
                    "user_id": target_user_id,
                    "role_id": int(row["role_id"]),
                    "granted_by": actor_user_id,
                }
                for row in role_rows
            ],
        )

    def _hash_session_token(self, session_token: str) -> str:
        return sha256(session_token.encode("utf-8")).hexdigest()

    def _build_password_hash(self, password: str, password_salt: str) -> str:
        digest = pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            password_salt.encode("utf-8"),
            260_000,
        ).hex()
        return f"pbkdf2_sha256$260000${password_salt}${digest}"

    def _fqtn(self, table_name: str) -> str:
        return f"{self.settings.schema}.{table_name}"

    def _source_code_for_item(self, item: dict[str, Any]) -> str:
        return str(item.get("source") or "unknown_source").strip()

    def _build_source_record_id(self, item: dict[str, Any], publish_time: datetime) -> str:
        candidate = str(item.get("url") or "").strip()
        if candidate:
            return sha256(candidate.encode("utf-8")).hexdigest()
        title = str(item.get("headline") or item.get("title") or "").strip()
        normalized_title = " ".join(title.split())
        key = f"{normalized_title}|{publish_time.strftime('%Y-%m-%d %H:%M')}"
        return sha256(key.encode("utf-8")).hexdigest()

    def _build_policy_record_id(self, item: dict[str, Any]) -> str:
        candidate = str(item.get("url") or item.get("title") or json.dumps(item, ensure_ascii=False)).strip()
        return sha256(candidate.encode("utf-8")).hexdigest()

    def _build_report_record_id(self, payload: dict[str, Any]) -> str:
        report_date = str(payload.get("report_date") or "").strip()
        title = str(payload.get("title") or "").strip()
        markdown = str(payload.get("markdown") or "").strip()
        key = f"{report_date}|{title}|{len(markdown)}"
        return sha256(key.encode("utf-8")).hexdigest()

    def _payload_hash(self, payload: dict[str, Any]) -> str:
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        return sha256(encoded.encode("utf-8")).hexdigest()

    def _raw_record_exists(
        self,
        connection: Any,
        *,
        table_name: str,
        source_id: int,
        source_record_id: str,
    ) -> bool:
        exists_value = connection.execute(
            text(
                f"""
                select 1
                from {self._fqtn(table_name)}
                where source_id = :source_id
                  and source_record_id = :source_record_id
                limit 1
                """
            ),
            {"source_id": source_id, "source_record_id": source_record_id},
        ).scalar()
        return exists_value is not None

    def _normalize_timestamp(self, value: Any, fallback_date: date) -> datetime:
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return datetime.combine(value, time(8, 0))
        raw = str(value or "").strip()
        if raw:
            normalized = raw.replace("/", "-").replace("T", " ")
            if normalized.endswith("24:00"):
                try:
                    base_date = datetime.strptime(normalized[:10], "%Y-%m-%d").date()
                    return datetime.combine(base_date + timedelta(days=1), time(0, 0))
                except ValueError:
                    pass
            for text_value, fmt in (
                (normalized[:19], "%Y-%m-%d %H:%M:%S"),
                (normalized[:16], "%Y-%m-%d %H:%M"),
                (normalized[:10], "%Y-%m-%d"),
            ):
                try:
                    parsed = datetime.strptime(text_value, fmt)
                    if fmt == "%Y-%m-%d":
                        return datetime.combine(parsed.date(), time(8, 0))
                    return parsed
                except ValueError:
                    continue
        return datetime.combine(fallback_date, time(8, 0))

    def _build_datetime_range(self, start_date: date, end_date: date) -> tuple[datetime, datetime]:
        return (
            datetime.combine(start_date, time(0, 0)),
            datetime.combine(end_date + timedelta(days=1), time(0, 0)),
        )

    def _extract_item_date(self, item: dict[str, Any]) -> date | None:
        for field in ("observation_date", "report_date", "effective_time", "publish_time", "publish_date"):
            raw_value = str(item.get(field) or "").strip()
            if len(raw_value) < 10:
                continue
            normalized = raw_value.replace("/", "-")
            try:
                return datetime.strptime(normalized[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
        return None

    def _coerce_date(self, value: Any) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        raw_value = str(value or "").strip()
        if len(raw_value) < 10:
            return None
        try:
            return datetime.fromisoformat(raw_value[:10]).date()
        except ValueError:
            return None

    def _extract_project_quota_id(self, indicator_code: str) -> int | None:
        try:
            return int(str(indicator_code).rsplit("_", 1)[-1])
        except Exception:
            return None

    def _default_unit_for_indicator(self, indicator_code: str) -> str:
        if indicator_code == "brent_active_settlement":
            return "美元/桶"
        return "元/吨"

    def _entity_code_for_indicator(self, indicator_code: str) -> str:
        mapping = {
            "sd_gas92_market": "SHANDONG",
            "cn_gas92_market": "NATIONAL",
            "east_china_gas92_market": "EAST_CHINA",
            "north_china_gas92_market": "NORTH_CHINA",
            "south_china_gas92_market": "SOUTH_CHINA",
            "central_china_gas92_market": "CENTRAL_CHINA",
            "northwest_gas92_market": "NORTHWEST",
            "southwest_gas92_market": "SOUTHWEST",
            "northeast_gas92_market": "NORTHEAST",
            "brent_active_settlement": "BRENT",
        }
        return mapping.get(indicator_code, indicator_code.upper())

    def _entity_name_for_indicator(self, indicator_code: str) -> str:
        mapping = {
            "SHANDONG": "山东",
            "NATIONAL": "全国",
            "EAST_CHINA": "华东",
            "NORTH_CHINA": "华北",
            "SOUTH_CHINA": "华南",
            "CENTRAL_CHINA": "华中",
            "NORTHWEST": "西北",
            "SOUTHWEST": "西南",
            "NORTHEAST": "东北",
            "BRENT": "布伦特",
        }
        return mapping.get(self._entity_code_for_indicator(indicator_code), indicator_code)

    def _entity_region_level(self, indicator_code: str) -> str:
        entity_code = self._entity_code_for_indicator(indicator_code)
        if entity_code in {"SHANDONG"}:
            return "province"
        if entity_code in {"NATIONAL"}:
            return "country"
        if entity_code in {"BRENT"}:
            return "global"
        return "macro_region"
