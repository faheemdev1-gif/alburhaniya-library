import unittest

from scripts.build_index import annotate_diwan_pages


class QasidaNumberingTests(unittest.TestCase):
    def test_numeric_headings_are_authoritative(self):
        pages = []
        for number in (1, 73, 91, 95):
            pages.append({
                "printed_page": str(number),
                "paragraphs": [
                    f"الْقَصِيدَة {number}: (عُنْوَانُ الْقَصِيدَةِ {number})\n"
                    f"التّاريخ: الأربعاء\n1 - بَيْتُ الْقَصِيدَةِ {number}"
                ],
            })

        annotated = annotate_diwan_pages(pages)

        self.assertEqual(
            [page["qasida_number"] for page in annotated],
            [1, 73, 91, 95],
        )

    def test_single_digit_numeric_headings_are_not_skipped(self):
        pages = []
        for number in range(1, 11):
            pages.append({
                "printed_page": str(number),
                "paragraphs": [
                    f"الْقَصِيدَة {number}: (عُنْوَان {number})\n"
                    f"التّاريخ: الجمعة\n1 - بَيْت {number}"
                ],
            })

        annotated = annotate_diwan_pages(pages)

        self.assertEqual(
            [page["qasida_number"] for page in annotated],
            list(range(1, 11)),
        )

    def test_arabic_indic_numeric_heading_is_supported(self):
        pages = [{
            "printed_page": "261",
            "paragraphs": [
                "الْقَصِيدَة ٩١: (بِأَحْمَدَ حَيْثُ الأَحْمَدِيَّةُ يَهْتَدِي)\n"
                "التّاريخ: الأربعاء\n9 - فَمَا طَلَعَتْ إِلَّا وَغَابَ ضِيَاؤُهَا"
            ],
        }]

        annotated = annotate_diwan_pages(pages)

        self.assertEqual(annotated[0]["qasida_number"], 91)
        self.assertEqual(annotated[0]["bayt_from"], 9)

    def test_explanatory_qasida_note_does_not_advance_number(self):
        pages = [
            {
                "printed_page": "56",
                "paragraphs": [
                    "الْقَصِيدَة الرّابِعَة: (تَاللَّهِ مَا نَضَبَ الْمَعِينُ)\n"
                    "التّاريخ: الأربعاء\n1 - تَاللَّهِ مَا نَضَبَ الْمَعِينُ"
                ],
            },
            {
                "printed_page": "58",
                "paragraphs": [
                    "ملحوظة: هذه القصيدة لها ثلاث قوافي: الياء والنون والباء"
                ],
            },
            {
                "printed_page": "59",
                "paragraphs": [
                    "الْقَصِيدَة الْخَامِسَة: (اللَّهُ مِنْ بَعْدِ الزِّيَادَةِ زَادَنِي)\n"
                    "التّاريخ: الجمعة\n1 - اللَّهُ مِنْ بَعْدِ الزِّيَادَةِ زَادَنِي"
                ],
            },
        ]

        annotated = annotate_diwan_pages(pages)

        self.assertEqual(annotated[0]["qasida_number"], 1)
        self.assertEqual(annotated[1]["qasida_number"], 1)
        self.assertEqual(annotated[2]["qasida_number"], 2)

    def test_heading_without_date_is_not_counted(self):
        pages = [{
            "printed_page": "1",
            "paragraphs": ["القصيدة هي: كلام توضيحي لا عنوان مطبوع"],
        }]

        annotated = annotate_diwan_pages(pages)

        self.assertIsNone(annotated[0]["qasida_number"])


if __name__ == "__main__":
    unittest.main()
