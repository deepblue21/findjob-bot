"""
Kişisel profil yükleyici — profile.yaml'dan CV/profil bilgilerini okur.
(Modül adı 'user_profile'; stdlib'deki 'profile' ile çakışmaması için.)
"""
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)
PROFILE_PATH = Path(__file__).parent / "profile.yaml"


def load_profile() -> dict:
    """profile.yaml içeriğini döndürür; yoksa boş dict."""
    if not PROFILE_PATH.exists():
        return {}
    try:
        with open(PROFILE_PATH, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning(f"profile.yaml okunamadı: {e}")
        return {}


def profile_scoring(profile: dict) -> dict[str, float]:
    """
    Profildeki 'skills' listesini puanlama ağırlıklarına çevirir.
      - "selenium"          -> {'selenium': skill_weight}
      - {"sql": 1}          -> {'sql': 1}
    """
    weights: dict[str, float] = {}
    default = float(profile.get("skill_weight", 2) or 2)
    for item in profile.get("skills", []) or []:
        if isinstance(item, dict):
            for k, v in item.items():
                weights[str(k).strip().lower()] = float(v)
        elif item:
            weights[str(item).strip().lower()] = default
    return weights
