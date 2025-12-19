"""
LLM Connection Testing Routes

Provides endpoints for testing LLM availability with caching.
"""

from flask import Blueprint, jsonify, request
from state.cache import llm_cache

bp = Blueprint('llm', __name__, url_prefix='/llm')


@bp.route('/test', methods=['GET'])
def test_connection():
    """
    Test LLM connection with caching.

    Returns cached result if less than 5 minutes old.

    Returns:
        JSON with connection status:
        {
            "available": bool,
            "cached": bool,
            "cache_age": int,
            "tested_at": str,
            "error": str (optional)
        }
    """
    result = llm_cache.get(force=False)
    return jsonify(result)


@bp.route('/test/force', methods=['POST'])
def test_connection_force():
    """
    Force fresh LLM connection test, bypassing cache.

    Returns:
        JSON with connection status (same format as /test)
    """
    result = llm_cache.get(force=True)
    return jsonify(result)


@bp.route('/cache/info', methods=['GET'])
def cache_info():
    """
    Get cache metadata without testing connection.

    Returns:
        JSON with cache information:
        {
            "has_cache": bool,
            "cache_age": int (or null),
            "expires_in": int (or null),
            "cached_result": dict (or null)
        }
    """
    info = llm_cache.get_cache_info()
    return jsonify(info)


@bp.route('/cache/clear', methods=['POST'])
def clear_cache():
    """
    Clear the LLM connection cache.

    Returns:
        JSON with success status
    """
    llm_cache.clear()
    return jsonify({
        'success': True,
        'message': 'Cache cleared'
    })
