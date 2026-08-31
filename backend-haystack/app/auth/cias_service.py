"""
Authentication and membership verification service for CIAS (cias.ai).
Ensures that only verified CIAS members can access ia.ominis.org.
"""

import logging
from dataclasses import dataclass
from typing import Optional, Tuple

import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.config import get_settings

logger = logging.getLogger(__name__)

DEFAULT_CIAS_DB_URL = "postgresql+asyncpg://cias:e399585516d5ac9dc35993cd242794cdfd6e365c@44.215.64.245:5432/cias_red?sslmode=require"


@dataclass
class CiasAuthResult:
    is_authenticated: bool
    is_member: bool
    user_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    role: str = "user"
    token: Optional[str] = None
    error_message: Optional[str] = None
    error_code: Optional[str] = None


async def check_cias_membership(email: str) -> Tuple[bool, Optional[str], str]:
    """
    Check if a given email is a verified CIAS member, admin, or has a linked Didactiva account.
    Returns: (is_member: bool, full_name: Optional[str], role: str)
    """
    if not email:
        return False, None, "user"

    settings = get_settings()
    db_url = settings.cias_database_url or DEFAULT_CIAS_DB_URL

    try:
        if db_url.startswith("postgres://"):
            db_url = "postgresql+asyncpg://" + db_url[len("postgres://"):]
        elif db_url.startswith("postgresql://") and "+asyncpg" not in db_url:
            db_url = "postgresql+asyncpg://" + db_url[len("postgresql://"):]

        engine = create_async_engine(db_url, echo=False)
        async with engine.connect() as conn:
            query = text(
                """
                SELECT 
                    u.name,
                    u.role,
                    u.email_verified,
                    COALESCE(sp.member_verified, false) as member_verified,
                    EXISTS (
                        SELECT 1 FROM account a 
                        WHERE a.user_id = u.id AND a.provider_id = 'didactiva'
                    ) as is_didactiva
                FROM "user" u
                LEFT JOIN "specialist_profile" sp ON sp.user_id = u.id
                WHERE LOWER(TRIM(u.email)) = LOWER(TRIM(:email))
                LIMIT 1
                """
            )
            result = await conn.execute(query, {"email": email.strip()})
            row = result.fetchone()
            if row:
                name, role, email_verified, member_verified, is_didactiva = row
                # Admins, verified specialists, or Didactiva linked users are members
                if role == "admin" or member_verified or is_didactiva:
                    await engine.dispose()
                    return True, name, ("admin" if role == "admin" else "user")
                await engine.dispose()
                return False, name, "user"
        await engine.dispose()
    except Exception as e:
        logger.warning(f"Error checking CIAS database directly for {email}: {e}")

    return False, None, "user"


async def _check_membership_via_database(email: str, cias_db_url: str) -> Optional[bool]:
    """Compatibility helper for direct boolean membership check."""
    is_member, _, _ = await check_cias_membership(email)
    return is_member


async def authenticate_with_cias(identifier: str, password: str) -> CiasAuthResult:
    """
    Authenticate user credentials against CIAS (cias.ai) and verify member status.
    Only accounts with verified CIAS membership (or admin role) are allowed.
    """
    settings = get_settings()
    cias_base_url = (settings.cias_auth_url or "https://www.cias.ai").rstrip("/")
    sign_in_url = f"{cias_base_url}/api/auth/sign-in/email"
    email = identifier.strip().lower()

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                sign_in_url,
                json={"email": email, "password": password},
                headers={
                    "Content-Type": "application/json",
                    "Origin": "https://ia.ominis.org",
                    "User-Agent": "Ominis-Auth/1.0",
                },
            )

            # Check response status
            if resp.status_code == 200:
                data = resp.json()
                token = data.get("token") or (data.get("session") or {}).get("token")
                user_data = data.get("user") or {}
                user_id = user_data.get("id")
                user_email = user_data.get("email") or email
                user_name = user_data.get("name") or email.split("@")[0]
                user_role = user_data.get("role", "user")
                email_verified = user_data.get("emailVerified", False)

                if not email_verified:
                    return CiasAuthResult(
                        is_authenticated=False,
                        is_member=False,
                        error_message="Debes verificar tu correo electrónico en CIAS antes de ingresar a OMINIS. Revisa tu bandeja de entrada o solicita un nuevo enlace en https://www.cias.ai/auth.",
                        error_code="EMAIL_NOT_VERIFIED",
                    )

                # Determine membership
                is_member = False
                if user_role == "admin":
                    is_member = True
                elif user_data.get("memberVerified") is True or user_data.get("member_verified") is True:
                    is_member = True
                else:
                    # Check database directly
                    db_member, db_name, db_role = await check_cias_membership(user_email)
                    if db_member:
                        is_member = True
                        if db_name and not user_name:
                            user_name = db_name
                        if db_role == "admin":
                            user_role = "admin"

                if not is_member:
                    return CiasAuthResult(
                        is_authenticated=True,
                        is_member=False,
                        user_id=user_id,
                        email=user_email,
                        name=user_name,
                        role=user_role,
                        token=token,
                        error_message="Acceso restringido: ia.ominis.org es de uso exclusivo para miembros verificados de la Red CIAS. Tu cuenta de CIAS no cuenta con una membresía activa. Solicita o activa tu membresía en https://www.cias.ai.",
                        error_code="NOT_A_CIAS_MEMBER",
                    )

                return CiasAuthResult(
                    is_authenticated=True,
                    is_member=True,
                    user_id=user_id,
                    email=user_email,
                    name=user_name,
                    role=user_role,
                    token=token,
                )

            elif resp.status_code in (400, 401):
                err_data = {}
                try:
                    err_data = resp.json()
                except Exception:
                    pass
                msg = err_data.get("message") or ""
                if "verify" in msg.lower() or "verif" in msg.lower():
                    return CiasAuthResult(
                        is_authenticated=False,
                        is_member=False,
                        error_message="Debes verificar tu correo en CIAS antes de entrar. Abre el enlace enviado a tu correo o ve a https://www.cias.ai/auth.",
                        error_code="EMAIL_NOT_VERIFIED",
                    )
                return CiasAuthResult(
                    is_authenticated=False,
                    is_member=False,
                    error_message="Correo o contraseña incorrectos en tu cuenta de CIAS (cias.ai).",
                    error_code="INVALID_CREDENTIALS",
                )

            elif resp.status_code == 403:
                return CiasAuthResult(
                    is_authenticated=False,
                    is_member=False,
                    error_message="Tu cuenta de CIAS no tiene permisos de acceso o requiere verificación previa en https://www.cias.ai/auth.",
                    error_code="ACCOUNT_FORBIDDEN",
                )

            else:
                logger.error(f"Unexpected status from CIAS auth: {resp.status_code} - {resp.text}")
                return CiasAuthResult(
                    is_authenticated=False,
                    is_member=False,
                    error_message="Error de comunicación con el servicio de autenticación de CIAS. Intenta de nuevo.",
                    error_code="CIAS_ERROR",
                )

    except httpx.TimeoutException:
        logger.error("Timeout connecting to CIAS auth service")
        return CiasAuthResult(
            is_authenticated=False,
            is_member=False,
            error_message="Tiempo de espera agotado al conectar con cias.ai. Por favor intenta de nuevo en unos momentos.",
            error_code="TIMEOUT",
        )
    except Exception as e:
        logger.error(f"Failed to connect to CIAS auth: {e}")
        return CiasAuthResult(
            is_authenticated=False,
            is_member=False,
            error_message="No fue posible conectar con el servidor de autenticación de CIAS.",
            error_code="NETWORK_ERROR",
        )
