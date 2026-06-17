"""Türkiye il listesi ve basit şehir eşleştirme yardımcıları."""

TURKISH_CITIES = [
    "Adana", "Adıyaman", "Afyonkarahisar", "Ağrı", "Amasya", "Ankara", "Antalya",
    "Artvin", "Aydın", "Balıkesir", "Bilecik", "Bingöl", "Bitlis", "Bolu",
    "Burdur", "Bursa", "Çanakkale", "Çankırı", "Çorum", "Denizli", "Diyarbakır",
    "Edirne", "Elazığ", "Erzincan", "Erzurum", "Eskişehir", "Gaziantep",
    "Giresun", "Gümüşhane", "Hakkari", "Hatay", "Isparta", "Mersin", "İstanbul",
    "İzmir", "Kars", "Kastamonu", "Kayseri", "Kırklareli", "Kırşehir",
    "Kocaeli", "Konya", "Kütahya", "Malatya", "Manisa", "Kahramanmaraş",
    "Mardin", "Muğla", "Muş", "Nevşehir", "Niğde", "Ordu", "Rize", "Sakarya",
    "Samsun", "Siirt", "Sinop", "Sivas", "Tekirdağ", "Tokat", "Trabzon",
    "Tunceli", "Şanlıurfa", "Uşak", "Van", "Yozgat", "Zonguldak", "Aksaray",
    "Bayburt", "Karaman", "Kırıkkale", "Batman", "Şırnak", "Bartın", "Ardahan",
    "Iğdır", "Yalova", "Karabük", "Kilis", "Osmaniye", "Düzce",
]

CITY_ALIASES = {
    "Mersin": ["İçel", "Icel"],
    "İzmir": ["T35"],
    "Manisa": ["T45"],
}


def tr_low(text: str) -> str:
    return (text or "").replace("İ", "i").replace("I", "i").replace("ı", "i").lower()


def _variants(value: str) -> set[str]:
    value = (value or "").strip()
    if not value:
        return set()
    return {
        value,
        value.lower(),
        value.upper(),
        value.replace("İ", "I"),
        value.replace("ı", "i"),
        tr_low(value),
    }


def city_variants(city: str) -> list[str]:
    city = (city or "").strip()
    if not city:
        return []
    variants = _variants(city)
    for alias in CITY_ALIASES.get(city, []):
        variants.update(_variants(alias))
    return [v for v in variants if v]
