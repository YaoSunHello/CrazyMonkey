import sys
import traceback
import kit


def log(*args):
    print(*args, flush=True)


log("=== START INSPECTION ===")

try:
    tables = kit.tables()
    log("kit.tables():", tables)
except Exception as e:
    log("Error kit.tables():", e)
    tables = []

try:
    q = kit.questions()
    log("kit.questions():", q)
except Exception as e:
    log("Error kit.questions():", e)

# Check all available tables
for t_name in tables:
    try:
        t_val = kit.table(t_name)
        log(f"\nTable '{t_name}': type={type(t_val)}")
        sample = list(t_val)
        log(f"  total items={len(sample)}")
        if sample:
            log(f"  sample item keys={list(sample[0].keys()) if isinstance(sample[0], dict) else type(sample[0])}")
            if isinstance(sample[0], dict):
                if "Trans Type" in sample[0]:
                    log("  COA items:")
                    for item in sample:
                        log("   ", item)
                elif len(sample) <= 50:
                    for item in sample:
                        log("   ", item)
                else:
                    log(f"  First 5 items: {sample[:5]}")
    except Exception as e:
        log(f"Error accessing table '{t_name}':", e)
        traceback.print_exc(file=sys.stdout)

# Inspect rows
try:
    rows = kit.rows()
    log(f"\n=== ROWS ({len(rows)}) ===")
    for i, r in enumerate(rows):
        log(
            f"[{i}] narr={r.get('narrative')!r} dr={r.get('debit')} cr={r.get('credit')} ccy={r.get('currency')} "
            f"acct={r.get('account_number')} class={r.get('classification')} cp={r.get('counterparty_match')}"
        )
except Exception as e:
    log("Error kit.rows():", e)
    traceback.print_exc(file=sys.stdout)

log("=== END INSPECTION ===")
assert False, "Inspection done"