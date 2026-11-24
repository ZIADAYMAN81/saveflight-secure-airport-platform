from prometheus_client import Counter, generate_latest, CONTENT_TYPE_LATEST

failed_login_attempts_total = Counter(
    "failed_login_attempts_total", "Total number of failed login attempts"
)
successful_login_total = Counter(
    "successful_login_total", "Total number of successful logins"
)
unauthorized_access_attempts_total = Counter(
    "unauthorized_access_attempts_total", "Total number of 401/403 responses returned to clients"
)


def metrics_response():
    return generate_latest(), CONTENT_TYPE_LATEST
