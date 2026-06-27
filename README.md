# 栞 Shiori

Convertisseur de mangas/comics pour liseuses **Kobo** (Libra Colour, Clara, Sage,
Elipsa…). **100% local** : tout se passe dans le navigateur via `<canvas>`, rien
n'est uploadé. Fonctionne identique sur Windows, Chromebook et Android.

C'est volontairement **un seul fichier HTML statique** (`kobo-converter.html`),
sans framework ni build, plus quelques fichiers PWA.

## Fonctionnalités

- Entrée : `.cbz` / `.zip` + images en vrac (tri naturel, filtrage des fichiers
  parasites `__MACOSX` / dotfiles).
- Profils d'appareil Kobo + dimensions personnalisées.
- Traitements : niveaux de gris, gamma, auto-niveaux, rognage des marges,
  qualité JPEG réglable.
- Doubles pages (planches larges) : rotation paysage, coupe en 2, les deux, ou
  garder large.
- Sens manga (droite → gauche) avec `ComicInfo.xml`.
- Sortie CBZ par tome, « tout télécharger » en zip, export Google Drive.
- **PWA** : installable et utilisable hors-ligne.

## Lancer en local

C'est un fichier statique. Pour tester le service worker (PWA / hors-ligne), il
faut un serveur HTTP local (le `file://` ne permet pas les service workers) :

```bash
# au choix
npx serve .
# ou
python3 -m http.server 8000
```

Puis ouvre `http://localhost:8000/kobo-converter.html`.

## Déploiement (Firebase Hosting + PWA)

Voir **[DEPLOY.md](DEPLOY.md)**.
