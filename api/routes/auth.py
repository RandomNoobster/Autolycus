"""
Auth API Routes

This module provides endpoints for generating secure tokens for accessing
protected resources without requiring pre-existing Discord bot interaction.
"""
import logging
import time
from typing import Any

from flask import Blueprint, jsonify, request

from api.security import generate_token

logger = logging.getLogger(__name__)

auth_bp = Blueprint('auth', __name__, url_prefix='/api/auth')


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
        user_id = data.get('user_id', 'web_user')
        data_type = data.get('data_type', 'raids')
        expires_in = data.get('expires_in', 3600)  # 1 hour default
        
        # Validate data_type
        valid_types = ['raids', 'builds', 'damage']
        if data_type not in valid_types:
            return jsonify({
                'error': 'Invalid data type',
                'message': f'data_type must be one of: {", ".join(valid_types)}',
                'code': 'INVALID_DATA_TYPE'
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
