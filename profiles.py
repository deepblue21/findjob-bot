"""
Çok profilli yükleyici — profiles/*.yaml dosyalarını okur.
Her profil = bir kişi (CV) + kendi arama ayarları + becerileri.
"""
import logging
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)
PROFILES_DIR = Path(__file__).parent / "profiles"


def _load_yaml(p: Path) -> dict:
    with open(p, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def list_profiles() -> list[dict]:
    """profiles/ klasöründeki tüm profilleri döndür (dosya adı sırasına göre)."""
    if not PROFILES_DIR.exists():
        return []
    out = []
    for p in sorted(PROFILES_DIR.glob("*.yaml")):
        if p.name.startswith(("_", ".")) or p.name == "example.yaml":
            continue  # gecici/fixture/sablon dosyalari atla
        try:
            d = _load_yaml(p)
            d["key"] = d.get("key") or p.stem
            out.append(d)
        except Exception as e:
            logger.warning(f"Profil okunamadı {p.name}: {e}")
    out.sort(key=lambda d: (d.get("order", 99), d["key"]))
    return out


def get_profile(key: str) -> dict | None:
    for d in list_profiles():
        if d.get("key") == key:
            return d
    return None


def profile_keys() -> list[str]:
    return [d["key"] for d in list_profiles()]


def profile_scoring(profile: dict) -> dict[str, float]:
    """Profildeki 'skills' listesini puanlama ağırlıklarına çevirir."""
    weights: dict[str, float] = {}
    default = float(profile.get("skill_weight", 2) or 2)
    for item in profile.get("skills", []) or []:
        if isinstance(item, dict):
            for k, v in item.items():
                weights[str(k).strip().lower()] = float(v)
        elif item:
            weights[str(item).strip().lower()] = default
    return weights
