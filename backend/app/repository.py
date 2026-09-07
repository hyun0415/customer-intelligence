import json
from collections.abc import Callable
from uuid import UUID, uuid4

from src.auth.access import PolicyAccessGrant
from src.database import connect

from .audit import SecurityAuditEvent
from .models import CurrentUser, UserRole
from .titles import build_conversation_title

ConnectionFactory = Callable[..., object]


class WebRepository:
    def __init__(self, connection_factory: ConnectionFactory = connect) -> None:
        self.connection_factory = connection_factory

    def check_connection(self) -> bool:
        with self.connection_factory() as conn:
            row = conn.execute("SELECT 1 AS ok").fetchone()
            return bool(row and row["ok"] == 1)

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
        self,
        user_id: int,
        title: str,
        *,
        context_mode: str = "general",
        product_parent_asin: str | None = None,
    ) -> dict:
        conversation_id = uuid4()
        with self.connection_factory() as conn:
            return conn.execute(
                """
                WITH inserted AS (
                    INSERT INTO conversations (
                        conversation_id, user_id, title,
                        context_mode, product_parent_asin
                    ) VALUES (%s, %s, %s, %s, %s)
                    RETURNING conversation_id, title, created_at, updated_at,
                              context_mode, product_parent_asin
                )
                SELECT i.*, p.title AS product_title, p.store AS product_store
                FROM inserted i
                LEFT JOIN products p ON p.parent_asin = i.product_parent_asin
                """,
                (
                    conversation_id,
                    user_id,
                    title,
                    context_mode,
                    product_parent_asin,
                ),
            ).fetchone()

    def list_conversations(self, user_id: int) -> list[dict]:
        with self.connection_factory() as conn:
            return conn.execute(
                """
                SELECT c.conversation_id, c.title, c.created_at, c.updated_at,
                       c.context_mode, c.product_parent_asin,
                       p.title AS product_title, p.store AS product_store
                FROM conversations c
                LEFT JOIN products p ON p.parent_asin = c.product_parent_asin
                WHERE c.user_id = %s AND c.archived_at IS NULL
                ORDER BY c.updated_at DESC
                """,
                (user_id,),
            ).fetchall()

    def list_dashboard_products(
        self, *, query: str | None = None, limit: int = 12
    ) -> list[dict]:
        search = (query or "").strip()
        with self.connection_factory() as conn:
            return conn.execute(
                """
                SELECT
                    parent_asin, title, store, average_rating,
                    review_count, negative_count, verified_count,
                    COALESCE(ROUND(
                        100.0 * negative_count / NULLIF(review_count, 0), 2
                    ), 0)::float AS negative_ratio,
                    COALESCE(ROUND(
                        100.0 * verified_count / NULLIF(review_count, 0), 2
                    ), 0)::float AS verified_ratio
                FROM products
                WHERE (%s = '' OR title ILIKE %s OR store ILIKE %s
                       OR parent_asin ILIKE %s)
                ORDER BY review_count DESC, parent_asin
                LIMIT %s
                """,
                (search, f"%{search}%", f"%{search}%", f"%{search}%", limit),
            ).fetchall()

    def product_exists(self, parent_asin: str) -> bool:
        with self.connection_factory() as conn:
            return bool(
                conn.execute(
                    "SELECT 1 FROM products WHERE parent_asin = %s",
                    (parent_asin,),
                ).fetchone()
            )

    def get_dashboard_product(self, parent_asin: str) -> dict | None:
        with self.connection_factory() as conn:
            product = conn.execute(
                """
                SELECT
                    parent_asin, title, store, average_rating,
                    review_count, negative_count, verified_count,
                    COALESCE(ROUND(
                        100.0 * negative_count / NULLIF(review_count, 0), 2
                    ), 0)::float AS negative_ratio,
                    COALESCE(ROUND(
                        100.0 * verified_count / NULLIF(review_count, 0), 2
                    ), 0)::float AS verified_ratio,
                    min_review_at, max_review_at
                FROM products
                WHERE parent_asin = %s
                """,
                (parent_asin,),
            ).fetchone()
            if product is None:
                return None

            distribution_rows = conn.execute(
                """
                SELECT rating::int AS rating, COUNT(*)::int AS review_count
                FROM reviews
                WHERE parent_asin = %s
                GROUP BY rating::int
                ORDER BY rating::int
                """,
                (parent_asin,),
            ).fetchall()
            counts = {row["rating"]: row["review_count"] for row in distribution_rows}
            distribution = [
                {"rating": rating, "review_count": counts.get(rating, 0)}
                for rating in range(1, 6)
            ]
            reviews = conn.execute(
                """
                SELECT review_id, rating, review_title, review_text,
                       reviewed_at, helpful_vote, verified_purchase
                FROM reviews
                WHERE parent_asin = %s AND rating <= 3
                ORDER BY helpful_vote DESC, reviewed_at DESC
                LIMIT 5
                """,
                (parent_asin,),
            ).fetchall()
            return {
                **product,
                "rating_distribution": distribution,
                "representative_reviews": reviews,
            }

    def get_conversation(self, user_id: int, conversation_id: UUID) -> dict | None:
        with self.connection_factory() as conn:
            conversation = conn.execute(
                """
                SELECT c.conversation_id, c.title, c.created_at, c.updated_at,
                       c.context_mode, c.product_parent_asin,
                       p.title AS product_title, p.store AS product_store
                FROM conversations c
                LEFT JOIN products p ON p.parent_asin = c.product_parent_asin
                WHERE c.conversation_id = %s AND c.user_id = %s
                  AND c.archived_at IS NULL
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
                    SELECT source_id, title, version_number, section_title,
                           metadata
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
                  AND archived_at IS NULL
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
                        RETURNING source_id, title, version_number, section_title,
                                  metadata
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
            title = build_conversation_title(content)
            conn.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP,
                    title = CASE
                        WHEN %s = 'user' AND title = '새 대화' THEN %s
                        ELSE title
                    END
                WHERE conversation_id = %s
                """,
                (role, title, conversation_id),
            )
            return {**message, "sources": saved_sources}

    def archive_conversation(self, user_id: int, conversation_id: UUID) -> bool:
        """사용자 화면에서는 숨기되 감사·근거 이력은 보존한다."""
        with self.connection_factory() as conn:
            row = conn.execute(
                """
                UPDATE conversations
                SET archived_at = CURRENT_TIMESTAMP,
                    updated_at = CURRENT_TIMESTAMP
                WHERE conversation_id = %s AND user_id = %s
                  AND archived_at IS NULL
                RETURNING conversation_id
                """,
                (conversation_id, user_id),
            ).fetchone()
            return row is not None

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
                  AND c.archived_at IS NULL
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
