import json
from collections.abc import Callable
from uuid import UUID, uuid4

from src.auth.access import PolicyAccessGrant
from src.database import connect

from .models import CurrentUser, UserRole
from .audit import SecurityAuditEvent

ConnectionFactory = Callable[..., object]


class WebRepository:
    def __init__(self, connection_factory: ConnectionFactory = connect) -> None:
        self.connection_factory = connection_factory

    def upsert_user(
        self,
        *,
        issuer: str,
        subject: str,
        email: str,
        display_name: str,
    ) -> CurrentUser:
        with self.connection_factory() as conn:
            row = conn.execute(
                """
                INSERT INTO app_users (
                    oidc_issuer, oidc_subject, email, display_name
                )
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (oidc_issuer, oidc_subject) DO UPDATE SET
                    email = EXCLUDED.email,
                    display_name = EXCLUDED.display_name,
                    updated_at = CURRENT_TIMESTAMP
                RETURNING user_id
                """,
                (issuer, subject, email, display_name),
            ).fetchone()
            return self.get_user(row["user_id"], conn=conn)

    def record_security_event(self, event: SecurityAuditEvent) -> None:
        with self.connection_factory() as conn:
            conn.execute(
                """
                INSERT INTO security_audit_events (
                    audit_event_id, event_type, outcome, actor_user_id,
                    oidc_issuer, oidc_subject, session_fingerprint, request_id,
                    ip_address, user_agent, resource_type, resource_id, metadata
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s,
                    %s::inet, %s, %s, %s, %s::jsonb
                )
                """,
                event.database_values(),
            )

    def list_security_events(self, limit: int = 100) -> list[dict]:
        with self.connection_factory() as conn:
            return conn.execute(
                """
                SELECT audit_event_id, occurred_at, event_type, outcome,
                       actor_user_id, oidc_issuer, session_fingerprint,
                       request_id, ip_address::text AS ip_address, user_agent,
                       resource_type, resource_id, metadata
                FROM security_audit_events
                ORDER BY occurred_at DESC
                LIMIT %s
                """,
                (limit,),
            ).fetchall()

    def get_user(self, user_id: int, *, conn=None) -> CurrentUser | None:
        owns_connection = conn is None
        if owns_connection:
            conn = self.connection_factory()
        try:
            row = conn.execute(
                """
                SELECT user_id, email, display_name, role, is_active
                FROM app_users
                WHERE user_id = %s
                """,
                (user_id,),
            ).fetchone()
            if row is None:
                return None
            scope_rows = conn.execute(
                """
                SELECT collection, jurisdiction, department
                FROM user_policy_scopes
                WHERE user_id = %s
                ORDER BY collection, jurisdiction, department
                """,
                (user_id,),
            ).fetchall()
            return CurrentUser(
                **row,
                policy_scopes=[PolicyAccessGrant(**scope) for scope in scope_rows],
            )
        finally:
            if owns_connection:
                conn.close()

    def list_users(self) -> list[CurrentUser]:
        with self.connection_factory() as conn:
            ids = conn.execute(
                "SELECT user_id FROM app_users ORDER BY user_id"
            ).fetchall()
            return [self.get_user(row["user_id"], conn=conn) for row in ids]

    def replace_user_scopes(
        self, user_id: int, grants: list[PolicyAccessGrant]
    ) -> CurrentUser:
        with self.connection_factory() as conn:
            exists = conn.execute(
                "SELECT 1 FROM app_users WHERE user_id = %s FOR UPDATE",
                (user_id,),
            ).fetchone()
            if not exists:
                raise KeyError(user_id)
            conn.execute(
                "DELETE FROM user_policy_scopes WHERE user_id = %s",
                (user_id,),
            )
            for grant in grants:
                conn.execute(
                    """
                    INSERT INTO user_policy_scopes (
                        user_id, collection, jurisdiction, department
                    ) VALUES (%s, %s, %s, %s)
                    """,
                    (
                        user_id,
                        grant.collection,
                        grant.jurisdiction,
                        grant.department,
                    ),
                )
            return self.get_user(user_id, conn=conn)

    def update_user_access(
        self, user_id: int, role: UserRole, is_active: bool
    ) -> CurrentUser:
        with self.connection_factory() as conn:
            row = conn.execute(
                """
                UPDATE app_users
                SET role = %s, is_active = %s, updated_at = CURRENT_TIMESTAMP
                WHERE user_id = %s
                RETURNING user_id
                """,
                (role.value, is_active, user_id),
            ).fetchone()
            if row is None:
                raise KeyError(user_id)
            return self.get_user(user_id, conn=conn)

    def create_conversation(
        self, user_id: int, title: str
    ) -> dict:
        conversation_id = uuid4()
        with self.connection_factory() as conn:
            return conn.execute(
                """
                INSERT INTO conversations (conversation_id, user_id, title)
                VALUES (%s, %s, %s)
                RETURNING conversation_id, title, created_at, updated_at
                """,
                (conversation_id, user_id, title),
            ).fetchone()

    def list_conversations(self, user_id: int) -> list[dict]:
        with self.connection_factory() as conn:
            return conn.execute(
                """
                SELECT conversation_id, title, created_at, updated_at
                FROM conversations
                WHERE user_id = %s
                ORDER BY updated_at DESC
                """,
                (user_id,),
            ).fetchall()

    def get_conversation(self, user_id: int, conversation_id: UUID) -> dict | None:
        with self.connection_factory() as conn:
            conversation = conn.execute(
                """
                SELECT conversation_id, title, created_at, updated_at
                FROM conversations
                WHERE conversation_id = %s AND user_id = %s
                """,
                (conversation_id, user_id),
            ).fetchone()
            if conversation is None:
                return None
            messages = conn.execute(
                """
                SELECT message_id, role, content, response_status, created_at
                FROM conversation_messages
                WHERE conversation_id = %s
                ORDER BY created_at, message_id
                """,
                (conversation_id,),
            ).fetchall()
            for message in messages:
                message["sources"] = conn.execute(
                    """
                    SELECT source_id, title, version_number, section_title
                    FROM message_sources
                    WHERE message_id = %s
                    ORDER BY source_id
                    """,
                    (message["message_id"],),
                ).fetchall()
            return {**conversation, "messages": messages}

    def add_message(
        self,
        *,
        user_id: int,
        conversation_id: UUID,
        role: str,
        content: str,
        response_status: str | None = None,
        sources: list[dict] | None = None,
    ) -> dict:
        message_id = uuid4()
        with self.connection_factory() as conn:
            owner = conn.execute(
                """
                SELECT 1 FROM conversations
                WHERE conversation_id = %s AND user_id = %s
                FOR UPDATE
                """,
                (conversation_id, user_id),
            ).fetchone()
            if not owner:
                raise KeyError(conversation_id)
            message = conn.execute(
                """
                INSERT INTO conversation_messages (
                    message_id, conversation_id, role, content, response_status
                ) VALUES (%s, %s, %s, %s, %s)
                RETURNING message_id, role, content, response_status, created_at
                """,
                (message_id, conversation_id, role, content, response_status),
            ).fetchone()
            saved_sources = []
            for source in sources or []:
                saved_sources.append(
                    conn.execute(
                        """
                        INSERT INTO message_sources (
                            message_id, source_id, title, version_number,
                            section_title, metadata
                        ) VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                        RETURNING source_id, title, version_number, section_title
                        """,
                        (
                            message_id,
                            source["source_id"],
                            source["title"],
                            source.get("version_number"),
                            source.get("section_title"),
                            json.dumps(source.get("metadata", {})),
                        ),
                    ).fetchone()
                )
            conn.execute(
                """
                UPDATE conversations SET updated_at = CURRENT_TIMESTAMP
                WHERE conversation_id = %s
                """,
                (conversation_id,),
            )
            return {**message, "sources": saved_sources}

    def create_escalation(
        self,
        *,
        user_id: int,
        conversation_id: UUID,
        message_id: UUID,
        category: str,
        reason: str,
    ) -> None:
        with self.connection_factory() as conn:
            conn.execute(
                """
                INSERT INTO escalations (
                    escalation_id, conversation_id, message_id,
                    user_id, category, reason, last_occurred_at
                )
                SELECT %s, c.conversation_id, %s, c.user_id, %s, %s,
                       CURRENT_TIMESTAMP
                FROM conversations c
                WHERE c.conversation_id = %s AND c.user_id = %s
                ON CONFLICT (conversation_id)
                    WHERE status IN ('open', 'acknowledged')
                DO UPDATE SET
                    message_id = EXCLUDED.message_id,
                    category = EXCLUDED.category,
                    reason = EXCLUDED.reason,
                    occurrence_count = escalations.occurrence_count + 1,
                    last_occurred_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    uuid4(),
                    message_id,
                    category,
                    reason,
                    conversation_id,
                    user_id,
                ),
            )

    def list_escalations(self) -> list[dict]:
        with self.connection_factory() as conn:
            return conn.execute(
                """
                SELECT e.escalation_id, e.conversation_id, e.message_id,
                       e.user_id, u.email, e.category, e.reason, e.status,
                       e.occurrence_count, e.last_occurred_at,
                       e.created_at, e.updated_at
                FROM escalations e
                JOIN app_users u ON u.user_id = e.user_id
                ORDER BY
                    CASE e.status WHEN 'open' THEN 0 WHEN 'acknowledged' THEN 1 ELSE 2 END,
                    e.created_at DESC
                """
            ).fetchall()

    def update_escalation(self, escalation_id: UUID, value: str) -> dict:
        with self.connection_factory() as conn:
            row = conn.execute(
                """
                UPDATE escalations
                SET status = %s, updated_at = CURRENT_TIMESTAMP
                WHERE escalation_id = %s
                RETURNING escalation_id, conversation_id, message_id, user_id,
                          category, reason, status, occurrence_count,
                          last_occurred_at, created_at, updated_at
                """,
                (value, escalation_id),
            ).fetchone()
            if row is None:
                raise KeyError(escalation_id)
            user = conn.execute(
                "SELECT email FROM app_users WHERE user_id = %s",
                (row["user_id"],),
            ).fetchone()
            return {**row, "email": user["email"]}
