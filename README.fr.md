# payment-service

[Русский](README.md) · [English](README.en.md) · [中文](README.zh.md) · [हिन्दी](README.hi.md) · [Español](README.es.md) · **Français** · [Deutsch](README.de.md) · [Italiano](README.it.md)

Prototype backend de gestion des états de paiement. Projet complémentaire du portfolio ; aucune extension fonctionnelle prévue actuellement. Les tests utilisent un fournisseur simulé et ne prouvent ni intégration réelle, ni certification, ni exploitation en production.

## Installation et tests

CI teste Python 3.11 et 3.12. Le Dockerfile utilise Python 3.14 ; la construction de l’image est un contrôle distinct. SQLite conserve opérations, événements et reçus. Définissez DATABASE_PATH vers un emplacement accessible en écriture avant d’importer l’application. Chaque test utilise une base isolée.

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
mkdir -p testdata
DATABASE_PATH="$PWD/testdata/bootstrap.sqlite" .venv/bin/python -m pytest tests/ -v --cov=src --cov-report=term-missing
```

## Démonstration Docker

Compose utilise une image externe provider-simulator ; son téléchargement requiert un accès au registre et sa disponibilité n’est pas garantie par les tests unitaires. Le volume candidate-data conserve SQLite après redémarrage ; le supprimer efface les données. PROVIDER_URL configure le fournisseur ; CALLBACK_URL appartient au simulateur et pointe vers le service de reçus.

```sh
git clone https://github.com/Anton-Sergeev-EA/payment-service.git
cd payment-service
docker compose up --build
```

```sh
curl http://localhost:8080/health
curl http://localhost:8080/metrics
docker compose logs -f payment-service
```

## API et états

GET /health vérifie la réponse du processus, pas les dépendances ni la réalisation d’un paiement. GET /metrics renvoie des compteurs JSON, pas le format Prometheus. POST /operations crée une opération : operationId requis, amount positif avec au plus deux décimales, currency RUB. POST /operations/{id}/submit enregistre l’intention : premier appel 202, répétitions ou états finaux 200. GET /operations/{id} consulte l’état ; GET /operations/{id}/events consulte l’historique. POST /receipts reçoit providerPaymentId, operationId, result (COMPLETED ou REJECTED), message et occurredAt.

CREATED → PROCESSING → COMPLETED / REJECTED. Le premier reçu valide fixe l’état final ; les doublons ou reçus tardifs opposés sont ignorés. Un providerPaymentId lié incompatible produit 409. Validation, opérations absentes et conflits ont des chemins spécifiques ; un corps invalide ne garantit pas toujours un 400.

## Reprise et limites

L’intention locale est enregistrée avant l’appel externe. Le client envoie Idempotency-Key et X-Correlation-ID avec operationId ; certains échecs transitoires déclenchent jusqu’à cinq tentatives avec attente exponentielle et jitter. La reprise au démarrage et périodique recherche les opérations PROCESSING. Les journaux JSON incluent operation_id, provider_payment_id et attempt selon le contexte. Les tests API, concurrence et reprise ne prouvent pas la tolérance aux pannes de tout fournisseur réel.

Au plus un paiement externe exige une idempotence durable du fournisseur ; SQLite seul ne la garantit pas. Avant utilisation réelle : authentification, vérification de l’authenticité des callbacks, audit de sécurité et procédures opérationnelles. Aucun paiement réel ni certification revendiqué. Ces traductions ne modifient pas les réponses ou journaux de l’application.

## Exemple d’opération

```sh
curl -X POST http://localhost:8080/operations \
  -H 'Content-Type: application/json' \
  -d '{"operationId":"demo-1","amount":"100.00","currency":"RUB","description":"Demo"}'
curl -X POST http://localhost:8080/operations/demo-1/submit
curl http://localhost:8080/operations/demo-1
curl http://localhost:8080/operations/demo-1/events
```

[Voir le README russe pour les exemples détaillés et la structure.](README.md)
