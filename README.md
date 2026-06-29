# mdverse_entity_norm

## Setup environment

We use [uv](https://docs.astral.sh/uv/getting-started/installation/) to manage dependencies and the project environment.

Clone the GitHub repository:

```sh
git clone https://github.com/MDverse/mdverse_entity_norm.git
cd mdverse_entity_norm
```

Sync dependencies:

```sh
uv sync
```

## Usage

This project implements the normalisation pipeline for molecular dynamics simulation metadata entities. Normalisation is currently supported for four entity types: temperature, small molecules, simulation times, and software versions (not yet implemented). The scripts are located in `src/mdverse_entity_norm/scripts/` and can be executed independently. Output files are saved in the `results/` directory, which is created automatically if it does not exist.

### Normalize temperature

```sh
uv run src/mdverse_entity_norm/scripts/normalize_temperature.py
```

This reads temperature entities from `data/entities.tsv` and writes `results/norm_temp.tsv`, a TSV file with four columns:

| Column | Description |
|---|---|
| `raw_temperature` | Original temperature string |
| `normalised_temperature` | Numeric value after normalisation |
| `normalised_unit` | Unit after normalisation (Kelvin) |
| `normalized_result` | Concatenated value and unit |

Special cases `room temperature` and `human body temperature` are normalised to 293 K and 310 K respectively. All Celsius values are converted to Kelvin.

### Ground molecules

The grounding logic is illustrated below:

![Grounding logic](molecules_grounding_logic.png)

```sh
uv run src/mdverse_entity_norm/scripts/normalize_molecules.py
```

This reads molecular entities from `data/entities.tsv`. Entities are first classified by type (PDB, UniProt, DNA, RNA, protein, or small molecule). PDB and UniProt entries are resolved via their respective APIs and saved to `results/ground_molecule/same_grounding_mol/pdb_uniprot_seq_entities.tsv`. Small molecules are grounded by consensus across ChEBI, PubChem, and KEGG, producing two output files:

**`chebi_comparaison.tsv`** — ChEBI grounding results for all small molecules:

| Column | Description |
|---|---|
| `Molecule` | Original molecule name |
| `CHEBI_ID` | ID returned directly by ChEBI |
| `CHEBI_ID_from_KEGG` | ChEBI ID resolved via KEGG |
| `CHEBI_ID_from_PubChem` | ChEBI ID resolved via PubChem synonyms |
| `Match` | `True` if at least two sources agree |

**`pubchem_comparaison_no_chebi_match.tsv`** — PubChem fallback for molecules with no ChEBI consensus:

| Column | Description |
|---|---|
| `Molecule` | Original molecule name |
| `PubChem_ID` | ID returned directly by PubChem |
| `PubChem_ID_from_KEGG` | PubChem ID resolved via KEGG |
| `Match` | `True` if both sources agree |

### Normalize simulation times

Two scripts are involved: one evaluates candidate LLM models on a labelled gold standard, the other applies the selected model to the full dataset.

**Model evaluation:**

```sh
uv run src/mdverse_entity_norm/scripts/normalize_simulation_time.py \
  --ground_truth_file data/STIME_ground_truth.json \
  --runs 10 \
  --model_evaluation_file results/norm_simu_times/model_evaluation.tsv
```

This benchmarks 9 models via OpenRouter (including GPT-4o, DeepSeek V4 Pro, Claude Opus 4.7, and others) on a manually annotated gold standard of 100 simulation time entities, repeated over the specified number of runs. Results are saved to the file specified by `--model_evaluation_file`:

| Column | Description |
|---|---|
| `model_name` | Model identifier |
| `accuracy_percentage` | Average accuracy across runs (%) |
| `normalisation_times_sec` | Average processing time per entity (s) |
| `normalisation_cost` | Average cost per entity (USD) |

> An `OPEN_ROUTER_KEY` environment variable must be set (e.g. via a `.env` file) for API access.

**Entity normalisation:**

```sh
uv run src/mdverse_entity_norm/scripts/normalize_stime_results.py \
  --entities-file data/entities.tsv \
  --output-file results/norm_simu_times/normalized_stime_results.tsv
```

This applies DeepSeek V4 Pro to all STIME entities in the input file and writes a TSV with three columns:

| Column | Description |
|---|---|
| `STIME` | Original simulation time string |
| `LLM_value` | Normalised numeric value |
| `LLM_unit` | Normalised unit (`ps`, `ns`, `μs`, `ms`, or `s`) |
