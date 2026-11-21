# Plateforme de monitoring de sécurité et d'authentification (Stack ELK)

Mini-projet Big Data, **Scénario C : Sécurité et Authentification**.

Application de centralisation et d'analyse de logs de sécurité : les fichiers CSV et JSON sont validés par une API Flask, ingérés par Logstash, indexés dans Elasticsearch et explorés avec Kibana. MongoDB conserve les métadonnées des imports et l'historique des recherches, Redis met en cache les recherches et les statistiques.

> **État d'avancement :** l'infrastructure Docker, l'ingestion et le backend principal (import, recherche, API REST, documentation Swagger, tests) sont en place. L'interface web, les alertes et les dashboards Kibana sont à venir.

## Architecture

| Service | Version | Rôle | Port |
|---|---|---|---|
| Elasticsearch | 8.19.23 | Stockage et recherche des événements | 9200 |
| Logstash | 8.19.23 | Lecture, transformation et enrichissement des logs | 9600 (interne) |
| Kibana | 8.19.23 | Exploration et visualisation | 5601 |
| MongoDB | 7 | Métadonnées des imports, historique des recherches | 27017 |
| Redis | 7.2 | Cache des recherches et des statistiques | 6379 |
| Application Flask | Python 3.11 | Backend / API REST | 8000 |

Flux de données :

```
POST /upload ──► validation ──► data/csv ou data/json ──► Logstash ──► Elasticsearch ──► Kibana
                     │                                                       ▲
                     └──► MongoDB (métadonnées, statut)                      │
GET /search, /api/v1/logs, /api/v1/stats ──► Redis (cache) ──────────────────┘
```

## Prérequis

- Docker 24 ou supérieur avec Docker Compose 2 (`docker compose version`)
- Python 3 avec le module `venv` (génération des données de test et tests)
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

**2. Générer les données de test avec Faker**

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r scripts/requirements.txt
python scripts/gen_logs.py --format csv  --count 1000 --output data/csv/security_logs.csv
python scripts/gen_logs.py --format json --count 500  --output data/json/security_logs.json
```

Les événements couvrent les cinq catégories du scénario (authentification, intrusion, accès sensibles, pare-feu, audit) et incluent deux scénarios de force brute. L'option `--seed` rend un fichier reproductible et `--help` liste toutes les options.

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
docker compose up -d --build
```

**Temps de démarrage estimé :** environ 3 à 5 minutes une fois les images téléchargées. Le premier lancement est plus long (environ 3 Go d'images).

> Démarrer le projet avec `docker compose up -d` sans nom de service : sinon Logstash ou Kibana peuvent rester arrêtés et les fichiers importés ne seront pas indexés.

## Vérification du fonctionnement

```bash
docker compose ps
curl localhost:8000/health
curl 'localhost:9200/security_logs*/_count?pretty'
curl 'localhost:9200/logs_parse_errors/_count?pretty'    # index absent ou vide = aucune erreur d'analyse
```

`/health` doit renvoyer `"status":"healthy"` avec Elasticsearch, MongoDB et Redis à `"up"`.

**Kibana :** ouvrir http://localhost:5601, puis *Stack Management → Data Views → Create data view* avec le motif `security_logs*` et le champ de temps `@timestamp`.

## Accès

| Interface | URL |
|---|---|
| Documentation interactive de l'API (Swagger) | http://localhost:8000/apidocs |
| Spécification OpenAPI | http://localhost:8000/openapi.yaml |
| Application web | http://localhost:8000 |
| Kibana | http://localhost:5601 |
| Elasticsearch | http://localhost:9200 |

## API REST

La documentation complète, avec un bouton « Try it out » pour chaque route, est disponible sur `/apidocs`. La spécification `openapi.yaml` peut aussi être importée dans Postman.

| Méthode | Route | Description |
|---|---|---|
| GET | `/health` | État et latence d'Elasticsearch, MongoDB et Redis |
| POST | `/upload` | Importer un fichier CSV ou JSON (champ `file`) |
| GET | `/api/v1/files` | Historique des 50 derniers imports et leur statut |
| GET | `/api/v1/files/{id}` | Détail et statut d'un import |
| GET | `/search` | Recherche avec filtres, tri et pagination (enregistrée dans l'historique) |
| GET | `/api/v1/searches` | Les 20 dernières recherches enregistrées |
| GET | `/api/v1/logs` | Liste paginée des événements (mêmes filtres que `/search`) |
| GET | `/api/v1/logs/{id}` | Détail complet d'un événement |
| GET | `/api/v1/stats` | Statistiques globales pour le tableau de bord |

### Import de fichiers

```bash
curl -F "file=@mon_fichier.csv" localhost:8000/upload
```

- Formats acceptés : `.csv` (en-tête de 9 colonnes exact) et `.json` au format **NDJSON** (un objet par ligne). Taille maximale : 100 Mo.
- Le contenu est validé (colonnes, horodatages ISO 8601, adresses IP) ; les erreurs sont renvoyées avec leur numéro de ligne.
- Un fichier valide est déposé de façon atomique dans le dossier surveillé par Logstash. Son statut évolue ainsi : `pending`, `processing`, puis `indexed`, `partial` (certaines lignes en erreur d'analyse) ou `failed`. Suivre le statut avec `GET /api/v1/files/{id}`.

| Code | Signification |
|---|---|
| 201 | Fichier accepté, ingestion en cours |
| 400 | Aucun fichier reçu |
| 413 | Fichier trop volumineux |
| 415 | Extension non supportée |
| 422 | Contenu invalide (détail des erreurs par ligne) |
| 503 | Base de données indisponible |

### Recherche

Paramètres de `/search` et de `/api/v1/logs` :

| Paramètre | Description |
|---|---|
| `q` | Texte libre (description, utilisateur, ressource, service, type) |
| `ip` | Adresse IP ou plage CIDR (`41.226.10.0/24`) |
| `user`, `type`, `result`, `level`, `service` | Filtres exacts |
| `from`, `to` | Période (`2026-11-01` ou ISO 8601 ; une date seule pour `to` inclut toute la journée) |
| `page`, `size` | Pagination (50 par page par défaut, 100 au maximum) |
| `sort`, `order` | Tri : `timestamp` (défaut), `ip`, `user`, `type`, `result`, `level`, `service` ; `asc` ou `desc` |

```bash
curl 'localhost:8000/search?ip=185.220.101.5&result=echec&from=2026-11-01&size=10'
```

Les résultats sont mis en cache dans Redis pendant 60 secondes (champ `cached` dans la réponse). Seuls les 10 000 premiers résultats sont accessibles par pagination.

## Tests

Les tests utilisent `pytest`. Les tests unitaires n'ont pas besoin de Docker ; les tests d'intégration appellent l'API en cours d'exécution.

```bash
. .venv/bin/activate
pip install -r requirements-dev.txt

pytest -v -m "not integration"     # tests unitaires : validation des fichiers et paramètres de recherche
pytest -v -m integration           # tests d'intégration : nécessite docker compose up -d
```

Le test d'intégration principal importe un fichier, attend son indexation, retrouve ses événements par une recherche, lit un événement en détail, puis supprime ses événements de test.

## Configuration

Les identifiants sont lus dans le fichier `.env` (jamais versionné ; `.env.example` sert de modèle) :

| Variable | Description |
|---|---|
| `MONGO_USER`, `MONGO_PASSWORD` | Compte administrateur MongoDB |
| `REDIS_PASSWORD` | Mot de passe Redis |

Variables optionnelles de l'application (valeurs par défaut) :

| Variable | Défaut | Description |
|---|---|---|
| `MAX_UPLOAD_MB` | 100 | Taille maximale d'un import |
| `SEARCH_CACHE_TTL` | 60 | Durée du cache de recherche (secondes) |
| `UPLOAD_DIR` | `/data` | Dossier de dépôt des fichiers importés |
| `MONGO_DB` | `security_monitor` | Nom de la base MongoDB |

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
├── pytest.ini, requirements-dev.txt
├── data/
│   ├── csv/                          # fichiers CSV surveillés par Logstash
│   └── json/                         # fichiers JSON surveillés par Logstash
├── elasticsearch/
│   └── security_logs_template.json   # mapping des index security_logs*
├── logstash/
│   ├── config/pipelines.yml          # déclaration des deux pipelines
│   └── pipeline/                     # csv.conf et json.conf
├── scripts/
│   ├── gen_logs.py                   # génération des données de test (Faker)
│   └── requirements.txt
├── tests/
│   ├── test_validation.py            # tests unitaires de la validation
│   ├── test_search_params.py         # tests unitaires de la recherche
│   ├── test_integration.py           # tests d'intégration de l'API
│   └── samples/                      # fichiers d'exemple valides et invalides
└── webapp/
    ├── Dockerfile, requirements.txt, app.py
    └── backend/
        ├── config.py, extensions.py  # configuration et connexions aux services
        ├── openapi.yaml              # spécification de l'API
        ├── routes/                   # health, upload, search, api, docs
        └── services/                 # validation, ingestion, search, logs, stats
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
| `source_file` | keyword | Fichier d'origine de l'événement |
| `geoip.*` | keyword / geo_point | Pays et coordonnées déduits de l'IP |

Les événements valides sont indexés dans `security_logs-AAAA.MM` (un index par mois). Les lignes qui ne peuvent pas être analysées sont redirigées vers `logs_parse_errors`.

## Notes et limites

- La sécurité native d'Elasticsearch (xpack) est **désactivée** pour simplifier l'environnement de développement. Elle devra être activée avant toute mise en production.
- Un fichier envoyé deux fois est indexé deux fois : il n'existe pas encore de détection des fichiers déjà importés.
- Le statut d'un import est calculé à la demande, lorsqu'on le consulte.
- Les résultats de recherche et les statistiques peuvent avoir jusqu'à 60 et 30 secondes de retard à cause du cache.
- Le tri par gravité est alphabétique (`eleve`, `faible`, `moyen`) et non par niveau de criticité.
- Les fichiers déposés par l'application appartiennent à l'utilisateur root sur la machine hôte, car ils sont créés depuis le conteneur.
- Le format JSON accepté est uniquement le NDJSON ; l'authentification, les alertes et l'interface web ne sont pas encore développées.

## Feuille de route

| Semaine | Contenu | État |
|---|---|---|
| 1 | Analyse : cahier des charges | Terminé |
| 2 | Conception : architecture, modèle de données, maquettes | Terminé |
| 3 | Environnement Docker, pipelines Logstash, index Elasticsearch | Terminé |
| 4 | Backend Flask : import, recherche, API REST, Swagger, tests | Terminé |
| 5 | Interface web, dashboard, Kibana, alertes | À venir |
| 6 | Détection ML, tests, CI/CD, documentation | À venir |

## Auteur

Eya Guizani, IT Business School.
