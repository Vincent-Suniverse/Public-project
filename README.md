# UVB-76 Transmission Database

Public database of documented UVB-76 ("The Buzzer") voice transmissions on 4625 kHz.

## Live Database

Browse and search all transmissions at the GitHub Pages site:

**[vincent-suniverse.github.io/public-project](https://vincent-suniverse.github.io/public-project/)**

## Data

The `data/` directory contains the raw register files:

| File | Contents | Transmissions |
|------|----------|---------------|
| `UVB76_MASTER_REGISTER_V4.md` | Complete register 2020-2026 with analysis | ~1230 |
| `UVB76_NACHTRAG_28MAI_11JUNI_2026.md` | Supplement: 28 May - 11 June 2026 | 9 |
| `UVB76_22_24_JUNI_2026.md` | 22 + 24 June 2026 transmissions | 12 |

### Transmission Format

Each transmission follows this structure:

```
DATE TIME CALLSIGN COMMAND_BLOCK CODEWORD TARGET_BLOCK_1 TARGET_BLOCK_2
```

Example:
```
29.9. 10:31 НЖТИ 55849 ВОЗМЕЩЕНИЕ 8597 7049
```

- **Date/Time**: Moscow time (MSK)
- **Callsign**: Usually НЖТИ (NZhTI), sometimes ЦЖАП, ТОД3, У352, ДХГЕ, or combinations
- **Command Block**: 5-digit numeric group
- **Codeword**: Russian word (real or neologism)
- **Target Blocks**: Two 4-digit numeric groups

Multi-word transmissions (DOPPEL, TRIPLE, QUADRUPEL) carry multiple codeword+block pairs in a single message.

### Sources

- **2020-2024**: Priyom.org public archive
- **Sept 2025 - June 2026**: Vincent Weber's Telegram channel @uvb76logs

## Building the Site

The website is generated from the data files:

```bash
python scripts/parse_registers.py
```

This parses all markdown registers in `data/` and produces `docs/transmissions.json`, which the HTML frontend loads.

## Radio Monitor Pipeline

The `radio_monitor/` package is a separate ADS-B monitoring pipeline (OpenSky API -> SQLite). See the module docstrings for details.

```bash
pip install -e ".[dev]"
python -m radio_monitor.cli run --once
pytest
```

## License

MIT
