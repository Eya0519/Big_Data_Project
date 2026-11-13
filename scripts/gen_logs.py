import csv, json, os, random
from datetime import datetime, timedelta

users = ["alice", "bob", "carol", "dave", "admin", "eya"]
ips = ["41.226.10.5", "41.226.10.9", "90.12.34.5", "81.2.69.142",
       "8.8.8.8", "92.63.197.1", "185.220.101.5"]
resources = ["/login", "/api/users", "/files/confidential.pdf", "db_prod", "/admin"]
services = ["auth-service", "web-app", "firewall", "database", "admin-console"]
types = ["authentication", "sensitive_access", "firewall", "audit", "intrusion_attempt"]
FIELDS = ["timestamp", "ip_source", "utilisateur", "type_evenement", "resultat",
          "niveau", "ressource", "service", "description"]


def event(ts, ip, user, typ, ok, level, res, svc):
    return {
        "timestamp": ts.isoformat(), "ip_source": ip, "utilisateur": user,
        "type_evenement": typ, "resultat": "succes" if ok else "echec",
        "niveau": level, "ressource": res, "service": svc,
        "description": f"{typ} - {'succes' if ok else 'echec'} pour {user} sur {res}",
    }


start = datetime(2026, 11, 1)
events = []
for _ in range(1500):
    typ = random.choice(types)
    ok = random.random() < 0.7 and typ != "intrusion_attempt"
    level = "faible" if ok else ("eleve" if typ == "intrusion_attempt" else random.choice(["moyen", "eleve"]))
    events.append(event(start + timedelta(minutes=random.randint(0, 20000)),
                        random.choice(ips), random.choice(users), typ, ok, level,
                        random.choice(resources), random.choice(services)))

# forced brute-force pattern: 8 failures from one IP in under 3 minutes
base = datetime(2026, 11, 10, 3, 0)
for i in range(8):
    events.append(event(base + timedelta(seconds=20 * i), "185.220.101.5", "admin",
                        "authentication", False, "eleve", "/login", "auth-service"))

events.sort(key=lambda e: e["timestamp"])
cut = int(len(events) * 0.7)          # 70% -> CSV, 30% -> JSON
os.makedirs("data/csv", exist_ok=True)
os.makedirs("data/json", exist_ok=True)

with open("data/csv/security_logs.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(events[:cut])

with open("data/json/security_logs.json", "w") as f:
    for e in events[cut:]:
        f.write(json.dumps(e) + "\n")

print(f"{cut} CSV rows, {len(events) - cut} JSON rows")
