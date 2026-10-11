"""Bounded string checks for known private résumé output and provider fields."""

from __future__ import annotations

import re


_CONTACT = re.compile(
    r"@|\b(?:https?://|www\.)|\b[\w.-]+\.(?:com|org|net|io|ru|rs|dev|me|uk|eu)/\S+|"
    r"(?<!\w)\+\d{7,15}(?!\w)|"
    r"\b(?:e-?mail|phone|mobile|tel(?:ephone)?|contact|whatsapp|telegram|"
    r"телефон|почта|контакт)\s*[:：]|"
    r"(?<![\w])(?:\+?\d{1,3}[ .-])?(?:\(\d{2,4}\)|\d{2,4})[ .-]\d{3,4}[ .-]\d{4}(?!\w)|"
    r"(?<![\w])(?:\+?\d{1,3}[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{2}[ .-]\d{2}(?!\w)|"
    r"(?<![\w])\d{3}[ .-]\d{4}(?!\w)", re.I)
_BARE_PHONE = re.compile(r"(?<!\w)\d{10,11}(?!\w)")
_PHONE_CONTEXT = re.compile(
    r"\b(?:call|text|reach|contact|phone|mobile|tel|number|whatsapp|telegram|"
    r"телефон|номер|связь|позвон\w*)\b", re.I)
_LABELED_PERSONAL_SITE = re.compile(
    r"\b(?:portfolio|website|web\s*site|personal\s*(?:site|website)|linkedin|github|gitlab|"
    r"портфолио|личный\s+сайт|сайт)\s*[:：]\s*(?:[\w-]+\.)+[a-z]{2,24}(?!\w)", re.I)
_PRIVATE_METADATA = re.compile(
    r"\b(?:age|возраст)\s*[:：,\-]?\s*\d{1,3}\b|"
    r"\b(?:date of birth|birth\s*date|birthdate|дата рождения|год рождения)\b|"
    r"\b(?:resume|résumé|cv|резюме)\s*(?:id|#|№|updated|posted|обновлено|размещено)\b|"
    r"\b(?:job[ -]?board|сайт вакансий|источник резюме)\s*[:：]\s*\S+", re.I)


def private_output_text(text: str) -> bool:
    """Recognize concrete contact, age and job-board forms without guessing redactions."""
    if _CONTACT.search(text) or _LABELED_PERSONAL_SITE.search(text) or _PRIVATE_METADATA.search(text):
        return True
    bare = _BARE_PHONE.search(text)
    return bool(bare and (text.strip() == bare.group() or _PHONE_CONTEXT.search(text)))
