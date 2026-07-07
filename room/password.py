import hashlib
import secrets


def hash_password(password: str) -> str:
    """
    パスワードをソルト付きでハッシュ化する。
    戻り値の形式: "ソルト$ハッシュ値"
    """
    salt = secrets.token_hex(16)
    digest = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}${digest}"


def verify_password(password: str, hashed: str) -> bool:
    """
    入力されたパスワードが、保存済みのハッシュ値と一致するか検証する。
    """
    try:
        salt, digest = hashed.split("$", 1)
    except ValueError:
        return False

    check = hashlib.sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(check, digest)
