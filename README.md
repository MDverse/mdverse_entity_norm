# mdverse_entity_norm

## Setup environment

We use [uv](https://docs.astral.sh/uv/getting-started/installation/)
to manage dependencies and the project environment.

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

### Normalize temperature

To normalize temperature entities, run :

```sh
uv run src/mdverse_entity_norm/scripts/normalize_temperature.py
```
> This command generates...

### Ground molecules

To ground molecules entities, run :

```sh
uv run src/mdverse_entity_norm/scripts/ground_molecule.py
```
> This command generates...
