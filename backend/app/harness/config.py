"""配置层:从.env读取所有配置"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(__file__).resolve().parents[2] / ".env"

class Settings(BaseSettings):

    # 生成模型
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # Embedding（硅基流动）
    embedding_api_key: str = ""
    embedding_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"

    # ChromaDB 本地持久化目录
    chroma_dir: str = "./chroma"

    # MySQL
    mysql_host: str = "localhost"
    mysql_port: int = 3306
    mysql_user: str = "root"
    mysql_password: str = ""
    mysql_database: str = "my_jevis"

    # JWT
    jwt_secret_key: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 10080


    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        env_file_encoding="utf-8",
        # 环境变量名不区分大小写
        case_sensitive=False,
        extra="ignore",
    )

settings = Settings()


# 明显不安全的默认值，绝不允许用于真实认证
_INSECURE_JWT_KEYS = {"", "change-me", "changeme", "secret", "your-secret-key", "test"}


def _validate_security(s: Settings) -> None:
    """启动前校验安全配置。不安全就直接拒绝启动，而不是带着弱密钥跑起来。

    理由：JWT 密钥用于签发登录令牌。如果沿用默认值，任何知道默认值的人
    都能伪造任意用户的 token，绕过全部权限校验。这种"能启动但完全不安全"
    的状态比启动失败危险得多。
    """
    key = (s.jwt_secret_key or "").strip()
    if key.lower() in _INSECURE_JWT_KEYS or len(key) < 32:
        raise RuntimeError(
            "\n"
            "============================================================\n"
            "[启动中止] JWT_SECRET_KEY 未配置或强度不足\n"
            "============================================================\n"
            "  要求：至少 32 个字符的随机字符串，且不能使用默认值。\n"
            "  请在 backend/.env 中设置，例如生成一个：\n"
            "\n"
            r'    python -c "import secrets; print(secrets.token_hex(32))"' + "\n"
            "\n"
            "  然后把结果写入 .env：\n"
            "    JWT_SECRET_KEY=<生成的值>\n"
            "\n"
            "  注意：.env 已被 .gitignore 忽略，请勿提交到 Git。\n"
            "============================================================\n"
        )


_validate_security(settings)