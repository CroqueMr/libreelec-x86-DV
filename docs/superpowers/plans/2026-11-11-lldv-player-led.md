# Plan d’implémentation du Dolby Vision Player-Led (LLDV)

> Exécuter les étapes dans l’ordre avec `superpowers:executing-plans` et Ponytail. Chaque étape laisse un résultat vérifiable et un commit local.

## Objectif et architecture

Ajouter **Dolby Vision Player-Led (LLDV)** comme circuit pour les entrées Dolby Vision dans **Dolby Vision default playback** et dans le sélecteur en cours de lecture. Le PC reconstruit l’image Dolby Vision, applique le mapping une fois vers la cible écran et transmet le résultat par HDMI. Le choix **LLDV output format** reste indépendant du choix du circuit.

Conserver le décodage et la présentation Kodi, la reconstruction de Master Reference et les briques de mapping réutilisables de HDR10 Rendering Reference. Ajouter le chemin de sortie LLDV dans les propriétaires existants, avec le moteur CB1, FFmpeg et libplacebo déjà livrés. Le plan s’appuie sur le cadrage validé et sur les contrats [Master Reference](../../../CB1/docs/MASTER-REFERENCE.md), [creative mapping](../../../CB1/docs/CREATIVE-MAPPING.md) et [qualification CM4](../../../CB1/docs/CM4-QUALIFICATION.md).

## Contraintes et points de revue

- Partir de `work/lldv-handshake` et des commits `68adad3` et `6b134ab`. Garder les nouveaux commits en local. Publier le PR après la validation de bout en bout. Exclure le rebase et les changements de release.
- Le profil P5 conserve sa pleine plage IPT-PQ-C2 jusqu’à la conversion prévue par la chaîne couleur. Un FEL actif exige la couche d’amélioration de la même image, y compris après un seek. Le panneau Info rapporte le traitement de l’image présentée.
- Le mapper choisit une seule famille de trims pour la cible HDR. Traiter explicitement les cibles manquantes ou ambiguës et les contrôles HDR dont la sémantique reste à qualifier. Réserver au SDR les corrections secondaires de teinte et saturation par couleur.
- Le mode LLDV est propre à la sortie HDMI sélectionnée. Les circuits HDR10, HDR10+, SDR et Dolby Vision TV-led gardent leur comportement. Une transaction refusée doit conserver ou rétablir l’affichage et présenter la cause.
- Distinguer préférence enregistrée, route demandée et route active. Un choix temporaire ne change pas le défaut. Une route ou une profondeur indisponible garde sa préférence et indique la cause.

## 1. Qualifier le format HDMI et la cible

**Propriétaires.** `linux-9945-lldv-format-lab.patch`, `kodi-9999-zzzzzzzzzz-lldv-format.patch`, `tests/cb1/test_lldv_format.py` et les mires existantes du N100. Le noyau fournit `CB1_LLDV_FORMAT`. Kodi lit les capacités, le format actif et le timing dans `GetLldvConnectorStatus()`.

- [ ] Rejouer la base des deux mires 4K24 et relever les codes vidéo reçus avec une capture capable de les préserver. Contrôler la plage, l’ordre Cb/Cr et une différence limitée aux deux bits faibles. Mesurer sur la LG les gris, le noir et les couleurs. Consigner séparément le verrouillage HDMI, les codes reçus et la mesure optique.
- [ ] Réutiliser le décodage EDID commun pour exposer les informations Dolby effectivement présentes. Définir la cible avec le pic, le noir, les primaires, le blanc et la provenance des valeurs. Garder distincts EDID et mesure ou calibration. Les valeurs inconnues restent explicites.
- [ ] Étendre la matrice du test à 24,000 et 23,976 Hz. Vérifier qu’un timing incompatible, un EDID invalide, une TV sans ce format et un pilote sans la propriété reçoivent chacun la bonne raison. Essayer le 23,976 Hz sur le récepteur avant de l’annoncer dans Kodi. Le 4K60 reste désactivé tant qu’il échoue à la qualification.
- [ ] Vérifier que **Automatique** préfère 10 bits utiles et que le choix manuel 12 bits est conservé. Les deux modes utilisent des champs HDMI de 12 bits. Vérifier le rejet sans modification du mode courant et le retour au mode d’origine après la mire. Commit local.

### Mesures N100 et LG G5 du 11 novembre

Le noyau d’essai a accepté les quatre combinaisons et restauré l’état DRM après chaque mire. Le lanceur a relu l’horloge et le format actifs. Sur HDMI 2, la LG a confirmé les trois voies TMDS verrouillées, le YCbCr 4:2:2 annoncé par l’AVI et le paquet Dolby Low Latency. Le test atomique 4K60 a rejeté le mode avant toute modification de l’affichage.

| Horloge DRM | Précision de la mire source | Échantillons LG verrouillés |
| --- | --- | --- |
| 297000 kHz | 10 bits utiles | 25/29 |
| 297000 kHz | 12 bits | 26/29 |
| 296703 kHz | 10 bits utiles | 26/29 |
| 296703 kHz | 12 bits | 26/29 |

La différence des deux bits faibles a été vérifiée sur les rasters source. La capture interne de la LG montre les barres et les gris dans un PNG RGB 8 bits. Les modes natifs `SOURCE` et `VIDEO` ont refusé la capture. Restent la lecture des codes HDMI à 12 bits et les mesures optiques sur la dalle. Le passage à l’intégration du moteur attend ces preuves.

### Essai différentiel avec le matériel existant

À 4K24, le lanceur a gardé le format LLDV 12 bits actif et a uniquement changé le framebuffer. Il a alterné six fois la mire de base avec deux passages par bit faible et un contrôle à +32 codes. Les onze relevés Intel sont stables dans chaque phase et les quatre variantes ont des CRC distincts.

Sur la capture interne RGB 8 bits de la LG, la perturbation de +1 a donné un écart reproductible dans 7 plages stables et celle de +2 dans 23. Ces écarts sont répartis sur les bandes de luma et de chroma. Aucun écart des deux bits faibles ne se répète dans la bande proche du noir. La capture YUV422 demandée à la TV a été refusée.

Ce résultat établit que chaque perturbation influence le chemin vidéo capturé par la LG. Le traitement interne et sa quantification limitent la conclusion. Les codes HDMI natifs et les couleurs émises par la dalle restent à qualifier. La restauration DRM a réussi après l’essai.

## 2. Récupérer l’image Dolby Vision avant le mapping

**Propriétaires.** `CB1/src/cb1_master_reference.c`, `CB1/src/dvbridge_render.c`, les tests `master_reference`, `master_ipt` et `CB1/tests/reference/test_dovi_master_reference.py`. Réutiliser les entrées BL, EL, RPU et l’identité flux, image et révision de CB1.

- [ ] Fixer des sorties attendues avant mapping pour P5 pleine plage, P7 FEL non neutre, P7 MEL et les variantes P8 déjà admises, dont P8.4 HLG. Tester qu’un résiduel FEL positif ou négatif change effectivement les pixels et qu’une EL absente ou décalée est rejetée.
- [ ] Réutiliser la reconstruction qualifiée de Master Reference dans un chemin vers le mapper. Découpler cette étape du transport TV-led au point de sortie utile. Préserver les filtres, la précision et les matrices de reconstruction. Appliquer la conversion couleur du P5 une fois et préserver la distinction entre pleine plage d’entrée et plage HDMI de sortie.
- [ ] Rejouer la référence numérique ETSI et les tests C/GPU existants. Comparer les codes reconstruits avant mapping, notamment aux limites de plage et sur un FEL réel. Vérifier que le chemin TV-led existant garde ses sorties. Commit local.

## 3. Qualifier le mapping CM 2.9 et CM 4.0

**Propriétaires.** `CB1/src/dvbridge_creative.c`, `CB1/src/cb1_hdr10_expert.c`, `CB1/src/dvbridge_render.c`, `CB1/tests/creative_cm4.c`, `CB1/tests/creative_cm4_images.c` et `CB1/tests/reference/test_cm4.py`.

- [ ] Établir une référence externe à cible égale, avec versions, mode, gamut, plage et encodage documentés. Privilégier un rendu de référence Dolby disponible sur des mires isolant chaque contrôle applicable en HDR. Les vecteurs internes servent de garde numérique pendant que la référence externe est recherchée.
- [ ] Couvrir L1 seul, L3 non neutre, L8 seul, L2 et L8 présents ensemble, cible exacte ou encadrée, cible inconnue et métadonnées corrompues. Comparer le contraste des tons moyens, les hautes lumières, la chroma et les contrôles de détail HDR applicables. Consigner les contrôles dont l’effet reste à démontrer.
- [ ] Appliquer L3 à l’analyse L1 et sélectionner les trims HDR avec le résolveur existant, en tenant compte des descriptions L9 et L10 quand elles sont valides. Choisir le L8 applicable ou la compatibilité L2. Réutiliser les primitives et le shader CM4 lorsque le domaine et les mesures concordent. Le mapper reste le seul propriétaire des transformations créatives de luminance et de gamut.
- [ ] Comparer les pixels à la référence et vérifier que les familles de trims ne se cumulent pas. Fixer les tolérances avant d’examiner les résultats. Les écarts HDR non expliqués restent ouverts jusqu’à résolution. Mettre à disposition l’état réellement appliqué pour le panneau Info. Commit local.

### Moteur hors ligne

`dvbridge_render_player_led()` produit une texture RGBA32F aux dimensions de la source. Les canaux RGB sont linéaires dans le gamut cible et 1,0 représente son pic en nits. La reconstruction P5 et P7 FEL réutilise les filtres entiers de Master Reference et les matrices du RPU. Une EL FEL absente, décalée ou de taille incompatible est rejetée.

Les offsets L3 utilisables modifient le maximum et la moyenne de scène L1. Le minimum participe à la validation des statistiques. Un L8 compatible sélectionne les contrôles HDR ponctuels du modèle CB1 CM4. En l’absence de cible L8 compatible, le moteur reprend les trims L2 disponibles. Le détail spatial et les secondaires SDR restent hors du rendu. Les essais hors ligne couvrent les couleurs, le noir, les hautes lumières, les résiduels FEL et les changements de trims. La comparaison à un rendu Dolby externe et les mesures sur la LG restent à faire.

## 4. Brancher le circuit dans Kodi et sécuriser les bascules

**Propriétaires.** `DVOutputSettings.h`, `DVOutputSelection.h`, `DVPlaybackModes.cpp`, `DVPlaybackInfo.h` et `CWinSystemGbmGLESContext`, dans leurs patches Kodi existants. Côté moteur, ajouter le mode dans `CB1/src/dvbridge_policy.h` et son identité dans `CB1/src/cb1_circuit.c`. Côté HDMI, réutiliser `CDRMAtomic::FlipPageTransactional()` et la propriété déjà testée.

- [ ] Étendre les tests existants des défauts et du sélecteur. Le nouveau choix est réservé aux sources DV admises. Le défaut s’applique au fichier suivant et le choix à la volée à la lecture en cours. Le circuit peut être proposé depuis l’accueil à 60 Hz si la TV et le pilote sont compatibles et que Kodi peut atteindre le timing de lecture qualifié. La disponibilité en cours de lecture suit le timing effectivement utilisable.
- [ ] Intégrer le mode au même parcours de sélection et de révision. Avant présentation, vérifier le format demandé, la cible et la capacité du pilote. Valider ensemble le premier framebuffer LLDV, la propriété du connecteur et le retrait des états HDR ou TV-led incompatibles. Déclarer le circuit actif après confirmation de la présentation.
- [ ] Réutiliser la restauration DRM et tester un refus de transaction, une déconnexion et une reprise, un seek, une pause, un arrêt et le passage au fichier suivant. Les bascules LLDV ↔ HDR10 et LLDV ↔ TV-led doivent rendre une image et récupérer le dernier état utilisable en cas d’échec. Vérifier aussi le retour SDR et l’absence de résidu LLDV sur les autres circuits.
- [ ] Vérifier la composition des sous-titres et de l’interface. Dans le panneau Info via **O**, indiquer le circuit, le format actif et les trims appliqués avec les règles de lisibilité existantes. Commit local.

## 5. Valider l’ensemble avant le PR

- [ ] Rejouer les tests ciblés sur les sources appariées, la suite CB1 et les contrôles de staging. Rejouer les patches avec zéro fuzz, compiler le noyau et Kodi, puis démarrer le build local sur le N100.
- [ ] Lire des extraits réels P5, P7 FEL, P7 MEL et P8 en 4K24 et 23,976 Hz. Confirmer la profondeur, la signalisation et les mesures sur la LG. Mesurer les images perdues après stabilisation et tester les bascules dans les deux sens, y compris une lecture longue du FEL le plus lourd retenu.
- [ ] Auditer les autres pilotes déjà pris en charge. Étendre l’admission aux couples pilote/TV effectivement qualifiés et garder une raison dans le sélecteur pour les autres. Tester en priorité les sorties 4:2:2 10 bits utiles et vérifier les chemins SDR/HDR/TV-led à chaque extension.
- [ ] Faire la revue finale Astra xhigh sur le mapping, le contrat de précision et la restauration HDMI. Résoudre les défauts avant publication. Le PR regroupe la fonctionnalité complète, ses preuves de fidélité et la matrice des modes qualifiés.

### Commandes de base

```sh
python3 -m unittest discover -s CB1/tests/reference -p 'test_cm4.py'
python3 -m unittest discover -s CB1/tests/reference -p 'test_dovi_master_reference.py'
python3 -m unittest discover -s tests/cb1 -p 'test_lldv_format.py'
python3 -m unittest discover -s tests/cb1 -p 'test_playback_defaults.py'
python3 -m unittest discover -s tests/cb1 -p 'test_*.py'
python3 CB1/tools/verify.py
python3 scripts/cb1-stage.py --check
git diff --check
```

Les tests qui compilent les propriétaires réels utilisent les sources appariées et les variables de `.github/scripts/prepare-test-sources.sh`. Vérifier que les tests ciblés ont été exécutés. Un test ignoré ne vaut pas validation.
