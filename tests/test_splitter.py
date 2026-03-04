"""Tests for lok_sabha_dataset.splitter."""

from lok_sabha_dataset.splitter import split_question_answer


class TestHeadingAnswer:
    """Strategy 1: `## ANSWER` on its own line."""

    def test_standalone_heading(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF RAILWAYS

## LOK SABHA UNSTARRED QUESTION NO.374 TO BE ANSWERED ON 24.07.2024

## EARNING OF RAILWAYS

## 374. SMT. MALA ROY:

Will the Minister of RAILWAYS be pleased to state:

- (a) the details of revenue?
- (b) the amount earned?

## ANSWER

## MINISTER OF RAILWAYS (SHRI ASHWINI VAISHNAW)

- (a) to (b): A statement is laid on the Table of the House.

*****
"""
        q, a, method = split_question_answer(md)
        assert method == "heading_answer"
        assert q is not None
        assert a is not None
        assert "Will the Minister" in q
        assert "MINISTER OF RAILWAYS" in a
        assert "GOVERNMENT OF INDIA" not in q  # header stripped
        assert "*****" not in a  # footer stripped

    def test_heading_with_minister_on_same_line(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF EDUCATION

## LOK SABHA STARRED QUESTION NO. 99

## 99. SHRI SOMEONE:

Will the Minister of EDUCATION be pleased to state:

- (a) some question?
- (b) another question?

## ANSWER THE MINISTER OF EDUCATION (SHRI DHARMENDRA PRADHAN)

- (a) to (b) A statement is laid on the Table of the House.

*****
"""
        q, a, method = split_question_answer(md)
        assert method == "heading_answer"
        assert "Will the Minister" in q
        assert "DHARMENDRA PRADHAN" in a


class TestSpacedHeadingAnswer:
    """Strategy 2: `## A N S W E R` — Docling extraction artifact."""

    def test_spaced_heading(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF POWER LOK SABHA UNSTARRED QUESTION NO.2987

## ANSWERED ON 08.08.2024

## SMART CONSUMER METERS

2987 SHRI G LAKSHMINARAYANA: SHRI APPALANAIDU KALISETTI:

Will the Minister of POWER be pleased to state:

- (a) the total number of smart consumer meters sanctioned?

## A N S W E R

THE MINISTER OF STATE IN THE MINISTRY OF POWER (SHRI SHRIPAD NAIK)

(a): Details are as follows.
"""
        q, a, method = split_question_answer(md)
        assert method == "spaced_heading_answer"
        assert "Will the Minister" in q
        assert "SHRIPAD NAIK" in a


class TestStandaloneAnswer:
    """Strategy 3: `ANSWER` without ## prefix."""

    def test_answer_no_hash(self):
        md = """## GOVERNMENT OF INDIA

## LOK SABHA STARRED QUESTION NO. 102

*102. SHRI SUBBARAYAN K:

Will the Minister of RURAL DEVELOPMENT be pleased to state:

- (a) whether the Government proposes to increase days of work?
- (d) if so, the details thereof?

ANSWER MINISTER OF RURAL DEVELOPMENT (SHRI SHIVRAJ SINGH CHOUHAN)

- (a) to (d): A statement is laid on the Table of the House.
*****
"""
        q, a, method = split_question_answer(md)
        assert method == "standalone_answer"
        assert "Will the Minister" in q
        assert "SHIVRAJ SINGH CHOUHAN" in a


class TestSpacedStandaloneAnswer:
    """Strategy 4: `A N S W E R` without ## prefix."""

    def test_spaced_no_hash(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF POWER

## LOK SABHA UNSTARRED QUESTION NO. 2891

## ANSWERED ON 08.08.2024

## 2891. SHRI SOMEONE:

Will the Minister of POWER be pleased to state:

- (a) whether thermal power plants are being expanded?

A N S W E R

THE MINISTER OF STATE IN THE MINISTRY OF POWER

(a): Details are laid on the Table of the House.
"""
        q, a, method = split_question_answer(md)
        assert method == "spaced_standalone_answer"
        assert "Will the Minister" in q
        assert "MINISTER OF STATE" in a


class TestTableAnswer:
    """Strategy 5: ANSWER inside a markdown table row."""

    def test_answer_in_table_cell(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF MSME

## LOK SABHA STARRED QUESTION NO. *245

TO BE ANSWERED ON 08.08.2024

| *245. | SHRI ANURAG SINGH THAKUR: |
|-------|---------------------------|
| Will the Minister of MICRO, SMALL AND MEDIUM ENTERPRISES be pleased to state: |
| (a) some question? |
| ANSWER |
| MINISTER OF MSME (SHRI JITAN RAMMANJHI) |
| (a): Response text. |
"""
        q, a, method = split_question_answer(md)
        assert method == "table_answer"
        assert "pleased to state" in q
        assert "JITAN RAMMANJHI" in a


class TestInlineAnswer:
    """Strategy 6: ANSWER mid-line after punctuation."""

    def test_answer_after_semicolon(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF HOME AFFAIRS

## LOK SABHA UNSTARRED QUESTION NO. 2370

TO BE ANSWERED ON THE 6TH AUGUST, 2024

2370 SHRI KAMAKHYA PRASAD TASA:

Will the Minister of HOME AFFAIRS be pleased to state:

- (a) whether the promotion of members of CISF is on time;
- (d) the steps taken to remove stagnation? ANSWER MINISTER OF STATE IN THE MINISTRY OF HOME AFFAIRS (SHRI NITYANAND RAI)

(a) to (d): The Officers and personnel who complete the required residency period are considered for promotion.
"""
        q, a, method = split_question_answer(md)
        assert method == "inline_answer"
        assert "Will the Minister" in q
        assert "NITYANAND RAI" in a


class TestMinisterBoundary:
    """Strategy 7: No ANSWER marker, starts with ## MINISTER OF."""

    def test_minister_boundary(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF LABOUR AND EMPLOYMENT

## LOK SABHA STARRED QUESTION NO. 108

## *108. SHRI SOMEONE:

Will the Minister of LABOUR AND EMPLOYMENT be pleased to state:

- (a) whether the Government proposes to increase the upper salary limit?
- (c) its implementation?

## MINISTER OF LABOUR AND EMPLOYMENT (DR. MANSUKH MANDAVIYA)

(a) to (d): A statement is laid on the Table of the House.

*****
"""
        q, a, method = split_question_answer(md)
        assert method == "minister_boundary"
        assert "Will the Minister" in q
        assert "MANSUKH MANDAVIYA" in a


class TestMinisterBoundaryBare:
    """Strategy 8: MINISTER OF STATE without ## prefix."""

    def test_minister_of_state_no_heading(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF DEFENCE

## LOK SABHA UNSTARRED QUESTION NO. 3217

TO BE ANSWERED ON 09th August, 2024

## 3217 SHRI RAJEEV RAI:

Will the Minister of DEFENCE be pleased to state:

- (a) the total number of vacancies reserved for ex-servicemen?
- (b) details thereof?

MINISTER OF STATE IN THE MINISTRY OF DEFENCE

(SHRI SANJAY SETH)

(a) to (b): A statement is laid on the Table of the House.
"""
        q, a, method = split_question_answer(md)
        assert method == "minister_boundary_bare"
        assert "Will the Minister" in q
        assert "MINISTRY OF DEFENCE" in a


class TestHindiAnswer:
    """Strategy 9: Hindi `उत्तर` marker."""

    def test_hindi_answer_marker(self):
        md = """## भारत सरकार

## 1790. श्री विप्लि कुमार:

क्या नागर विमानन मंत्री यह बताने की कृपा करेंगे दकः

- (क) गत पांच वर्षों के दौरान जारी दकए गए पायलट लाइसेंसों की संख्या?

## उत्तर

## नागर विमानन मंत्रालय में राज्य मंत्री (श्री मुरलीधर मोहोल)

(क) विवरण नीचे दिया गया है।
"""
        q, a, method = split_question_answer(md)
        assert method == "hindi_answer"
        assert "कृपा करेंगे" in q
        assert "मुरलीधर मोहोल" in a


class TestTitleCaseAnswer:
    """## Answer (title case) should match via case-insensitive heading_answer."""

    def test_title_case_answer(self):
        md = """## GOVERNMENT OF INDIA

## LOK SABHA UNSTARRED QUESTION NO. 2745

## 2745. SHRI SOMEONE:

Will the Minister of DEVELOPMENT OF NORTH EASTERN REGION be pleased to state:

- (a) some question?

## Answer

The Minister of State of the Ministry of Development of North Eastern Region (Dr. Sukanta Majumdar)

(a): Response text.
"""
        q, a, method = split_question_answer(md)
        assert method == "heading_answer"
        assert "Will the Minister" in q
        assert "Sukanta Majumdar" in a


class TestReversedDocOrder:
    """Document where ANSWER appears at the very start, question below."""

    def test_answer_before_question(self):
        md = """## ANSWER

MINISTER OF CONSUMER AFFAIRS, FOOD &amp; PUBLIC DISTRIBUTION

(SHRI PRALHAD JOSHI)

(a) to (c): A statement is laid on the Table of the House.

## GOVERNMENT OF INDIA DEPARTMENT OF FOOD AND PUBLIC DISTRIBUTION

## LOK SABHA

STARRED QUESTION NO.326

## 326. SHRI SOMEONE:

Will the Minister of CONSUMER AFFAIRS be pleased to state:

- (a) some question?
"""
        q, a, method = split_question_answer(md)
        assert method == "heading_answer"
        assert q is not None
        assert a is not None
        assert "Will the Minister" in q
        assert "PRALHAD JOSHI" in a


class TestDoclingArtifactAnswer:
    """## \\2\\ ANSWER — Docling artifact with escaped chars."""

    def test_escaped_chars_before_answer(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF CORPORATE AFFAIRS

## 961. Shri Abhay Kumar Sinha:

Will the Minister of CORPORATE AFFAIRS be pleased to state:

- (a) some question?

## \\2\\ ANSWER

Minister of State in the Ministry of Corporate Affairs

(a): Response text.
"""
        q, a, method = split_question_answer(md)
        assert method == "heading_answer"
        assert "Will the Minister" in q
        assert "Minister of State" in a


class TestTableMinister:
    """MINISTER line inside a markdown table row."""

    def test_table_minister_boundary(self):
        md = """## GOVERNMENT OF INDIA

## LOK SABHA STARRED QUESTION NO. 238

| Will the Minister of COMMUNICATION be pleased to state: |
|----------------------------------------------------------|
| (a) some question? |
| (b) another question? |
| MINISTER OF COMMUNICATIONS (SHRI JYOTIRADITYA M. SCINDIA) |
| (a) to (b): Response text. |
"""
        q, a, method = split_question_answer(md)
        assert method == "table_minister"
        assert "pleased to state" in q
        assert "JYOTIRADITYA" in a


class TestMinisterOfStateForMinistry:
    """MINISTER OF STATE FOR MINISTRY OF (variant without ##)."""

    def test_minister_for_ministry(self):
        md = """## GOVERNMENT OF INDIA

## 5062. SHRI SOMEONE:

Will the Minister of CONSUMER AFFAIRS be pleased to state:

- (a) some question?

MINISTER OF STATE FOR MINISTRY OF CONSUMER AFFAIRS, FOOD & PUBLIC DISTRIBUTION

(a): Response text.
"""
        q, a, method = split_question_answer(md)
        assert method == "minister_boundary_bare"
        assert "Will the Minister" in q
        assert "CONSUMER AFFAIRS" in a


class TestUnsplit:
    """Fallback: No recognizable boundary."""

    def test_empty(self):
        q, a, method = split_question_answer("")
        assert method == "empty"
        assert q is None
        assert a is None

    def test_no_boundary(self):
        md = "Some random text without any answer marker."
        q, a, method = split_question_answer(md)
        assert method == "unsplit"
        assert q is not None
        assert a is None


class TestCleaning:
    """Verify header stripping, footer removal, HTML entity decoding."""

    def test_html_entities(self):
        md = """## GOVERNMENT OF INDIA

## 100. SHRI TEST:

Will the Minister of HEALTH &amp; FAMILY WELFARE be pleased to state:

- (a) test question?

## ANSWER

The response to part (a) is &ldquo;yes&rdquo;.
"""
        q, a, method = split_question_answer(md)
        assert "&amp;" not in q
        assert "HEALTH & FAMILY WELFARE" in q
        assert "\u201cyes\u201d" in a  # decoded left/right quotes

    def test_footer_stripped(self):
        md = """## 200. SHRI TEST:

Will the Minister be pleased to state:

- (a) test?

## ANSWER

The answer is yes.

*****
"""
        _, a, _ = split_question_answer(md)
        assert "*****" not in a

    def test_header_stripped_keeps_question(self):
        md = """## GOVERNMENT OF INDIA MINISTRY OF FINANCE

## LOK SABHA UNSTARRED QUESTION NO. 500 TO BE ANSWERED ON 01.01.2025

## TAX COLLECTION

## 500. DR. SOMEONE:

Will the Minister of FINANCE be pleased to state:

- (a) total tax collected?

## ANSWER

The answer.
"""
        q, _, _ = split_question_answer(md)
        assert "GOVERNMENT OF INDIA" not in q
        assert "LOK SABHA UNSTARRED" not in q
        # Question number and content should be kept
        assert "500." in q
        assert "Will the Minister" in q
