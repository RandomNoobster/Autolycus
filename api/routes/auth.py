"""
Auth API Routes

This module provides endpoints for generating secure tokens for accessing
protected resources without requiring pre-existing Discord bot interaction.
"""
import logging
import secrets
import time
from typing import Any

from flask import Blueprint, current_app, jsonify, request

from api.security import generate_token
from database.mongo import get_sync_db

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')

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
