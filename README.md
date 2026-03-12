# AutoCustomizeResume

Customize your LaTeX resume and cover letter for every job application, automatically. Paste a job description, get a tailored and optimized one-page resume and matching cover letter as compiled PDFs.

[![CI](https://github.com/avishj/AutoCustomizeResume/actions/workflows/ci.yml/badge.svg)](https://github.com/avishj/AutoCustomizeResume/actions/workflows/ci.yml)
[![CodeQL](https://github.com/avishj/AutoCustomizeResume/actions/workflows/codeql.yml/badge.svg)](https://github.com/avishj/AutoCustomizeResume/actions/workflows/codeql.yml)
[![codecov](https://codecov.io/gh/avishj/AutoCustomizeResume/branch/main/graph/badge.svg)](https://codecov.io/gh/avishj/AutoCustomizeResume)
[![License](https://img.shields.io/github/license/avishj/AutoCustomizeResume)](LICENSE)
[![Python](https://img.shields.io/badge/python-%3E%3D3.13-blue)](./pyproject.toml)
[![Stars](https://img.shields.io/github/stars/avishj/AutoCustomizeResume)](https://github.com/avishj/AutoCustomizeResume/stargazers)
[![Last commit](https://img.shields.io/github/last-commit/avishj/AutoCustomizeResume)](https://github.com/avishj/AutoCustomizeResume/commits/main)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/avishj/AutoCustomizeResume/badge)](https://scorecard.dev/viewer/?uri=github.com/avishj/AutoCustomizeResume)
[![Docker](https://img.shields.io/docker/v/avishj/autocustomizeresume?label=docker)](https://hub.docker.com/r/avishj/autocustomizeresume)

## What it does

You write one master resume in LaTeX with all your experience, projects, and skills. The tool reads a job description and uses an LLM to tailor your resume at every level:

- **Sections** (Education, Experience, Projects, Research) are included or excluded based on relevance.
- **Items** (individual jobs, projects, publications) are selected or dropped per role.
- **Bullets** within each item are individually included or excluded, with minor keyword edits to match the JD language.
- **Skills** are reordered by relevance, with new skills added and irrelevant ones removed per category.
- **Cover letter** is generated from scratch using your selected resume content and the JD.
- **One-page enforcement** automatically drops the lowest-scored optional content and recompiles until it fits.

The output is a compiled PDF ready to submit. Every run is archived with timestamps so you never lose a previous version.

## Quick start

```bash
git clone https://github.com/avishj/AutoCustomizeResume.git
cd AutoCustomizeResume
uv sync
```

Then follow the setup instructions in [`examples/`](./examples/) to configure your resume, API key, and config file.

## Prerequisites

- **Python 3.10+**
- **[uv](https://docs.astral.sh/uv/)** (recommended)
- **[Tectonic](https://tectonic-typesetting.github.io)** on PATH
  - macOS: `brew install tectonic`
  - Linux: [install guide](https://tectonic-typesetting.github.io/en-US/install.html)
  - Cargo: `cargo install tectonic`
- **LLM API key** for any OpenAI-compatible provider (or local Ollama)

## Tagging your resume

You mark sections, items, and bullets with LaTeX comment tags so the tool knows what it can include or exclude.

```latex
%%% BEGIN:pinned:education        ← always included
\section{Education}
    %%% BEGIN:optional:state-u     ← LLM decides per section, per item, per bullet, and then can edit bullet too!
    \resumeSubheading{State University}{...}
    %%% END:optional:state-u
%%% END:pinned:education

%%% SKILLS:languages               ← LLM can reorder, add, remove
\textbf{Languages}{: Python, Go, Rust, SQL}
%%% END:SKILLS:languages
```

Full specification: [docs/TAGS.md](./docs/TAGS.md)

## Configuration

Start from [`examples/config.example.yaml`](./examples/config.example.yaml) and copy it to `config.yaml`.

| Section | Key | Description |
|---------|-----|-------------|
| `user` | `first_name`, `last_name` | Used for output file naming and cover letter header |
| `user` | `phone`, `email`, `linkedin`, `website`, `degree`, `university` | Cover letter header fields |
| `naming` | `output_resume`, `output_cover` | Naming templates for `output/` (overwritten each run) |
| `naming` | `history_resume`, `history_cover` | Naming templates for `history/` (timestamped archive) |
| `llm` | `base_url`, `model` | LLM endpoint and model name |
| `llm` | `api_key_env` | Name of the environment variable holding your API key |
| `cover_letter` | `enabled` | `true` or `false` |
| `cover_letter` | `template`, `style`, `signature_path` | Template path, style prompt, optional signature image |
| `paths` | `master_resume`, `jd_file` | Input file paths |
| `paths` | `output_dir`, `history_dir` | Output directories |
| `watcher` | `debounce_seconds` | Seconds to wait after last file change before triggering |

**Naming template variables:** `{first}`, `{last}`, `{company}`, `{role}`, `{date}`, `{timestamp}`

## Usage

### One-shot mode

Process a single job description and exit.

```bash
uv run autocustomizeresume --jd path/to/jd.txt
```

### Watch mode (default)

Monitors `jd.txt` (configurable via `paths.jd_file`) and rebuilds on every save.

```bash
uv run autocustomizeresume
```

Press `Ctrl+C` to stop.

### CLI flags

| Flag | Description |
|------|-------------|
| `--jd PATH` | Path to JD file (triggers one-shot mode) |
| `--company NAME` | Override LLM-extracted company name |
| `--role TITLE` | Override LLM-extracted role title |

```bash
uv run autocustomizeresume --jd jd.txt --company "Acme Corp" --role "Backend Engineer"
```

## Supported LLM providers

Any OpenAI-compatible API works. Set `llm.base_url` and `llm.model` in `config.yaml`, and put the API key in `.env`.

| Provider | `base_url` | Notes |
|----------|-----------|-------|
| NVIDIA NIM | `https://integrate.api.nvidia.com/v1` | Free tier available |
| OpenAI | `https://api.openai.com/v1` | |
| Groq | `https://api.groq.com/openai/v1` | Fast inference |
| Together | `https://api.together.xyz/v1` | |
| Ollama | `http://localhost:11434/v1` | Local, no API key needed |

## Troubleshooting

**"tectonic is not installed or not on PATH"**
Install Tectonic and make sure it is accessible from your terminal. See [Prerequisites](#prerequisites).

**"API key not found"**
Set the environment variable named by `llm.api_key_env` (default: `LLM_API_KEY`) in your `.env` file or shell.

**"Config file not found"**
Copy `examples/config.example.yaml` to `config.yaml` in the project root.

**Resume exceeds one page after all retries**
The tool auto-drops lowest-scored optional items, but if your pinned content alone exceeds one page, reduce content or adjust template spacing. You can also convert some `pinned` tags to `optional` to give the tool more flexibility.

**Watch mode not triggering**
Check that you are editing the file at `paths.jd_file` (default: `jd.txt`). The watcher debounces changes by `watcher.debounce_seconds` before running.

## Development

### Prerequisites

- [uv](https://docs.astral.sh/uv/)
- [just](https://github.com/casey/just)
- [Tectonic](https://tectonic-typesetting.github.io) on PATH

### Setup

```bash
git clone https://github.com/avishj/AutoCustomizeResume.git
cd AutoCustomizeResume
uv sync
pre-commit install
```

### Common tasks

```bash
just lint        # lint and format check
just typecheck   # run type checker
just test        # run tests
just cov         # run tests with coverage
just ci          # run all quality gates
just docs        # serve docs locally
just clean       # remove build artifacts
```

## Documentation

[https://avishj.github.io/AutoCustomizeResume](https://avishj.github.io/AutoCustomizeResume)

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md).

## License

[GNU Affero General Public License v3.0 (AGPL-3.0)](./LICENSE)

## Star History

[![Star History Chart](https://api.star-history.com/svg?repos=avishj/AutoCustomizeResume&type=Date)](https://star-history.com/#avishj/AutoCustomizeResume&Date)
