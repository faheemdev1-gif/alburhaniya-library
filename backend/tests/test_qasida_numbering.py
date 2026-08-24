import unittest

from scripts.build_index import _BAYT_NUMBER, annotate_diwan_pages, classify_block


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

    def test_parenthesized_bayt_openings_are_indexed(self):
        text = (
            "16- وَإِلَى رَسُولِ اللَّهِ شَدُّ رِحَالِنَا "
            "17- ( قُلْ هَذِهِ ) أَدْعُو إِلَيْهِ عَلَى هُدىً "
            "18- إِنَّ الشَّفَاعَةَ لِلْكِرَامِ"
        )
        self.assertEqual(
            [int(match.group(1)) for match in _BAYT_NUMBER.finditer(text)],
            [16, 17, 18],
        )

    def test_diwan_footer_and_qasida_total_are_authoritative(self):
        pages = [{
            "printed_page": "261",
            "paragraphs": [
                "الْقَصِيدَة الْحَادِيَة والتِّسْعُون: "
                "(بِأَحْمَدَ حَيْثُ الأَحْمَدِيَّةُ يَهْتَدِي)\n"
                "التّاريخ: الخميس\nعَدَد الأبيات: 22\n"
                "1 - بِأَحْمَدَ حَيْثُ الأَحْمَدِيَّةُ يَهْتَدِي\n[242]"
            ],
        }]
        page = annotate_diwan_pages(pages)[0]
        self.assertEqual(page["printed_page"], "242")
        self.assertEqual(page["qasida_bayt_count"], 22)
        self.assertIn("من 22", page["page_label"])

    def test_numbered_fihris_page_is_explicitly_toc(self):
        text = (
            "174 - فصل فى مقام الفراسة ... 175 - منزلة الرسول ... "
            "176 - خصاله ... 177 - فصل فى العلم ... 178 - فصل فى النور ... "
            "انتهى فهرس الجزء الثالث"
        )
        self.assertEqual(classify_block(text), "toc")


if __name__ == "__main__":
    unittest.main()
