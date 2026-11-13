# Plateforme de monitoring de sécurité et d'authentification (Stack ELK)

Mini-projet Big Data : Sécurité et Authentification.

Application de centralisation et d'analyse de logs de sécurité : les fichiers CSV et JSON sont ingérés par Logstash, indexés dans Elasticsearch et explorés avec Kibana. MongoDB, Redis et une application Flask complètent l'architecture.

> **État d'avancement : semaine 3 (environnement et ingestion).** L'infrastructure Docker, les pipelines d'ingestion et le mapping Elasticsearch sont en place. L'API Flask (import, recherche, alertes) sera développée à partir de la semaine 4.

## Architecture

| Service | Version | Rôle | Port |
|---|---|---|---|
| Elasticsearch | 8.19.23 | Stockage et recherche des événements | 9200 |
| Logstash | 8.19.23 | Lecture, transformation et enrichissement des logs | 9600 (interne) |
| Kibana | 8.19.23 | Exploration et visualisation | 5601 |
| MongoDB | 7 | Données applicatives (utilisateurs, métadonnées, règles) | 27017 |
| Redis | 7.2 | Sessions, cache, compteurs | 6379 |
| Application Flask | Python 3.11 | Backend / API REST | 8000 |

Flux de données :

```
data/csv/*.csv  ──► Logstash (pipeline csv)  ──┐
                                                ├─► Elasticsearch ──► Kibana
data/json/*.json ─► Logstash (pipeline json) ──┘
```

## Prérequis

- Docker 24 ou supérieur avec Docker Compose 2 (`docker compose version`)
- Python 3 (uniquement pour générer les données de test)
- Environ 4 Go de RAM disponibles et 5 Go d'espace disque
- **Linux :** Elasticsearch exige une limite de mappages mémoire plus élevée :

```bash
sudo sysctl -w vm.max_map_count=262144
# pour la rendre permanente :
echo "vm.max_map_count=262144" | sudo tee -a /etc/sysctl.conf
```

## Installation et démarrage

**1. Cloner le dépôt et créer le fichier d'environnement**

```bash
git clone https://github.com/Eya0519/Big_Data_Project.git
cd Big_Data_Project
cp .env.example .env
```

Éditer `.env` et remplacer `change_me` par de vrais mots de passe (lettres et chiffres uniquement, sans espaces ni guillemets).

**2. Générer les données de test**

```bash
python3 scripts/gen_logs.py
```

Le script crée `data/csv/security_logs.csv` et `data/json/security_logs.json` (environ 1 500 événements, dont un scénario de force brute).

**3. Démarrer l'infrastructure**

```bash
docker compose up -d elasticsearch kibana mongo redis
docker compose ps
```

Attendre que les quatre services soient `healthy` (1 à 2 minutes).

**4. Charger le template d'index Elasticsearch** (avant l'ingestion)

```bash
curl -X PUT localhost:9200/_index_template/security_logs \
  -H 'Content-Type: application/json' \
  -d @elasticsearch/security_logs_template.json
```

La réponse attendue est `{"acknowledged":true}`.

**5. Démarrer Logstash et l'application web**

```bash
docker compose up -d --build logstash webapp
```

**Temps de démarrage estimé :** environ 3 à 5 minutes une fois les images téléchargées. Le premier lancement prend plus de temps (environ 3 Go d'images à télécharger).

## Vérification du fonctionnement

```bash
# État des conteneurs
docker compose ps

# Application web et connexion aux trois bases
curl localhost:8000
curl localhost:8000/health

# Nombre d'événements indexés (environ 1508)
curl 'localhost:9200/security_logs*/_count?pretty'

# Erreurs d'analyse (index absent ou vide = aucune erreur)
curl 'localhost:9200/logs_parse_errors/_count?pretty'
```

`/health` doit renvoyer `"status":"healthy"` avec Elasticsearch, MongoDB et Redis à `"up"`.

**Kibana :** ouvrir http://localhost:5601, puis *Stack Management → Data Views → Create data view* avec le motif `security_logs*` et le champ de temps `@timestamp`. Dans *Discover*, choisir la période de novembre 2026.

## Accès

| Interface | URL |
|---|---|
| Application web | http://localhost:8000 |
| Kibana | http://localhost:5601 |
| Elasticsearch | http://localhost:9200 |

## Arrêt et réinitialisation

```bash
# Arrêter les services (les données sont conservées)
docker compose down

# Tout supprimer, y compris les données (réinitialisation complète)
docker compose down -v
```

## Structure du projet

```
.
├── docker-compose.yml
├── .env.example                      # modèle de configuration (sans secrets)
├── data/
│   ├── csv/                          # fichiers CSV surveillés par Logstash
│   └── json/                         # fichiers JSON surveillés par Logstash
├── elasticsearch/
│   └── security_logs_template.json   # mapping des index security_logs*
├── logstash/
│   ├── config/pipelines.yml          # déclaration des deux pipelines
│   └── pipeline/
│       ├── csv.conf
│       └── json.conf
├── scripts/
│   └── gen_logs.py                   # génération des données de test
└── webapp/
    ├── Dockerfile
    ├── requirements.txt
    └── app.py                        # application Flask (Hello World + /health)
```

## Modèle de données Elasticsearch

| Champ | Type | Description |
|---|---|---|
| `@timestamp`, `timestamp` | date | Date et heure de l'événement |
| `ip_source` | ip | Adresse IP à l'origine de l'action |
| `utilisateur` | keyword | Utilisateur concerné |
| `type_evenement` | keyword | Type d'action enregistrée |
| `resultat` | keyword | Succès ou échec |
| `niveau` | keyword | Gravité : faible, moyen, élevé |
| `ressource`, `service` | keyword | Ressource et service concernés |
| `description` | text | Message descriptif |
| `geoip.*` | keyword / geo_point | Pays et coordonnées déduits de l'IP |

Les événements valides sont indexés dans `security_logs-AAAA.MM` (un index par mois). Les lignes qui ne peuvent pas être analysées sont redirigées vers `logs_parse_errors`.

## Notes de développement

- La sécurité native d'Elasticsearch (xpack) est **désactivée** pour simplifier l'environnement de développement. Elle devra être activée avant toute mise en production.
- Logstash relit les fichiers depuis le début à chaque démarrage (`sincedb_path => "/dev/null"`), ce qui peut créer des doublons après un redémarrage. Un mécanisme de déduplication est prévu avec le développement du backend.
- Le fichier `.env` contient les secrets et n'est jamais versionné. Seul `.env.example` est dans le dépôt.

## Feuille de route

| Semaine | Contenu | État |
|---|---|---|
| 1 | Analyse : cahier des charges | Terminé |
| 2 | Conception : architecture, modèle de données, maquettes | Terminé |
| 3 | Environnement Docker, pipelines Logstash, index Elasticsearch | Terminé |
| 4 | Backend Flask : import, validation, recherche, MongoDB, Redis | À venir |
| 5 | Interface web, dashboard, alertes | À venir |
| 6 | Détection ML, tests, CI/CD, documentation | À venir |

## Auteur

Eya Guizani, IT Business School.
