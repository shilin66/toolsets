"""Short-lived, single-file capabilities for the external mail extraction service."""
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer


def sign_artifact_url(url, key=None):
    if key is None:
        from config import settings
        key = settings.api_key
    if not key:
        raise ValueError('需要配置 API_KEY 才能生成附件访问链接')
    parsed = urlsplit(url)
    from urllib.parse import unquote
    token = URLSafeTimedSerializer(key, salt='mail-artifact-v1').dumps(unquote(parsed.path))
    return urlunsplit(parsed._replace(query=urlencode([*parse_qsl(parsed.query), ('access_token', token)])))


def verify_artifact_token(path, token, key):
    if not key or not token:
        return False
    try:
        return URLSafeTimedSerializer(key, salt='mail-artifact-v1').loads(token, max_age=3600) == path
    except (BadSignature, SignatureExpired):
        return False
