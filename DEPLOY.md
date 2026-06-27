# Déployer Shiori sur Firebase Hosting

Shiori reste **un site statique** (un seul fichier HTML + quelques fichiers PWA).
Firebase Hosting le sert en HTTPS, ce qui le rend accessible partout et
**installable en PWA** (Windows / Chromebook / Android).

## 1. Pré-requis (une seule fois)

```bash
# Installer la CLI Firebase
npm install -g firebase-tools

# Se connecter à ton compte Google
firebase login
```

## 2. Créer / relier le projet Firebase

Crée un projet sur https://console.firebase.google.com (ou réutilise un projet
existant), puis relie-le au dépôt :

```bash
# Remplace le placeholder de .firebaserc par TON id de projet réel
firebase use --add
```

> `.firebaserc` contient pour l'instant `"default": "shiori-app"` — c'est un
> placeholder. `firebase use --add` le remplacera par l'id réel de ton projet.

## 3. Déployer

```bash
firebase deploy --only hosting
```

La CLI affiche l'URL publique, du type `https://TON-PROJET.web.app`.
Ouvre-la, puis utilise le bouton **« Installer l'app »** (en-tête) ou
le menu du navigateur pour l'ajouter à l'écran d'accueil.

## Comment c'est branché

- **`firebase.json`** — config Hosting. Sert tout le dépôt (`"public": "."`),
  ignore les fichiers techniques, et **réécrit toute URL inconnue vers
  `kobo-converter.html`** : l'app se charge donc à la racine `/`.
  Les en-têtes de cache forcent `sw.js` / `manifest` / HTML à se rafraîchir,
  et mettent les icônes en cache long.
- **`manifest.webmanifest`** — métadonnées PWA (nom, couleurs, icônes).
- **`sw.js`** — service worker : met l'app en cache pour le **mode hors-ligne**
  (réseau d'abord pour les pages, cache d'abord pour les assets). L'auth Google
  et l'API Drive ne sont jamais interceptées.
- **`icons/`** — icônes PWA (192 / 512 / maskable / apple-touch) + source SVG.

## Mettre à jour l'app

1. Modifie `kobo-converter.html` (ou autre).
2. Si tu changes des fichiers mis en cache, **incrémente `VERSION`** en haut de
   `sw.js` (ex. `shiori-v1` → `shiori-v2`) pour invalider l'ancien cache.
3. `firebase deploy --only hosting`.

## Export Google Drive (optionnel)

L'export Drive nécessite un **ID client OAuth** Google :

1. Dans Google Cloud Console, crée un ID client OAuth de type *Web*.
2. Ajoute ton domaine Firebase (`https://TON-PROJET.web.app`) dans les
   **origines JavaScript autorisées**.
3. Active l'**API Google Drive**.
4. Colle l'ID dans `GOOGLE_CLIENT_ID` (en haut du `<script>` de
   `kobo-converter.html`), puis redéploie.

Tant que `GOOGLE_CLIENT_ID` est vide, le reste de l'app fonctionne ; seul le
bouton « Envoyer vers Drive » affiche un message de configuration.
