<p align="center">
  <img src="docs/assets/OpenSansad_Logo.png" alt="OpenSansad Logo" width="200">
</p>

<h1 align="center">OpenSansad — Lok Sabha Q&A Dataset</h1>

<p align="center">
  A structured dataset of Indian Lok Sabha parliamentary question-and-answer records for NLP research and transparency.
</p>

Part of the **OpenSansad** initiative — a personal project to make Sansad's (Indian Parliament's) workings more accessible and transparent through open data and open-source tooling. Data sourced from [Digital Sansad](https://sansad.in/).

## Setup

```bash
uv sync
```

## Build

```bash
# Build dataset from default data directory
uv run python -m lok_sabha_dataset.build

# Specify custom source directory
uv run python -m lok_sabha_dataset.build --source-dir /path/to/lok-sabha-rag/data

# Build specific sessions only
uv run python -m lok_sabha_dataset.build --lok 18 --sessions 6-7
```

Output is written to `output/lok_sabha_qa.parquet`.

## Configuration

Set `LOKSABHA_RAG_DATA_DIR` to point to your `lok-sabha-rag/data/` directory:

```bash
export LOKSABHA_RAG_DATA_DIR=/path/to/lok-sabha-rag/data
```

## Data Source

This dataset is built from data processed by the [lok-sabha-rag](https://github.com/sammitjain/lok-sabha-rag) project, which ingests parliamentary Q&A records from the Digital Sansad portal (sansad.in).
