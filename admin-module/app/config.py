"""
03@C7:0 :>=D83C@0F88 87 config.yaml A 2>7<>6=>ABLN ?5@5>?@545;5=8O G5@57 env vars.
"""
import os
from pathlib import Path
from typing import Any, Dict

import yaml

from app.core.config_models import Config


def load_config(config_path: str = "config.yaml") -> Config:
    """
    03@C605B :>=D83C@0F8N 87 YAML D09;0.

    Args:
        config_path: CBL : D09;C config.yaml

    Returns:
        1J5:B Config A 20;848@>20==K<8 =0AB@>9:0<8

    Raises:
        FileNotFoundError: A;8 config.yaml =5 =0945=
        ValueError: A;8 :>=D83C@0F8O =520;84=0
    """
    config_file = Path(config_path)

    if not config_file.exists():
        raise FileNotFoundError(f">=D83C@0F8>==K9 D09; {config_path} =5 =0945=")

    # 03@C7:0 YAML
    with open(config_file, "r", encoding="utf-8") as f:
        config_dict = yaml.safe_load(f)

    # 1@01>B:0 ?5@5<5==KE >:@C65=8O 4;O GC2AB28B5;L=KE 40==KE
    config_dict = _process_env_vars(config_dict)

    # 0;840F8O G5@57 Pydantic
    try:
        config = Config(**config_dict)
    except Exception as e:
        raise ValueError(f"H81:0 20;840F88 :>=D83C@0F88: {e}")

    return config


def _process_env_vars(config_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    1@010BK205B ?5@5<5==K5 >:@C65=8O 4;O ?5@5>?@545;5=8O :>=D83C@0F88.

    5@5<5==K5 >:@C65=8O 8<5NB ?@8>@8B5B =04 7=0G5=8O<8 87 config.yaml.
    $>@<0B: ADMIN_MODULE_<SECTION>_<KEY> (=0?@8<5@, ADMIN_MODULE_DATABASE_PASSWORD)

    Args:
        config_dict: !;>20@L :>=D83C@0F88 87 YAML

    Returns:
        1=>2;5==K9 A;>20@L :>=D83C@0F88
    """
    # Database
    if "database" not in config_dict:
        config_dict["database"] = {}

    config_dict["database"]["password"] = os.getenv(
        "ADMIN_MODULE_DATABASE_PASSWORD", config_dict["database"].get("password", "")
    )
    config_dict["database"]["host"] = os.getenv(
        "ADMIN_MODULE_DATABASE_HOST", config_dict["database"].get("host", "localhost")
    )
    config_dict["database"]["port"] = int(
        os.getenv(
            "ADMIN_MODULE_DATABASE_PORT", str(config_dict["database"].get("port", 5432))
        )
    )

    # Redis
    if "redis" not in config_dict:
        config_dict["redis"] = {}

    config_dict["redis"]["password"] = os.getenv(
        "ADMIN_MODULE_REDIS_PASSWORD", config_dict["redis"].get("password", "")
    )
    config_dict["redis"]["host"] = os.getenv(
        "ADMIN_MODULE_REDIS_HOST", config_dict["redis"].get("host", "localhost")
    )
    config_dict["redis"]["port"] = int(
        os.getenv(
            "ADMIN_MODULE_REDIS_PORT", str(config_dict["redis"].get("port", 6379))
        )
    )

    # JWT Keys
    if "auth" not in config_dict:
        config_dict["auth"] = {}
    if "jwt" not in config_dict["auth"]:
        config_dict["auth"]["jwt"] = {}

    config_dict["auth"]["jwt"]["private_key_path"] = os.getenv(
        "ADMIN_MODULE_JWT_PRIVATE_KEY_PATH",
        config_dict["auth"]["jwt"].get("private_key_path", "./keys/jwt-private.pem"),
    )
    config_dict["auth"]["jwt"]["public_key_path"] = os.getenv(
        "ADMIN_MODULE_JWT_PUBLIC_KEY_PATH",
        config_dict["auth"]["jwt"].get("public_key_path", "./keys/jwt-public.pem"),
    )

    # LDAP
    if "ldap" in config_dict:
        config_dict["ldap"]["bind_password"] = os.getenv(
            "ADMIN_MODULE_LDAP_BIND_PASSWORD",
            config_dict["ldap"].get("bind_password", ""),
        )

    # OAuth2
    if "oauth" in config_dict and "providers" in config_dict["oauth"]:
        for provider_name, provider_config in config_dict["oauth"]["providers"].items():
            env_prefix = f"ADMIN_MODULE_OAUTH_{provider_name.upper()}"
            provider_config["client_secret"] = os.getenv(
                f"{env_prefix}_CLIENT_SECRET", provider_config.get("client_secret", "")
            )

    # Debug mode
    if "app" not in config_dict:
        config_dict["app"] = {}
    config_dict["app"]["debug"] = os.getenv("ADMIN_MODULE_DEBUG", "false").lower() in [
        "true",
        "1",
        "yes",
    ]

    return config_dict


# ;>10;L=K9 M:75<?;O@ :>=D83C@0F88
# 03@C605BAO ?@8 8<?>@B5 <>4C;O
try:
    settings = load_config()
except FileNotFoundError:
    # ;O B5AB>2 8 development <>6=> A>740BL ?CABCN :>=D83C@0F8N
    settings = None
except Exception as e:
    print(f"   @54C?@5645=85: 5 C40;>AL 703@C78BL :>=D83C@0F8N: {e}")
    settings = None
