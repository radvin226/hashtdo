# -*- coding: utf-8 -*-
"""لیست فحش‌ها برای فیلتر"""

SWEAR_WORDS = [
    # فارسی
    "کص", "کیر", "کون", "جنده", "مادرجنده", "ننه جنده", "کسکش", "کسخل",
    "گاییدم", "گوه", "عن", "خایه", "لاشی", "حرومزاده", "حرامزاده",
    "خفه شو", "گمشو", "برو گمشو", "سگ پدر", "ننه سگ",
    "کیری", "جقی", "جق", "ممه", "کص ننت", "ننتو", "مادرتو",
    "کصخل", "مادرت جنده", "ننت جنده", "کیرم", "کونت",
    # انگلیسی
    "fuck", "fck", "fuk", "shit", "bitch", "asshole", "bastard",
    "motherfucker", "mf", "cunt", "dick", "pussy", "cock", "whore",
    "slut", "faggot", "damn", "hell", "stfu", "fucker", "shithead",
    # ترکی
    "siktir", "orospu", "amk", "amına", "piç", "göt", "sik", "amq",
    # ایموجی
    "🍆", "🖕", "🍑", "💦", "🍌", "🌭", "👉👌", "👅"
]


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    text = (text
            .replace("ي", "ی")
            .replace("ك", "ک")
            .replace("ة", "ه")
            .replace("أ", "ا")
            .replace("إ", "ا")
            .replace("آ", "ا"))
    return text


def has_swear(text: str) -> bool:
    if not text:
        return False
    norm = normalize(text)
    for w in SWEAR_WORDS:
        if w.lower() in norm or w in text:
            return True
    return False
