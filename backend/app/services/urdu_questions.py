"""Translate fully recognized Urdu question frames for Arabic source discovery."""
import re
import unicodedata

# Keep the noun phrase and the requested relation separate. Unknown modifiers
# stay on the multilingual search path, including negations and comparisons.
_SUBJECTS = {
    "توبہ": "التوبة", "سچی توبہ": "التوبة النصوح",
    "اخلاص": "الإخلاص", "ذکر": "الذكر", "ذکر قلبی": "ذكر القلب",
    "دل کا ذکر": "ذكر القلب", "خلوت": "الخلوة", "مراقبہ": "المراقبة",
    "مرید": "المريد", "سچے مرید": "المريد الصادق",
    "سچا مرید": "المريد الصادق", "سیدنا محمد سے محبت": "محبة النبي",
    "نبی کریم سے محبت": "محبة النبي", "رسول اللہ سے محبت": "محبة الرسول",
    "نماز": "الصلاة", "استغفار": "الاستغفار", "توکل": "التوكل",
    "دل کی صفائی": "تزكية القلب", "نفس": "النفس", "شکر": "الشكر",
    "حسد": "الحسد", "دعا": "الدعاء", "عبادت": "العبادة",
    "امید": "الرجاء", "خوف": "الخوف", "صبر": "الصبر",
}
_RELATIONS = {
    "شرائط": "شروط", "شرطیں": "شروط", "نشانیاں": "علامات",
    "علامات": "علامات", "پہچان": "علامات", "فضیلت": "فضل",
    "اجر": "ثواب", "اہمیت": "أهمية", "فائدہ": "فائدة", "مطلب": "معنى",
}
_FRAME = re.compile(
    r"(.+?) (?:کا|کے|کی) (?:(?:کیا|کون سی) (\S+) (?:ہے|ہیں)|"
    r"(\S+) (?:کیا|کون سی) (?:ہے|ہیں))"
)


def discovery_question(query):
    text = unicodedata.normalize("NFC", query).strip(" ؟?")
    text = " ".join(text.split())
    # An explicit spiritual-path context is implicit in the corpus. Keep
    # every other qualifier for the multilingual model.
    text = text.removeprefix("سلوک میں ")
    match = _FRAME.fullmatch(text)
    if not match:
        return None
    subject = _SUBJECTS.get(match[1])
    relation = _RELATIONS.get(match[2] or match[3])
    return f"ما {relation} {subject}" if relation and subject else None
