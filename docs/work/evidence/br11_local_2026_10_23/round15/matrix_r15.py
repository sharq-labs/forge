"""Round-15 consolidated finding matrix from the workflow journal (results + labels).

Usage: python matrix_r15.py <results.jsonl> <labels.txt>.  Prints one row per finding: id | lens | question | severity
| skeptic verdicts | critic mention | reproduction head, then the lens and critic Q1-Q7 verdicts."""
import json
import re
import sys

results, labels_path = sys.argv[1:3]
labels = dict(re.findall(r'"agentId":"([^"]+)","label":"([^"]+)"', open(labels_path, encoding="utf-8").read()))
rows = [json.loads(line) for line in open(results, encoding="utf-8")]
verdicts, findings, questions, critic = {}, [], {}, None
for r in rows:
    label, res = labels.get(r["agentId"], "?"), r["result"]
    if label.startswith("verify:"):
        _, fid, skeptic = label.split(":")
        verdicts.setdefault(fid, []).append(f"{skeptic}={'CONFIRMED' if res['confirmed'] else 'REFUTED'}/{res['severity']}")
    elif label.startswith("review:") or label == "critic":
        lens = label.split(":", 1)[1] if label != "critic" else "critic"
        questions[lens] = " ".join(f"{q['q'][:2]}={q['verdict']}" for q in res["questions"])
        for f in res["findings"]:
            findings.append((f, lens))
        if label == "critic":
            critic = res
critic_text = json.dumps(critic) if critic else ""
for f, lens in findings:
    mentioned = "critic-mentioned" if f["id"] in critic_text and lens != "critic" else ""
    print(f"{f['id']} | {lens} | {f['question']} | {f['severity']} | {'; '.join(verdicts.get(f['id'], ['-']))} | "
          f"{mentioned} | {f['title'][:150]}")
print()
for lens, q in questions.items():
    print(f"{lens}: {q}")
