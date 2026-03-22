---
license: cc-by-4.0
language:
  - en
  - hi
pretty_name: "Lok Sabha Q&A — Indian Parliamentary Questions & Answers"
size_categories:
  - 10K<n<100K
task_categories:
  - question-answering
  - text-classification
  - summarization
tags:
  - parliament
  - india
  - lok-sabha
  - government
  - politics
  - transparency
  - opensansad
  - rag
dataset_info:
  features:
    - name: id
      dtype: string
    - name: lok_no
      dtype: int64
    - name: session_no
      dtype: int64
    - name: ques_no
      dtype: int64
    - name: type
      dtype: string
    - name: date
      dtype: string
    - name: subject
      dtype: string
    - name: ministry
      dtype: string
    - name: members
      sequence: string
    - name: full_text
      dtype: string
    - name: question_text
      dtype: string
    - name: answer_text
      dtype: string
    - name: question_word_count
      dtype: float64
    - name: answer_word_count
      dtype: float64
    - name: pdf_url
      dtype: string
    - name: pdf_url_hindi
      dtype: string
    - name: num_pages
      dtype: float64
  splits:
    - name: train
      num_examples: 115126
---

<p align="center">
  <img class="hidden dark:block" src="OpenSansad_Logo_dark.svg" alt="OpenSansad Logo" width="200">
  <img class="dark:hidden" src="OpenSansad_Logo_light.svg" alt="OpenSansad Logo" width="200">
</p>

<h1 align="center">OpenSansad — Lok Sabha Q&A Dataset</h1>

<p align="center">
  <em>Structured parliamentary question-and-answer records from India's Lok Sabha</em>
</p>

## Dataset Description

- **Repository:** [github.com/sammitjain/lok-sabha-dataset](https://github.com/sammitjain/lok-sabha-dataset)
- **Point of Contact:** Sammit Jain
- **License:** CC-BY-4.0

### Dataset Summary

This dataset contains **115,100+** parliamentary Q&A records from India's Lok Sabha (lower house of Parliament), covering:

- **18th Lok Sabha** — 27,723 questions across sessions 2–7 (Jul 2024 — Mar 2026), fully extracted with question/answer text
- **17th Lok Sabha** — 60,549 questions across sessions 1–12, 14–15 (Jun 2019 — Feb 2024), fully extracted with question/answer text
- **16th Lok Sabha** — 26,854 questions from sessions 12–17 (Feb 2018 — Feb 2019), fully extracted with question/answer text

Each record contains rich metadata including the responsible ministry, subject, date, MP names, and links to the original source PDFs on [Digital Sansad](https://sansad.in/). For records where text extraction is complete, the full question and official government answer are included.

This dataset is part of the [**OpenSansad**](https://github.com/sammitjain) initiative by Sammit Jain — a project to make the workings of Sansad (Indian Parliament) more accessible and transparent through open data and open-source tooling.

### Supported Tasks

- **Question Answering / RAG:** The question-answer pairs can be used directly for retrieval-augmented generation over Indian parliamentary proceedings. See the companion [lok-sabha-rag](https://github.com/sammitjain/lok-sabha-rag) project for a working RAG pipeline built on this data.
- **Text Classification:** Classify questions by ministry, topic, or question type (starred vs. unstarred).
- **Summarization:** Generate concise summaries of verbose government responses.
- **Information Extraction:** Extract structured data such as schemes, statistics, and policy details from answer text.
- **Multilingual NLP:** Some records contain Hindi text, useful for Hindi/English code-mixed NLP tasks.

### Languages

The dataset is primarily in **English** (`en`), with a subset of records in **Hindi** (`hi`). Some records contain a mix of both languages.

## Dataset Structure

### Data Instance

```json
{
  "id": "LS18-S2-STARRED-280",
  "lok_no": 18,
  "session_no": 2,
  "ques_no": 280,
  "type": "STARRED",
  "date": "2024-08-09",
  "subject": "Role of NGOs in Welfare of Women and Children",
  "ministry": "WOMEN AND CHILD DEVELOPMENT",
  "members": ["Shri Manish Jaiswal"],
  "full_text": "## GOVERNMENT OF INDIA ...",
  "question_text": "*280. SHRI MANISH JAISWAL :\n\nWill the Minister of WOMEN AND CHILD DEVELOPMENT be pleased to state ...",
  "answer_text": "## ANSWER\n\nMINISTER OF WOMEN AND CHILD DEVELOPMENT (SHRIMATI ANNPURNA DEVI)\n\n(a) to (e) : A Statement is laid ...",
  "question_word_count": 147,
  "answer_word_count": 855,
  "pdf_url": "https://sansad.in/getFile/loksabhaquestions/annex/182/AS280_6OmUWJ.pdf?source=pqals",
  "pdf_url_hindi": "https://sansad.in/getFile/loksabhaquestions/qhindi/182/AS280_6OmUWJ.pdf?source=pqals",
  "num_pages": 3
}
```

### Data Fields

| Field | Type | Description |
|-------|------|-------------|
| `id` | `string` | Unique identifier following the pattern `LS{lok_no}-S{session}-{type}-{ques_no}` |
| `lok_no` | `int` | Lok Sabha number (16, 17, or 18) |
| `session_no` | `int` | Parliamentary session number |
| `ques_no` | `int` | Question serial number within the session |
| `type` | `string` | `STARRED` (oral answer in Parliament) or `UNSTARRED` (written answer) |
| `date` | `string` | Date the question was answered, in `YYYY-MM-DD` format |
| `subject` | `string` | Subject or topic of the question |
| `ministry` | `string` | Government ministry responsible for answering |
| `members` | `list[string]` | Name(s) of the MP(s) who asked the question |
| `full_text` | `string` | Complete text extracted from the source PDF |
| `question_text` | `string` | The question portion, separated from the answer |
| `answer_text` | `string` | The government's answer portion (null for ~0.05% unsplit records) |
| `question_word_count` | `float` | Word count of the question text |
| `answer_word_count` | `float` | Word count of the answer text |
| `pdf_url` | `string` | URL to the original English PDF on Digital Sansad |
| `pdf_url_hindi` | `string` | URL to the Hindi PDF on Digital Sansad |
| `num_pages` | `float` | Number of pages in the source PDF |

### Data Splits

The dataset is provided as a single `train` split. Users can create custom splits by lok number, session, date, ministry, or question type as needed.

#### 18th Lok Sabha (2024–2026) — fully extracted

| Session | Period | Starred | Unstarred | Total |
|---------|--------|---------|-----------|-------|
| 2 | Jul — Aug 2024 | 280 | 3,219 | 3,499 |
| 3 | Nov — Dec 2024 | 380 | 4,369 | 4,749 |
| 4 | Feb — Mar 2025 | 500 | 5,750 | 6,250 |
| 5 | Jul — Aug 2025 | 419 | 4,829 | 5,248 |
| 6 | Nov — Dec 2025 | 280 | 3,219 | 3,499 |
| 7 | Jan — Mar 2026 | 358 | 4,120 | 4,478 |
| **Total** | | **2,217** | **25,506** | **27,723** |

#### 16th Lok Sabha (2014–2019) — extraction in progress

| Session | Period | Starred | Unstarred | Total | Text available |
|---------|--------|---------|-----------|-------|----------------|
| 12 | Feb — Mar 2018 | 377 | 4,358 | 4,735 | 4,735 extracted |
| 13 | Mar — Apr 2018 | 280 | 3,214 | 3,494 | 3,494 extracted |
| 14 | Feb — Apr 2018 | 579 | 6,668 | 7,247 | 7,244 extracted |
| 15 | Jul — Aug 2018 | 360 | 4,136 | 4,496 | 4,491 extracted |
| 16 | Dec — Jan 2019 | 393 | 4,498 | 4,891 | 4,888 extracted |
| 17 | Feb — Feb 2019 | 160 | 1,831 | 1,991 | 1,991 extracted |
| **Total** | | **2,149** | **24,705** | **26,854** | |

> **Note:** 16th Lok Sabha extraction is in progress. Remaining sessions will be added incrementally.

#### 17th Lok Sabha (2019–2024) — fully extracted

| Session | Period | Starred | Unstarred | Total | Text available |
|---------|--------|---------|-----------|-------|----------------|
| 1 | Jun — Aug 2019 | 500 | 5,698 | 6,198 | 6,188 extracted |
| 2 | Nov — Dec 2019 | 380 | 4,369 | 4,749 | 4,746 extracted |
| 3 | Jan — Mar 2020 | 419 | 4,818 | 5,237 | 5,237 extracted |
| 4 | Sep — Sep 2020 | 0 | 2,301 | 2,301 | 2,301 extracted |
| 5 | Jan — Mar 2021 | 440 | 5,057 | 5,497 | 5,493 extracted |
| 6 | Jul — Aug 2021 | 320 | 3,679 | 3,999 | 3,999 extracted |
| 7 | Nov — Dec 2021 | 339 | 3,909 | 4,248 | 4,248 extracted |
| 8 | Jan — Apr 2022 | 500 | 5,749 | 6,249 | 6,249 extracted |
| 9 | Jul — Aug 2022 | 319 | 3,672 | 3,991 | 3,991 extracted |
| 10 | Dec — Dec 2022 | 239 | 2,759 | 2,998 | 2,998 extracted |
| 11 | Jan — Apr 2023 | 480 | 5,520 | 6,000 | 6,000 extracted |
| 12 | Jul — Aug 2023 | 340 | 3,910 | 4,250 | 4,250 extracted |
| 14 | Dec — Dec 2023 | 267 | 3,066 | 3,333 | 3,331 extracted |
| 15 | Feb — Feb 2024 | 120 | 1,379 | 1,499 | 1,499 extracted |
| **Total** | | **4,663** | **55,886** | **60,549** | |

> **Note:** Session 13 does not exist in the official Digital Sansad records for the 17th Lok Sabha.

## Dataset Creation

### Curation Rationale

Indian parliamentary Q&A records are a rich source of information about government policy, public spending, and administrative decisions. However, this data is only available as individual PDF files on the Digital Sansad portal, making it difficult to search, analyze, or use programmatically. This dataset aims to make this information accessible in a structured, machine-readable format.

### Source Data

All data is sourced from [Digital Sansad](https://sansad.in/) (`sansad.in`), the official portal of the Indian Parliament. The source documents are publicly available PDF files containing parliamentary questions and their official government responses.

**Collection process:**
1. Question metadata (subject, ministry, members, dates) is scraped from the Digital Sansad search API
2. PDF documents are downloaded from official URLs
3. Text is extracted from PDFs using [Docling](https://github.com/DS4SD/docling)
4. Question and answer portions are separated using a multi-strategy regex-based splitter (15 strategies covering English, Hindi, and various OCR artifacts)

### Personal and Sensitive Information

This dataset contains only publicly available parliamentary records. The names of Members of Parliament and government ministers appear as part of the official record. No private or sensitive personal information is included.

## Considerations for Using the Data

### Known Limitations

- **OCR artifacts:** Text is extracted from PDFs, some of which have corrupted embedded text layers. This can result in garbled characters in a small number of records (~0.05% remain unsplit due to severe OCR issues).
- **Q/A separation:** The question-answer split is automated and may occasionally include header/footer text or split at imprecise boundaries.
- **Coverage:** Currently covers the 16th (2014–2019), 17th (2019–2024), and 18th (2024–2026) Lok Sabhas. The 17th and 18th are fully extracted (~88,200 records with text); the 16th Lok Sabha has sessions 12–17 extracted (~26,800 records), remaining sessions in progress.
- **Hindi records:** A small subset of records are in Hindi. The Q/A separation for Hindi text relies on Hindi-specific markers and may be less reliable than for English records.

### Future Improvements

- **Complete 16th Lok Sabha extraction:** Expand from sessions 12–17 to all sessions
- **Earlier Lok Sabhas:** Expand coverage to include 15th and older parliamentary data
- **OCR fallback:** Re-extract garbled PDFs using image-based OCR for the remaining unsplit records
- **Minister extraction:** Extract and normalize the answering minister's name as a structured field
- **Rajya Sabha:** Extend to India's upper house of Parliament
- **Enrichments:** Add MP party affiliation, constituency, and other metadata from external sources

## Usage

```python
from datasets import load_dataset

ds = load_dataset("opensansad/lok-sabha-qa")

# Filter by ministry
health = ds["train"].filter(lambda x: "HEALTH" in x["ministry"])

# Filter by session
session_4 = ds["train"].filter(lambda x: x["session_no"] == 4)

# Starred questions only (answered orally in Parliament)
starred = ds["train"].filter(lambda x: x["type"] == "STARRED")

# Search by subject keyword
education = ds["train"].filter(lambda x: "education" in x["subject"].lower())
```

### Use for RAG

This dataset pairs well with retrieval-augmented generation. See the companion [lok-sabha-rag](https://github.com/sammitjain/lok-sabha-rag) project for a complete RAG pipeline that uses this data to answer questions about Indian parliamentary proceedings.

## Additional Information

### Dataset Curators

This dataset is created and maintained by **Sammit Jain** as part of the [OpenSansad](https://github.com/sammitjain) initiative.

### Licensing

The dataset is released under **CC-BY-4.0**. The underlying parliamentary records are public documents of the Government of India.

### Citation

```bibtex
@dataset{opensansad_lok_sabha_qa,
  title   = {OpenSansad Lok Sabha Q&A Dataset},
  author  = {Sammit Jain},
  year    = {2026},
  url     = {https://huggingface.co/datasets/opensansad/lok-sabha-qa},
  license = {CC-BY-4.0},
}
```
