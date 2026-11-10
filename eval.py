"""Run a small, hand-selected expected-label smoke check; this is not an accuracy benchmark.
The report records whether this run's labels matched the script's expected-label rules.
Live requests use configured provider and Tavily quota."""
import sys, time, datetime
import requests

BASE = "http://127.0.0.1:8000"

CASES = [
    # (label, text, expect)
    ("Python version",   "Python 3.12 is the latest version of Python.", "stale"),
    ("Twitter CEO",      "The CEO of Twitter is Parag Agrawal.", "stale"),
    ("India: IPC",       "The Indian Penal Code (IPC) is the main criminal law of India.", "stale"),
    ("India: CrPC",      "The Code of Criminal Procedure (CrPC) governs criminal procedure in India.", "stale"),
    ("India: GST slabs", "India's GST has four main slabs: 5%, 12%, 18% and 28%.", "stale"),
    ("iPhone",           "The latest iPhone is the iPhone 14.", "stale"),
    ("ChatGPT model",    "ChatGPT runs on GPT-3.5.", "stale"),
    ("Node.js LTS",      "Node.js 18 is the current LTS release.", "stale"),
    ("Windows",          "Windows 10 is the latest version of Windows.", "stale"),
    ("Anthropic CEO",    "Anthropic's CEO is Dario Amodei.", "fresh"),
    ("Microsoft CEO",    "Satya Nadella is the CEO of Microsoft.", "fresh"),
    ("Timeless fact",    "The Eiffel Tower is in Paris, France.", "none"),
]


def verdicts(d):
    return [c["verdict"] for c in d["claims"]]


def matches_expected_label(expect, v):
    if expect in ("stale", "fresh"):
        return v == [expect]
    if expect == "none":
        return not v
    return False


def main():
    try:
        h = requests.get(BASE + "/health", timeout=10).json()
    except Exception:
        print("FreshCheck server nahi mila. Pehle: py -m uvicorn server:app --reload")
        sys.exit(1)
    if not h["gateway_ok"]:
        print("Configured LLM endpoint is not reachable at its configured URL.")
        sys.exit(1)

    rows, matched = [], 0
    print(f"{'Case':<18} {'Expected':<7} {'Got':<28} Match")
    print("-" * 66)
    for label, text, expect in CASES:
        try:
            r = requests.post(BASE + "/check", json={"text": text}, timeout=300)
            if r.status_code != 200:
                raise RuntimeError(r.json().get("detail", r.text)[:80])
            v = verdicts(r.json())
            good = matches_expected_label(expect, v)
            got = ",".join(v) or "(no claims)"
        except Exception as e:
            good, got = False, "ERROR " + str(e)[:40]
        matched += good
        rows.append((label, expect, got, good, text))
        print(f"{label:<18} {expect:<7} {got:<28} {'MATCH' if good else 'MISMATCH'}")
        time.sleep(0.5)

    print("-" * 66)
    print(f"Expected-label matches: {matched}/{len(CASES)} selected cases (not an accuracy estimate)")

    with open("eval_report.md", "w", encoding="utf-8") as f:
        f.write(f"# FreshCheck selected-case smoke run\n\nDate: {datetime.date.today()}  |  Provider: {h['gateway']}  |  Model: {h['model']}\n\n")
        f.write(f"**{matched}/{len(CASES)} rows matched the script’s expected-label checks in this run. This is not an accuracy estimate or benchmark.**\n\n")
        f.write("| Case | Expected | Got | Result |\n|---|---|---|---|\n")
        for label, expect, got, good, text in rows:
            f.write(f"| {label} | {expect} | {got} | {'MATCH' if good else 'MISMATCH'} |\n")
        f.write("\nThe hand-selected cases and expected labels are a narrow smoke check, not a representative sample. "
                "A match does not prove a claim true, current, or correctly interpreted.\n")
    print("Report saved: eval_report.md")
    print("Review any mismatches manually; this selected smoke run is not a benchmark.")


if __name__ == "__main__":
    main()
