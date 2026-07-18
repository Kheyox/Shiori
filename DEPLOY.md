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

## Déploiement automatique (GitHub Actions)

Le workflow `.github/workflows/firebase-hosting.yml` redéploie le site **à chaque
push sur `main`**. Tant qu'il n'est pas configuré, il ne plante pas : il affiche
juste un avertissement et saute le déploiement.

Pour l'activer, **2 choses à faire une seule fois** :

### a) Mettre le vrai id de projet dans `.firebaserc`

Remplace le placeholder `shiori-app` par l'id réel de ton projet Firebase
(visible dans la console Firebase). Le workflow lit l'alias `default`.

### b) Créer le secret `FIREBASE_SERVICE_ACCOUNT`

1. Console Firebase → ⚙️ **Paramètres du projet** → onglet **Comptes de service**
   → **Générer une nouvelle clé privée**. Un fichier **JSON** est téléchargé.
2. Sur GitHub : dépôt → **Settings** → **Secrets and variables** → **Actions**
   → **New repository secret**.
   - **Name** : `FIREBASE_SERVICE_ACCOUNT`
   - **Secret** : colle **tout le contenu** du fichier JSON.

C'est tout. Au prochain push sur `main`, le site se déploie tout seul. Tu peux
aussi le lancer à la main depuis l'onglet **Actions** → *Déploiement Firebase
Hosting* → **Run workflow**.

> Le JSON du compte de service est sensible : ne le commit jamais dans le dépôt,
> garde-le uniquement dans le secret GitHub.

## En faire une « vraie app » (Windows / Android)

### Windows — déjà prêt
Ouvre le site dans Chrome ou Edge → bouton **« Installer l'app »**. Shiori
devient une application fenêtrée avec son icône dans le menu Démarrer.
Grâce aux `file_handlers` du manifest, tu peux associer les `.cbz` à Shiori :
clic droit sur un fichier → *Ouvrir avec* → Shiori (après installation).

### Android — APK via PWABuilder (Trusted Web Activity)
Pour une **application Android installable** (APK, distribuable ou publiable
sur le Play Store) :

1. Va sur https://www.pwabuilder.com et entre `https://shiori-5be31.web.app`.
2. Onglet **Android** → **Generate package** (garde le package proposé, ex.
   `app.web.shiori_5be31.twa`, ou choisis le tien).
3. PWABuilder te fournit un **APK signé** + l'**empreinte SHA-256** de la
   clé de signature (fichier `signing.keystore` à conserver !).
4. Colle cette empreinte dans `.well-known/assetlinks.json` (à la place du
   placeholder), même package name, puis redéploie (`push` sur `main`).
   → C'est ce qui fait disparaître la barre d'adresse : Google vérifie que
   l'app et le site t'appartiennent tous les deux.
5. Installe l'APK (ou téléverse le `.aab` sur le Play Store, compte
   développeur 25 $ une fois).

L'app Android profite alors du **partage système** (« Partager → Shiori »
depuis n'importe quelle app) déclaré dans le manifest.

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

Tu peux aussi **coller l'ID directement dans l'app** : au premier clic sur
« Envoyer vers Drive », Shiori te le demande et le mémorise dans le navigateur
(pas besoin de toucher au code ni de redéployer).

Tant qu'aucun ID n'est fourni, le reste de l'app fonctionne normalement.

## Application Windows (.exe)

Le workflow **Build Windows (.exe)** (`.github/workflows/build-windows.yml`)
compile une vraie application de bureau (Tauri : fenêtre native + moteur Edge
WebView2, ~10 Mo) sur une machine Windows de GitHub :

- **À la main** : onglet Actions → *Build Windows (.exe)* → Run workflow →
  récupère l'artefact `Shiori-Windows` (installateur `.exe`).
- **Par tag** : `git tag v1.0.1 && git push origin v1.0.1` → build + **Release
  GitHub** avec le `.exe` téléchargeable.

L'app embarque le convertisseur en local (JSZip et pdf.js vendorisés ⇒
fonctionne hors-ligne). Limites connues : l'export Google Drive ne marche pas
dans l'exe (origine OAuth non web) — utiliser le site pour ça ; la lecture des
.cbr télécharge sa lib au premier usage (internet requis une fois).
L'exe n'est pas signé : SmartScreen affichera « informations complémentaires »
au premier lancement (normal pour une app perso).

### Vérificateur de mise à jour de l'exe

L'exe compare sa version (constante `APP_VERSION` dans `kobo-converter.html`,
figée à la compilation) au `/version.json` du site (généré automatiquement au
déploiement depuis cette même constante). **Quand tu veux signaler une nouvelle
version aux exe installés : incrémente `APP_VERSION`** (ex. 1.1.0 → 1.2.0) —
le site publiera la nouvelle valeur et les anciens exe afficheront le bandeau
« Télécharger ».
