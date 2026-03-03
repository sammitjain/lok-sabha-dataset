# Lok Sabha Q&A Dataset

Build and publish a HuggingFace dataset of Indian Lok Sabha parliamentary question-and-answer records. Data sourced from [Digital Sansad](https://sansad.in/).

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
