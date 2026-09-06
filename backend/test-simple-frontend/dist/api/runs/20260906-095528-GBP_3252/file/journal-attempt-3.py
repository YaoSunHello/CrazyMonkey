import kit

# Print questions and COA trans types at the very end so they are visible in stdout
q = kit.questions()
coa = list(kit.table("coa"))
coa_trans_types = [
    r.get("Trans Type")
    for r in coa
    if isinstance(r, dict) and "Trans Type" in r
]

rows = kit.rows()

print(f"QUESTIONS: {q}")
print(f"COA COUNT: {len(coa_trans_types)}")
print(f"COA TRANS TYPES: {coa_trans_types}")
print("--- ROWS SUMMARY ---")
for i, r in enumerate(rows):
    print(
        f"{i}: dr={r.get('debit')} cr={r.get('credit')} ccy={r.get('currency')} "
        f"cls={r.get('classification')} cp_st={r.get('counterparty_match', {}).get('status')} "
        f"cp_name={r.get('counterparty_match', {}).get('matched_name')!r} narr={r.get('narrative')!r}"
    )

assert False, "Inspection print"