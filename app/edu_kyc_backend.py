"""
Part 4: Edu-KYC + Sybil Resistance.

Xác thực giáo dục (education credential) để:
1. Tăng điểm tín dụng (+30)
2. Chặn multi-account (Sybil resistance)

Các provider: Google, GitHub, LinkedIn, BrainDAO, ...
Ở đây: Mock provider cho demo (bật trong 5s, sau đó tắt).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional
import time


@dataclass
class EduCredential:
    """Giáo dục xác thực."""
    wallet: str         # address này xác thực được
    provider: str       # "google", "github", "linkedin", etc.
    credential_id: str  # external ID (nên hash)
    verified_at: int    # timestamp


# Mock storage (trong thực tế: DB hoặc contract)
_edu_verified: dict[str, EduCredential] = {}
_provider_config = {
    "google": {
        "client_id": "MOCK_GOOGLE_CLIENT_ID",
        "redirect_uri": "http://localhost:8501",  # Streamlit local
    },
    "github": {
        "client_id": "MOCK_GITHUB_CLIENT_ID",
        "redirect_uri": "http://localhost:8501",
    },
}


def get_edu_providers() -> list[str]:
    """Lấy danh sách provider khả dụng."""
    return list(_provider_config.keys())


def mark_edu_verified(wallet: str, provider: str, credential_id: str) -> EduCredential:
    """
    Đánh dấu wallet đã xác thực giáo dục.
    Dùng cho demo hoặc mock.
    """
    cred = EduCredential(
        wallet=wallet,
        provider=provider,
        credential_id=credential_id,
        verified_at=int(time.time()),
    )
    _edu_verified[wallet.lower()] = cred
    return cred


def is_edu_verified(wallet: str) -> bool:
    """Kiểm tra wallet đã xác thực giáo dục chưa."""
    return wallet.lower() in _edu_verified


def get_edu_credential(wallet: str) -> Optional[EduCredential]:
    """Lấy credential của wallet (nếu có)."""
    return _edu_verified.get(wallet.lower())


def mock_oauth_flow(provider: str, wallet: str) -> EduCredential:
    """
    Giả OAuth flow (demo).

    Trong thực tế:
    1. Redirect user đến provider
    2. Provider yêu cầu user login + cấp quyền
    3. Return access token tới Streamlit callback
    4. Streamlit verify token + extract credential ID
    5. Mark verified

    Ở đây chỉ mock: đánh dấu verified sau 1 giây.
    """
    if provider not in _provider_config:
        raise ValueError(f"Provider không hỗ trợ: {provider}")

    # Giả credential ID từ provider
    mock_credential_id = f"{provider}_{wallet[:8]}"

    # Đánh dấu verified
    cred = mark_edu_verified(wallet, provider, mock_credential_id)

    return cred


def revoke_edu_verification(wallet: str) -> bool:
    """Huỷ xác thực giáo dục của wallet (admin)."""
    if wallet.lower() in _edu_verified:
        del _edu_verified[wallet.lower()]
        return True
    return False
