# SAE 302 – Maître/Esclaves d’exécution de code (version patchée)

## Prérequis
- **OS** : Windows 10/11 64-bit ou Linux (Ubuntu 20.04+)
- **Python** : 3.9+
- **Dépendances Python** : `pip install -r docs/requirements.txt`
- **Compilateurs** :
  - C/C++ : GCC / G++ (TDM-GCC sous Windows)
  - Java : JDK (javac/java dans le PATH)

## Arborescence
```
vasla13-sae302/
├── client/
│   └── client.py
├── Server/
│   ├── server_maitre.py
│   └── server_esclave.py
└── docs/
    ├── README.md
    ├── requirements.txt
    └── video.txt
```

## Installation rapide
```bash
# Python deps
pip install -r docs/requirements.txt

# Vérifier GCC/G++
gcc --version && g++ --version
# Vérifier Java
javac -version && java -version
```

## Lancement
Dans un terminal :
```bash
cd Server
# (facultatif) sécuriser ADMIN
# Linux/macOS : export ADMIN_TOKEN=monsecret
# Windows PowerShell : $env:ADMIN_TOKEN="monsecret"

python server_maitre.py  # écoute sur 0.0.0.0:5000
```

Client :
```bash
cd client
python client.py
```
Renseigne `IP du serveur` et `Port`, choisis le langage, saisis ou importe un fichier, puis **Exécuter le code**.

## Commandes ADMIN (via le client)
- **GET_INFO**
- **SET_MAX_TASKS|<int>**
- **SET_MAX_SLAVES|<int>**

Depuis une machine distante : `ADMIN|TOKEN=<ADMIN_TOKEN>|GET_INFO` (si `ADMIN_TOKEN` défini côté serveur).

## Sécurité & limites
- Exécution sandboxée avec limites CPU/Mémoire/Fichier sur Unix (via `resource`). Sous Windows, limites par **timeout**.
- Fichiers compilés/exécutés dans des **répertoires temporaires isolés** (un par job) puis nettoyés.
- `filename` est **assaini** (pas de traversée de répertoires, extension forcée selon langage).

## Notes Java
- Le fichier doit contenir une classe publique dont le **nom == nom du fichier** (ex. `Main.java` → `public class Main`).

## Vidéos / Liens
- Voir `docs/video.txt`

> **Info** : Le fichier original `Rapport Final Sae302.docx` n’était pas fourni dans la conversation, il n’est donc pas inclus ici.
