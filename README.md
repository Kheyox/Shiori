# 栞 Shiori

Convertisseur de mangas pour liseuses **Kobo** (pensé pour la Libra Colour).
**100 % local** : tout se passe dans le navigateur via `<canvas>`, rien n'est envoyé.

Un seul fichier HTML statique (`kobo-converter.html`), sans framework ni build,
plus les fichiers PWA.

## Utilisation

1. Dépose tes tomes (CBZ, ZIP, CBR, EPUB ou dossiers d'images).
2. Vérifie l'aperçu « Sur ta Kobo » (page par page, avant/après).
3. Choisis couleur / sens de lecture / doubles pages si besoin, puis **Convertir**.

## Ce que fait la conversion

- **Marges rognées** automatiquement (fond blanc, noir ou crème détecté sur les coins).
- **Jamais d'étirement** : mise à l'échelle uniforme, la page est centrée sur la
  couleur du papier, à la taille exacte de l'écran (1264×1680 pour la Libra Colour).
- **Couleur auto** : une page n'est gardée en couleur que si elle en contient
  vraiment ; sinon niveaux de gris + niveaux auto (papier jauni → blanc pur).
  Les pages couleur reçoivent une légère hausse de saturation (écran Kaleido).
- **Doubles pages** : pivoter, couper en 2 ou laisser.
- Sortie **KEPUB** (ou CBZ) avec série, numéro de tome, sens RTL, et auteur/résumé récupérés en ligne (désactivable).

## Lancer en local

```bash
npx serve .
```

Puis `http://localhost:3000/kobo-converter`. Déploiement : voir [DEPLOY.md](DEPLOY.md).
