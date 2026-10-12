# Contributing

AIAD is an early draft (v0.1). The most useful contributions right now:

1. **Break the spec.** Find a way to game it: inflate ratings, hide a paid placement, smuggle instructions to an AI past the validator. Open an issue describing the attack.
2. **Category vocabularies.** Propose spec keys, units and standard test protocols for a product category you know well (`vocab/categories.json`).
3. **Real-world files.** If you run a shop, try writing an `ai-ads.json` for one product and tell us which fields were hard to fill honestly.
4. **Agent behaviour.** If you build AI assistants, tell us which of the [Agent Rules](AGENT_RULES.md) are impractical and why.

## Before opening a pull request

```bash
pip install -r requirements.txt
python -m pytest tests -q
python tools/aiad_validate.py examples/*.json examples/*/*.json
```

- Every example must pass the validator with no errors.
- Example data about real products must come from the manufacturer's own pages, with the URL in `evidence_url`. Never invent reviews, ratings or test results.
- Template files are published by `aiad-templates.example` and say "unofficial". Do not publish files that look like they come from a brand.

## Language

The spec, code and messages are in English. Translations go under `docs/<language>/`.

## License

By contributing, you agree that your contributions are licensed under the [Apache License 2.0](LICENSE).
