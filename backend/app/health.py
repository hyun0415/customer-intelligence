def dependency_status(repository, session_store) -> dict[str, bool]:
    """민감한 연결 정보를 노출하지 않고 준비 상태만 반환한다."""
    return {
        "postgres": bool(repository.check_connection()),
        "redis": bool(session_store.client.ping()),
    }
