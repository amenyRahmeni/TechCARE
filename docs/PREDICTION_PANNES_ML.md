# TECHcare — Prédiction des pannes par machine learning

Le module ajoute une **Random Forest en Python** qui exploite les caractéristiques du PC et son historique pour produire trois niveaux : **faible**, **moyen**, **élevé**.

La version initiale est une **démonstration sur 1 600 observations simulées**, demandée pour ce projet. La base de l’atelier ne contient pas encore assez d’observations de pannes pour apprendre un risque réel. Les données synthétiques ne sont jamais ajoutées aux PC, rendez-vous ou historiques métier. Le badge « Démonstration » et le texte sous le résultat indiquent cette limite.

## Parcours dans les interfaces

| Rôle | Accès |
| --- | --- |
| Client | Menu **Prédiction des pannes**, sélection d’un de ses PC, puis **Analyser ce PC**. Un panneau de la fiche PC mène aussi à cette page. |
| Technicien | Même parcours, limité aux PC de ses rendez-vous ou réparations assignés. Il peut analyser ces PC sans modifier leurs caractéristiques. |
| Administrateur | Analyse de tous les PC et menu **Modèle ML** pour entraîner, importer un CSV et consulter les métriques et versions. |

Adresses :

- `/predictions/` : ordinateurs accessibles et dernières analyses.
- `/predictions/pc/<id>/` : résultat, données d’entrée, seuils et historique.
- `/predictions/pc/<id>/analyser/` : calcul par POST avec authentification et CSRF.
- `/backoffice/prediction-ml/` : gestion et entraînement du modèle, réservés aux administrateurs.
- `/backoffice/prediction-ml/gabarit.csv` : gabarit CSV vide.

Une consultation GET ne lance pas de calcul et n’enregistre pas de prédiction. Un POST utilise les données du PC stockées côté serveur ; il ignore des valeurs de RAM, score ou niveau injectées dans le formulaire. Les droits sont vérifiés de nouveau dans le service. Si le PC est réaffecté, l’ancien technicien perd l’accès.

## Ce que le modèle apprend

Chaque observation contient des caractéristiques **connues au jour d’observation** et une cible binaire : `failure_within_90d`, égale à 1 si une panne a été observée dans les 90 jours suivants, 0 si le suivi complet de cette période n’en a pas relevé.

La Random Forest est entraînée avec **80 arbres CART**, profondeur maximale **6**, au moins **12 observations par feuille** et une graine **42**. Chaque arbre reçoit un échantillon bootstrap, examine des sous-ensembles aléatoires de variables et choisit les coupures réduisant l’impureté de Gini. Ses feuilles contiennent des fréquences de classe apprises. Le score correspond à la moyenne des sorties des arbres. L’algorithme apprend sur les exemples ; le score n’est pas le résultat du moteur de règles déjà présent dans Maintenance.

| Score du modèle | Niveau affiché |
| --- | --- |
| Moins de 0,25 | Faible |
| De 0,25 inclus à 0,60 exclu | Moyen |
| À partir de 0,60 | Élevé |

Ces seuils sont des choix du projet. Un score de 70 % dans la démonstration ne signifie pas qu’un PC réel a 70 % de chances de tomber en panne. Il n’est pas utilisé pour créer automatiquement des alertes de panne ou modifier une réparation, une facture ou le stock.

Les règles existantes restent responsables des recommandations de maintenance. Le modèle ne lit ni noms, ni e-mails, ni numéros de série, ni photos ou texte libre du client.

## Données d’entrée et CSV

Le fichier utilise une virgule comme séparateur et l’encodage UTF-8. L’exemple reproductible est [demo_pc_failures.csv](../data/ml/demo_pc_failures.csv). Les colonnes attendues sont :

| Colonne | Sens et valeurs |
| --- | --- |
| `data_origin` | `simulated` pour des exemples synthétiques, `real` pour un historique fourni. Une seule origine par CSV. |
| `machine_id` | Identifiant pseudonyme stable d’une machine, 80 caractères maximum. Aucun nom ou numéro de série personnel. |
| `observed_on` | Date de l’observation, format `AAAA-MM-JJ`. |
| `pc_age_days` | Nombre de jours depuis l’achat ; `-1` si la date d’achat est inconnue. Maximum : 10 958 jours. |
| `ram_gb` | RAM en Go, de 1 à 512. |
| `storage_gb` | Stockage en Go, de 1 à 32 768. |
| `is_hdd` | 1 pour HDD, 0 pour SSD. |
| `is_laptop` | 1 pour portable, 0 pour bureau. |
| `maintenance_count` | Nombre total d’entretiens réalisés et enregistrés avant ou à la date d’observation. |
| `repair_count` | Nombre de ces entretiens correspondant à des réparations. |
| `repairs_last_365d` | Réparations réalisées dans les 365 jours précédant l’observation. |
| `preventive_last_365d` | Entretiens préventifs dans cette même période. |
| `days_since_last_maintenance` | Délai depuis le dernier entretien enregistré, ou `-1` en l’absence d’historique. |
| `failure_within_90d` | Cible d’entraînement : 0 ou 1, fondée sur un suivi complet après observation. Jamais une entrée du modèle. |

Les nombres d’entretiens et réparations doivent être cohérents. Une date d’achat manquante reste inconnue ; l’application ne la remplace pas par une date inventée. Les dates futures de maintenance ne sont pas utilisées pour le calcul.

Pour un CSV déclaré réel, `observed_on` doit précéder la date actuelle d’au moins 90 jours. L’absence d’une demande dans TECHcare ne prouve pas l’absence d’une panne : ne pas fabriquer des cibles 0 à partir de cette seule absence. Les caractéristiques doivent correspondre à la date d’observation, sans reprendre des mises à niveau ou interventions ultérieures.

L’import exige entre **100 et 20 000 observations**, au moins **20 machines distinctes** et **20 exemples de chaque classe**. Taille maximale : **5 Mo**. Les colonnes incorrectes, doublons machine/date, origines mélangées et valeurs incohérentes sont refusés. Le CSV importé n’est pas enregistré dans un répertoire public.

L’origine `real` décrit ce que l’administrateur fournit ; elle n’est pas une certification de la qualité des données. Une copie de données simulées ne devient pas un historique empirique en changeant ce champ.

## Entraînement et évaluation

Les données sont réparties par **machine** : environ 80 % pour l’entraînement et 20 % pour le test. Les machines sont regroupées selon leur classe majoritaire puis réparties aléatoirement avec la graine choisie. Toutes les observations d’une même machine restent dans un seul ensemble. Le test n’est jamais utilisé pour entraîner les arbres. Si cette répartition ne laisse pas les deux classes dans chaque ensemble, l’entraînement est refusé.

L’interface d’administration présente :

- le nombre d’observations et de machines dans chaque ensemble ;
- ROC-AUC, exactitude, exactitude équilibrée et score de Brier sur le test ;
- une référence de Brier fondée sur une prédiction constante ;
- l’importance globale des variables et les versions entraînées.

La matrice de confusion, les paramètres, la graine, la version du moteur Python et l’empreinte du jeu de données sont aussi enregistrés dans `FailureModel`. L’importance d’une variable décrit les arbres entraînés ; elle n’établit pas une cause physique de panne.

La séparation par machine limite le partage d’observations entre entraînement et test. Pour un usage réel, il faut encore vérifier la qualité des labels, la représentativité du parc, la calibration et les performances sur une période future indépendante. Les métriques obtenues sur des données simulées évaluent uniquement cette simulation.

## Commandes de reproduction

Après installation des dépendances et migrations :

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py train_failure_model --demo
```

Pour exporter une nouvelle simulation dans un fichier qui n’existe pas encore :

```powershell
.\.venv\Scripts\python.exe manage.py generate_failure_dataset --output data/ml/nouvelle_simulation.csv --samples 1600 --seed 42
```

Pour entraîner un historique CSV :

```powershell
.\.venv\Scripts\python.exe manage.py train_failure_model --csv chemin/observations.csv
```

L’administration web propose les mêmes opérations. Un entraînement réussi crée une nouvelle version, qui devient le modèle courant. Un import invalide laisse le modèle précédent disponible. Les prédictions anciennes conservent leur version et leurs données d’entrée ; un changement de configuration, d’historique, de date ou de modèle affiche « À actualiser ».

## Fichiers du module

| Fichier | Responsabilité |
| --- | --- |
| `predictions/models.py` | Modèles entraînés, paramètres, métriques et prédictions historisées. |
| `predictions/dataset.py` | Génération reproductible de données simulées, lecture et validation CSV. |
| `predictions/features.py` | Extraction des caractéristiques, valeurs manquantes et empreintes. |
| `predictions/training.py` | Coordination de l’entraînement, validation et enregistrement de la version. |
| `predictions/learning.py` | Apprentissage des arbres CART, bootstrap, sous-ensembles de variables, séparation par machine et métriques. |
| `predictions/engine.py` | Export des arbres en JSON, calcul du score et attribution du niveau. |
| `predictions/services.py` | Contrôle des droits, calcul et conservation du résultat. |
| `predictions/views.py` | Vues client, technicien et administrateur. |
| `predictions/management/commands/` | Génération CSV et entraînement par commandes Django. |
| `templates/predictions/` | Tableau des PC, analyse détaillée et administration ML. |
| `static/css/predictions.css` | Thème sombre bleu/orange, jauge et graphiques responsives. |
| `predictions/tests.py` | Tests d’équivalence du moteur, validation des données, entraînement et isolation entre rôles. |

Le moteur utilise la bibliothèque standard Python et conserve les arbres en **JSON dans MySQL**. Il n’exécute aucun pickle fourni par l’utilisateur. Les tests vérifient l’apprentissage sur une relation étiquetée, la conservation des scores après rechargement JSON, les métriques sur des cas connus et la séparation des machines. Le démarrage et l’entraînement fonctionnent directement avec le Python du projet, sans dépendance scientifique native supplémentaire.

Vérification de la version livrée : **256 tests serveur réussis** pour l’ensemble du projet, et **40 contrôles responsive dans Chrome** pour le ML. Les parcours couvrent les trois rôles, le calcul réel d’un score, les analyses devenues anciennes après modification d’un PC et le réentraînement par l’administration. Les essais ont utilisé une base MySQL isolée ; aucun PC ni historique de test n’a été ajouté à la base de l’atelier.

Références : [RandomForestClassifier](https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.RandomForestClassifier.html), [séparation par groupes](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.StratifiedGroupKFold.html), [prévention des fuites de données](https://scikit-learn.org/stable/common_pitfalls.html), [évaluation des probabilités](https://scikit-learn.org/stable/modules/model_evaluation.html#brier-score-loss).
