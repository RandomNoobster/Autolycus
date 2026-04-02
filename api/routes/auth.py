"""
Auth API Routes

This module provides endpoints for generating secure tokens for accessing
protected resources without requiring pre-existing Discord bot interaction.
"""
import logging
import asyncio
import json
import urllib.parse
import urllib.request
import urllib.error
import secrets
import time
from typing import Any

from flask import Blueprint, current_app, jsonify, redirect, request, session

from api.security import generate_token
from api.security import require_discord_session
from database.mongo import get_sync_db
from logic.api_client import call as call_pnw
from logic.verification import verify_discord_nation_link

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


def _resolve_discord_redirect_uri() -> str:
    explicit = str(current_app.config.get("DISCORD_REDIRECT_URI") or "").strip()
    if explicit:
        return explicit.rstrip("/")

    web_base = str(current_app.config.get("AUTOLYCUS_WEB_BASE_URL") or "").strip()
    if web_base:
        return f"{web_base.rstrip('/')}/api/auth/discord/callback"

    # Last resort: derive from the request host.
    return f"{request.host_url.rstrip('/')}/api/auth/discord/callback"


def _oauth_discord_enabled() -> bool:
    return bool(
        current_app.config.get("DISCORD_CLIENT_ID")
        and current_app.config.get("DISCORD_CLIENT_SECRET")
        and _resolve_discord_redirect_uri()
    )


def _oauth_exchange_code_for_token(code: str) -> dict[str, Any]:
    token_url = "https://discord.com/api/oauth2/token"
    redirect_uri = _resolve_discord_redirect_uri()
    payload = urllib.parse.urlencode({
        "client_id": current_app.config.get("DISCORD_CLIENT_ID", ""),
        "client_secret": current_app.config.get("DISCORD_CLIENT_SECRET", ""),
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
    }).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=payload,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
            "User-Agent": "AutolycusOAuth/1.0 (+https://autolycus.app)",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def _oauth_fetch_user(access_token: str) -> dict[str, Any]:
    req = urllib.request.Request(
        "https://discord.com/api/users/@me",
        method="GET",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "User-Agent": "AutolycusOAuth/1.0 (+https://autolycus.app)",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:  # nosec B310
        return json.loads(resp.read().decode("utf-8"))


def _build_discord_avatar_url(user: dict[str, Any]) -> str | None:
    """Return a Discord CDN avatar URL (custom or default) for a user payload."""
    user_id_raw = user.get("id")
    if user_id_raw is None:
        return None

    user_id = str(user_id_raw).strip()
    if not user_id:
        return None

    avatar_hash = str(user.get("avatar") or "").strip()
    if avatar_hash:
        ext = "gif" if avatar_hash.startswith("a_") else "png"
        return f"https://cdn.discordapp.com/avatars/{user_id}/{avatar_hash}.{ext}?size=128"

    # No custom avatar: Discord serves one of the default embed avatars.
    discriminator = str(user.get("discriminator") or "").strip()
    try:
        if discriminator and discriminator != "0":
            index = int(discriminator) % 5
        else:
            index = (int(user_id) >> 22) % 6
    except (TypeError, ValueError):
        index = 0
    return f"https://cdn.discordapp.com/embed/avatars/{index}.png"


def _extract_discord_http_error(exc: urllib.error.HTTPError) -> tuple[str | None, str]:
    """
    Parse Discord OAuth HTTPError response into a short diagnostic string.
    Returns (discord_error_code, human_message).
    """
    try:
        body = exc.read().decode("utf-8", errors="replace")
    except Exception:
        body = ""

    if body:
        try:
            payload = json.loads(body)
            if isinstance(payload, dict):
                err = str(payload.get("error", "")).strip() or None
                desc = str(payload.get("error_description", "")).strip()
                if err and desc:
                    return err, f"{err}: {desc}"
                if err:
                    return err, err
        except Exception:
            # Keep fallback message below if payload is not JSON.
            pass
        # Non-JSON body (e.g. proxy/WAF HTML) can still explain the 403.
        compact = " ".join(body.split())
        preview = compact[:240]
        return None, f"HTTP {exc.code} from Discord OAuth endpoint. Body: {preview}"

    return None, f"HTTP {exc.code} from Discord OAuth endpoint"


@auth_bp.route('/discord/start', methods=['GET'])
def start_discord_oauth() -> Any:
    """Start official Discord OAuth login flow."""
    if not _oauth_discord_enabled():
        return jsonify({
            'error': 'Service unavailable',
            'message': 'Discord OAuth is not configured.',
            'code': 'OAUTH_NOT_CONFIGURED'
        }), 503

    state = secrets.token_urlsafe(24)
    redirect_target = request.args.get("redirect", "/raids")
    # Internal paths only.
    if not redirect_target.startswith("/"):
        redirect_target = "/raids"

    session["oauth_state"] = state
    session["oauth_redirect"] = redirect_target
    redirect_uri = _resolve_discord_redirect_uri()

    params = urllib.parse.urlencode({
        "client_id": current_app.config.get("DISCORD_CLIENT_ID", ""),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": "identify",
        "state": state,
        "prompt": "consent",
    })
    return redirect(f"https://discord.com/oauth2/authorize?{params}", code=302)


@auth_bp.route('/discord/callback', methods=['GET'])
def discord_oauth_callback() -> Any:
    """Handle Discord OAuth callback and establish web session."""
    if not _oauth_discord_enabled():
        return jsonify({
            'error': 'Service unavailable',
            'message': 'Discord OAuth is not configured.',
            'code': 'OAUTH_NOT_CONFIGURED'
        }), 503

    code = request.args.get("code")
    state = request.args.get("state")
    expected_state = session.get("oauth_state")
    redirect_target = session.get("oauth_redirect", "/raids")

    if not code or not state or not expected_state or state != expected_state:
        return jsonify({
            'error': 'Invalid OAuth state',
            'message': 'The Discord sign-in request could not be verified.',
            'code': 'OAUTH_STATE_INVALID'
        }), 401

    try:
        token_data = _oauth_exchange_code_for_token(code)
        access_token = token_data.get("access_token")
        if not access_token:
            return jsonify({
                'error': 'Authentication failed',
                'message': 'Discord did not return an access token.',
                'code': 'OAUTH_TOKEN_MISSING'
            }), 401
        user = _oauth_fetch_user(access_token)
        discord_user_id = user.get("id")
        if not discord_user_id:
            return jsonify({
                'error': 'Authentication failed',
                'message': 'Discord user details were incomplete.',
                'code': 'OAUTH_USER_INVALID'
            }), 401
        session["discord_user_id"] = int(discord_user_id)
        session["discord_username"] = user.get("username")
        session["discord_global_name"] = user.get("global_name")
        session["discord_avatar"] = user.get("avatar")
        session["discord_avatar_url"] = _build_discord_avatar_url(user)
        session["discord_authenticated_at"] = int(time.time())
        session.permanent = True
        session.pop("oauth_state", None)
        session.pop("oauth_redirect", None)
        return redirect(str(redirect_target), code=302)
    except urllib.error.HTTPError as exc:
        discord_error, reason = _extract_discord_http_error(exc)
        logger.error("Discord OAuth callback HTTP error: %s", reason, exc_info=True)
        return jsonify({
            'error': 'Authentication failed',
            'message': 'Discord sign-in failed during token exchange/user lookup.',
            'code': 'OAUTH_FAILED',
            'reason': reason,
            'discord_error': discord_error,
        }), 401
    except Exception as exc:
        logger.error("Discord OAuth callback failed: %s", exc, exc_info=True)
        return jsonify({
            'error': 'Authentication failed',
            'message': 'Discord sign-in failed. Please try again.',
            'code': 'OAUTH_FAILED',
            'reason': str(exc),
        }), 401


@auth_bp.route('/me', methods=['GET'])
def get_auth_me() -> tuple[Any, int]:
    """Return current Discord-authenticated session state."""
    raw = session.get("discord_user_id")
    try:
        user_id = int(raw) if raw is not None else None
    except (TypeError, ValueError):
        user_id = None
    if user_id is None:
        return jsonify({'authenticated': False}), 200
    return jsonify({
        'authenticated': True,
        'discord_user_id': user_id,
        'username': session.get("discord_username"),
        'global_name': session.get("discord_global_name"),
        'avatar': session.get("discord_avatar"),
        'avatar_url': session.get("discord_avatar_url"),
        'authenticated_at': session.get("discord_authenticated_at"),
    }), 200


@auth_bp.route('/linked-nation', methods=['GET'])
@require_discord_session
def get_linked_nation() -> tuple[Any, int]:
    """Return linked nation id for the current Discord-authenticated user."""
    user_id = getattr(request, "session_user_id", None)
    if user_id is None:
        return jsonify({
            "authenticated": False,
            "linked": False,
            "nation_id": None,
            "nation_name": None,
            "flag_url": None,
        }), 200

    mongo_db = get_sync_db()
    if mongo_db is None:
        return jsonify({
            "error": "Database unavailable",
            "message": "MongoDB is not configured.",
            "code": "DB_UNAVAILABLE",
        }), 503

    try:
        uid = int(user_id)
    except (TypeError, ValueError):
        return jsonify({
            "error": "Invalid user id",
            "message": "user_id must be numeric.",
            "code": "INVALID_USER",
        }), 400

    profile = mongo_db.global_users.find_one({"user": uid}) or {}
    nation_id = profile.get("id")
    nation_id_text = str(nation_id).strip() if nation_id is not None else ""
    nation_name: str | None = None
    flag_url: str | None = None

    if nation_id_text:
        api_key = str(current_app.config.get("API_KEY") or "").strip()
        if api_key:
            query = f"""
            {{
              nations(first: 1 id: {nation_id_text}) {{
                data {{
                  id
                  nation_name
                  flag
                }}
              }}
            }}
            """
            try:
                response = asyncio.run(call_pnw(query, api_key=api_key))
                data = (
                    ((response or {}).get("data") or {})
                    .get("nations", {})
                    .get("data", [])
                )
                if data:
                    nation = data[0] or {}
                    nation_name = str(nation.get("nation_name") or "").strip() or None
                    flag_url = str(nation.get("flag") or "").strip() or None
            except Exception as exc:
                logger.warning("Could not enrich linked nation metadata for %s: %s", nation_id_text, exc)

    return jsonify({
        "authenticated": True,
        "linked": bool(nation_id_text),
        "nation_id": nation_id_text or None,
        "nation_name": nation_name,
        "flag_url": flag_url,
    }), 200


@auth_bp.route('/logout', methods=['POST'])
def logout_discord_session() -> tuple[Any, int]:
    """Clear Discord-authenticated web session."""
    session.pop("discord_user_id", None)
    session.pop("discord_username", None)
    session.pop("discord_global_name", None)
    session.pop("discord_avatar", None)
    session.pop("discord_avatar_url", None)
    session.pop("discord_authenticated_at", None)
    session.pop("oauth_state", None)
    session.pop("oauth_redirect", None)
    return jsonify({'success': True, 'message': 'Logged out'}), 200


@auth_bp.route('/verify', methods=['POST'])
@require_discord_session
def verify_discord_link() -> tuple[Any, int]:
    """Verify/link the current Discord web session to a nation."""
    try:
        user_id = getattr(request, "session_user_id", None)
        username = str(session.get("discord_username") or "").strip()
        if user_id is None or not username:
            return jsonify({
                "error": "Authentication required",
                "message": "Please sign in with Discord to verify from web.",
                "code": "AUTH_REQUIRED",
            }), 401

        data = request.get_json() or {}
        nation_input = str(data.get("nationId") or "").strip()
        if not nation_input:
            return jsonify({
                "error": "Validation error",
                "message": "nationId is required.",
                "code": "VALIDATION_ERROR",
            }), 400

        api_key = str(current_app.config.get("API_KEY") or "").strip()
        if not api_key:
            return jsonify({
                "error": "Service unavailable",
                "message": "Verification is unavailable because API_KEY is not configured.",
                "code": "API_KEY_NOT_CONFIGURED",
            }), 503

        async def _call_func(query: str) -> dict[str, Any]:
            return await call_pnw(query, api_key=api_key)

        result = asyncio.run(verify_discord_nation_link(
            discord_user_id=int(user_id),
            discord_username=username,
            nation_input=nation_input,
            call_func=_call_func,
        ))

        if result["ok"]:
            return jsonify({
                "success": True,
                "code": result["code"],
                "message": "Verification successful.",
                "nationId": result["nation_id"],
                "relinked": result["relinked"],
            }), 200

        code_to_status = {
            "INVALID_NATION_ID": 400,
            "NOT_FOUND": 404,
            "OWNERSHIP_MISMATCH": 400,
            "LINK_CONFLICT": 409,
        }
        return jsonify({
            "success": False,
            "code": result["code"],
            "message": result["message"],
            "nationId": result["nation_id"],
            "relinked": False,
        }), code_to_status.get(result["code"], 400)
    except Exception as exc:
        logger.error("Web verification failed: %s", exc, exc_info=True)
        return jsonify({
            "error": "Verification failed",
            "message": "An unexpected error occurred while verifying.",
            "code": "VERIFY_ERROR",
        }), 500

def _normalize_api_key(value: Any) -> str:
    """Normalize API key values for comparison.

    Strips whitespace and optional surrounding quotes to avoid mismatches
    when env files include quoted values.
    """
    if value is None:
        return ""
    text = str(value).strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in ('"', "'"):
        return text[1:-1].strip()
    return text


@auth_bp.route('/token/generate', methods=['POST'])
def generate_access_token() -> tuple[Any, int]:
    """
    Generate a secure access token for web interface usage.
    
    This endpoint allows the web frontend to generate tokens for accessing
    protected resources (raids, builds, damage) without requiring Discord bot
    interaction first.
    
    Request Body:
        - user_id: Discord user ID (optional, defaults to 'web_user')
        - data_type: Type of data being accessed (raids, builds, damage)
        - expires_in: Token expiration time in seconds (optional, default: 3600)
    
    Returns:
        JSON response with:
        - token: The generated access token
        - expires_at: Unix timestamp when token expires
        - data_type: The data type this token is for
    
    Example:
        POST /api/auth/token/generate
        {
            "user_id": 123456789,
            "data_type": "raids"
        }
        
        Response:
        {
            "token": "eyJ...",
            "expires_at": 1704067200,
            "data_type": "raids"
        }
    """
    try:
        data = request.get_json() or {}
        
        # Extract parameters with defaults
        user_id = data.get('user_id')
        data_type = data.get('data_type', 'raids')
        expires_in = data.get('expires_in', 3600)  # 1 hour default

        # Require shared secret for token generation (server-to-server only)
        auth_key = _normalize_api_key(current_app.config.get("AUTH_TOKEN_API_KEY"))
        if not auth_key:
            return jsonify({
                'error': 'Service unavailable',
                'message': 'Token generation is disabled until AUTH_TOKEN_API_KEY is configured.',
                'code': 'AUTH_KEY_NOT_CONFIGURED'
            }), 503

        provided = _normalize_api_key(
            request.headers.get("X-Auth-Token") or request.headers.get("X-Api-Key")
        )
        if provided != auth_key:
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Invalid or missing API key.',
                'code': 'UNAUTHORIZED'
            }), 401
        
        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid user id',
                'message': 'user_id must be numeric.',
                'code': 'INVALID_USER'
            }), 400

        # Validate data_type
        valid_types = ['raids', 'builds', 'damage']
        if data_type not in valid_types:
            return jsonify({
                'error': 'Invalid data type',
                'message': f'data_type must be one of: {", ".join(valid_types)}',
                'code': 'INVALID_DATA_TYPE'
            }), 400
        
        # Validate expiration window
        try:
            expires_in = int(expires_in)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid parameter',
                'message': 'expires_in must be an integer (seconds)',
                'code': 'INVALID_PARAMETER'
            }), 400

        max_age = int(current_app.config.get('TOKEN_MAX_AGE', 3600 * 24 * 7))
        if expires_in < 60 or expires_in > max_age:
            return jsonify({
                'error': 'Invalid parameter',
                'message': f'expires_in must be between 60 and {max_age} seconds',
                'code': 'INVALID_PARAMETER'
            }), 400

        # Generate timestamp
        timestamp = int(time.time())
        
        # Generate token with the provided data
        token = generate_token(
            user_id=user_id,
            timestamp=timestamp,
            data_type=data_type,
            expires_in=expires_in
        )
        
        logger.info(f"Generated token for user_id={user_id}, data_type={data_type}")
        
        return jsonify({
            'token': token,
            'expires_at': timestamp + expires_in,
            'data_type': data_type,
            'message': 'Token generated successfully'
        }), 200
        
    except Exception as e:
        logger.error(f"Error generating token: {e}", exc_info=True)
        return jsonify({
            'error': 'Token generation failed',
            'message': 'An unexpected error occurred while generating token.',
            'code': 'GENERATION_ERROR'
        }), 500


@auth_bp.route('/token/issue', methods=['POST'])
def issue_discord_token_code() -> tuple[Any, int]:
    """
    Issue a short-lived authorization code for a Discord user.

    This endpoint is intended for the Discord bot only and requires a
    server-side shared secret.
    """
    try:
        bot_key = _normalize_api_key(current_app.config.get("DISCORD_BOT_API_KEY"))
        if not bot_key:
            return jsonify({
                'error': 'Service unavailable',
                'message': 'Bot token issuance is disabled until DISCORD_BOT_API_KEY is configured.',
                'code': 'BOT_KEY_NOT_CONFIGURED'
            }), 503

        provided = _normalize_api_key(
            request.headers.get("X-Bot-Token") or request.headers.get("X-Api-Key")
        )
        if provided != bot_key:
            return jsonify({
                'error': 'Unauthorized',
                'message': 'Invalid or missing bot API key.',
                'code': 'UNAUTHORIZED'
            }), 401

        data = request.get_json() or {}
        user_id = data.get('user_id')
        data_type = data.get('data_type', 'raids')
        expires_in = data.get('expires_in', 3600)

        try:
            user_id = int(user_id)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid user id',
                'message': 'user_id must be numeric.',
                'code': 'INVALID_USER'
            }), 400

        valid_types = ['raids', 'builds', 'damage']
        if data_type not in valid_types:
            return jsonify({
                'error': 'Invalid data type',
                'message': f'data_type must be one of: {", ".join(valid_types)}',
                'code': 'INVALID_DATA_TYPE'
            }), 400

        try:
            expires_in = int(expires_in)
        except (TypeError, ValueError):
            return jsonify({
                'error': 'Invalid parameter',
                'message': 'expires_in must be an integer (seconds)',
                'code': 'INVALID_PARAMETER'
            }), 400

        max_age = int(current_app.config.get('TOKEN_MAX_AGE', 3600 * 24 * 7))
        if expires_in < 60 or expires_in > max_age:
            return jsonify({
                'error': 'Invalid parameter',
                'message': f'expires_in must be between 60 and {max_age} seconds',
                'code': 'INVALID_PARAMETER'
            }), 400

        mongo_db = get_sync_db()
        if mongo_db is None:
            return jsonify({
                'error': 'Database unavailable',
                'message': 'MongoDB is not configured.',
                'code': 'DB_UNAVAILABLE'
            }), 503

        now = int(time.time())
        code_ttl = 300  # 5 minutes
        code = secrets.token_urlsafe(32)

        mongo_db.auth_codes.insert_one({
            'code': code,
            'user_id': user_id,
            'data_type': data_type,
            'expires_in': expires_in,
            'created_at': now,
            'expires_at': now + code_ttl,
            'used': False,
        })

        return jsonify({
            'code': code,
            'expires_at': now + code_ttl,
            'data_type': data_type,
            'message': 'Authorization code issued'
        }), 200
    except Exception as e:
        logger.error(f"Error issuing auth code: {e}", exc_info=True)
        return jsonify({
            'error': 'Auth code issuance failed',
            'message': 'An unexpected error occurred while issuing code.',
            'code': 'ISSUE_ERROR'
        }), 500


@auth_bp.route('/token/exchange', methods=['POST'])
def exchange_token_code() -> tuple[Any, int]:
    """Exchange a short-lived auth code for a signed access token."""
    try:
        data = request.get_json() or {}
        code = data.get('code')
        if not code:
            return jsonify({
                'error': 'Validation error',
                'message': 'code is required.',
                'code': 'VALIDATION_ERROR'
            }), 400

        mongo_db = get_sync_db()
        if mongo_db is None:
            return jsonify({
                'error': 'Database unavailable',
                'message': 'MongoDB is not configured.',
                'code': 'DB_UNAVAILABLE'
            }), 503

        now = int(time.time())
        doc = mongo_db.auth_codes.find_one({'code': code})
        if not doc:
            return jsonify({
                'error': 'Invalid code',
                'message': 'Authorization code is invalid or expired.',
                'code': 'CODE_INVALID'
            }), 401
        if doc.get('used'):
            return jsonify({
                'error': 'Code used',
                'message': 'Authorization code has already been used.',
                'code': 'CODE_USED'
            }), 401
        if now > int(doc.get('expires_at', 0)):
            return jsonify({
                'error': 'Code expired',
                'message': 'Authorization code has expired.',
                'code': 'CODE_EXPIRED'
            }), 401

        user_id = doc.get('user_id')
        data_type = doc.get('data_type', 'raids')
        expires_in = int(doc.get('expires_in', 3600))

        token = generate_token(
            user_id=user_id,
            timestamp=now,
            data_type=data_type,
            expires_in=expires_in,
        )

        mongo_db.auth_codes.update_one(
            {'code': code},
            {'$set': {'used': True, 'used_at': now}}
        )

        return jsonify({
            'token': token,
            'expires_at': now + expires_in,
            'data_type': data_type,
            'message': 'Token issued successfully'
        }), 200

    except Exception as e:
        logger.error(f"Error exchanging auth code: {e}", exc_info=True)
        return jsonify({
            'error': 'Token exchange failed',
            'message': 'An unexpected error occurred while exchanging code.',
            'code': 'EXCHANGE_ERROR'
        }), 500


@auth_bp.route('/token/verify', methods=['POST'])
def verify_access_token() -> tuple[Any, int]:
    """
    Verify if a token is valid without consuming it.
    
    Request Body:
        - token: The token to verify
    
    Returns:
        JSON response with:
        - valid: Boolean indicating if token is valid
        - payload: Decoded token data (if valid)
        - error: Error message (if invalid)
    """
    try:
        from api.security import (TokenExpiredError, TokenInvalidError,
                                  verify_token)
        
        data = request.get_json() or {}
        token = data.get('token')
        
        if not token:
            return jsonify({
                'valid': False,
                'error': 'Token is required',
                'code': 'TOKEN_MISSING'
            }), 400
        
        try:
            payload = verify_token(token)
            return jsonify({
                'valid': True,
                'payload': payload,
                'message': 'Token is valid'
            }), 200
        except TokenExpiredError:
            return jsonify({
                'valid': False,
                'error': 'Token has expired',
                'code': 'TOKEN_EXPIRED'
            }), 401
        except TokenInvalidError:
            return jsonify({
                'valid': False,
                'error': 'Token is invalid',
                'code': 'TOKEN_INVALID'
            }), 401
            
    except Exception as e:
        logger.error(f"Error verifying token: {e}", exc_info=True)
        return jsonify({
            'error': 'Token verification failed',
            'message': 'An unexpected error occurred.',
            'code': 'VERIFICATION_ERROR'
        }), 500
