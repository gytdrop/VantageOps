# VantageOps Verification Scripts

Three `odoo-bin shell` scripts that assert the externalised business rules actually behave
as documented. **Every script rolls the transaction back**, so running them never mutates
`vantage_db`.

| Script | Asserts |
| :--- | :--- |
| `verify_versatility.py` | 40 checks across all four externalised rules: tier ceilings + category overrides, escalation thresholds + circuit-breaker precedence, cadence/proration math, and N-way depot allocation incl. the leg cap and shortfall reporting. |
| `verify_demo_flow.py` | Replays the documented turnkey walkthrough: seed → 3-way split ($265 across Main/West/East) → 18% Bronze discount → risk 13.0 → manager → finance → confirm → quarterly billing. |
| `verify_ui_paths.py` | Every touched view renders, settings round-trip through `ir.config_parameter`, and the bargain wizard / portal counter-offer / circuit-breaker reset / re-score actions all run. |

## Running them

```bash
python3 /home/gytdrop/odoo/odoo-bin shell -d vantage_db -r odoo --addons-path=/home/gytdrop/odoo/addons,custom_addons --no-http < verification/verify_versatility.py
```

Swap the filename for the other two. Run from the project root so the relative
`custom_addons` path in `--addons-path` resolves.

Filter the Odoo boot noise if you only want the assertions:

```bash
python3 /home/gytdrop/odoo/odoo-bin shell -d vantage_db -r odoo --addons-path=/home/gytdrop/odoo/addons,custom_addons --no-http < verification/verify_versatility.py 2>&1 | grep -E "PASS|FAIL|RESULT"
```

## The proration check worth knowing about

`verify_versatility.py` asserts that a 12-month quarterly contract starting mid-quarter on
a calendar-aligned anchor produces cycles whose proration factors sum to **exactly
4.000000** — i.e. `11/92 + 1 + 1 + 1 + 81/92`. That single assertion is what proves the
proration is genuinely calendar-exact rather than approximated, and that no revenue is
lost or double-billed at the contract boundaries.
