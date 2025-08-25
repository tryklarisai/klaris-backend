"""
OAuth utilities for token management and refresh
"""
import os
import requests
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from google.oauth2.credentials import Credentials as GoogleCredentials


def refresh_google_oauth_token(refresh_token: str) -> Tuple[Optional[str], Optional[str], Optional[datetime]]:
    """
    Refresh Google OAuth access token using refresh token
    
    Args:
        refresh_token: The refresh token
        
    Returns:
        Tuple of (access_token, new_refresh_token, expiry_datetime) or (None, None, None) if failed
    """
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        return None, None, None
        
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }
    
    try:
        response = requests.post(token_url, data=data, timeout=30)
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            new_refresh_token = token_data.get("refresh_token", refresh_token)  # May not return new refresh token
            expires_in = token_data.get("expires_in", 3600)
            expiry = datetime.utcnow() + timedelta(seconds=expires_in)
            return access_token, new_refresh_token, expiry
        else:
            error_text = response.text
            print(f"Token refresh failed: {response.status_code} - {error_text}")
    except Exception as e:
        print(f"Token refresh error: {e}")
        
    return None, None, None


def get_valid_google_credentials(config: Dict[str, Any]) -> Tuple[Optional[GoogleCredentials], Dict[str, Any]]:
    """
    Get valid Google credentials, refreshing if necessary
    
    Args:
        config: Connector config containing oauth tokens
        
    Returns:
        Tuple of (GoogleCredentials object or None, updated_config_dict)
    """
    access_token = config.get("oauth_access_token")
    refresh_token = config.get("oauth_refresh_token")
    token_expiry_str = config.get("token_expiry")
    
    if not refresh_token:
        return None, config
        
    client_id = os.getenv("GOOGLE_CLIENT_ID")
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    
    if not client_id or not client_secret:
        return None, config
    
    # Check if token is expired
    token_expired = True
    if token_expiry_str and access_token:
        try:
            token_expiry = datetime.fromisoformat(token_expiry_str.replace('Z', '+00:00'))
            current_time = datetime.utcnow()
            expires_soon = current_time + timedelta(minutes=5)
            token_expired = expires_soon >= token_expiry
        except Exception:
            token_expired = True
    
    # Create a copy of config to potentially update
    updated_config = config.copy()
    
    # Refresh if expired or missing
    if token_expired or not access_token:
        new_access_token, new_refresh_token, expiry = refresh_google_oauth_token(refresh_token)
        if new_access_token:
            # Update config with new tokens
            updated_config["oauth_access_token"] = new_access_token
            if new_refresh_token != refresh_token:  # Only update if we got a new one
                updated_config["oauth_refresh_token"] = new_refresh_token
            if expiry:
                updated_config["token_expiry"] = expiry.isoformat()
            access_token = new_access_token
            refresh_token = updated_config["oauth_refresh_token"]
        else:
            return None, config
    
    creds = GoogleCredentials(
        token=access_token,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret
    )
    
    return creds, updated_config


def is_token_expired(token_expiry_str: Optional[str]) -> bool:
    """
    Check if a token is expired based on expiry string
    
    Args:
        token_expiry_str: ISO format datetime string of token expiry
        
    Returns:
        True if expired or invalid, False if still valid
    """
    if not token_expiry_str:
        return True
        
    try:
        token_expiry = datetime.fromisoformat(token_expiry_str.replace('Z', '+00:00'))
        # Consider token expired if it expires within 5 minutes
        return datetime.utcnow() + timedelta(minutes=5) >= token_expiry
    except Exception:
        return True