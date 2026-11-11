# Plan d’implémentation du Dolby Vision Player-Led (LLDV)

> Exécuter les étapes dans l’ordre avec `superpowers:executing-plans` et Ponytail. Chaque étape laisse un résultat vérifiable et un commit local.

## Objectif et architecture

Ajouter **Dolby Vision Player-Led (LLDV)** comme circuit pour les entrées Dolby Vision dans **Dolby Vision default playback** et dans le sélecteur en cours de lecture. Le PC reconstruit l’image Dolby Vision, applique le mapping une fois vers la cible écran et transmet le résultat par HDMI. Le choix **LLDV output format** reste indépendant du choix du circuit.

Conserver le décodage et la présentation Kodi, la reconstruction de Master Reference et les briques de mapping réutilisables de HDR10 Rendering Reference. Ajouter le chemin de sortie LLDV dans les propriétaires existants, avec le moteur CB1, FFmpeg et libplacebo déjà livrés. Le plan s’appuie sur le cadrage validé et sur les contrats [Master Reference](../../../CB1/docs/MASTER-REFERENCE.md), [creative mapping](../../../CB1/docs/CREATIVE-MAPPING.md) et [qualification CM4](../../../CB1/docs/CM4-QUALIFICATION.md).

## Contraintes et points de revue

- Reprendre `work/lldv-handshake` à `dc13405`. Garder les commits locaux sur cette branche, sans rebase. La préparation du PR vient après la validation de bout en bout. La release reste hors de ce travail.
- Le profil P5 conserve sa pleine plage IPT-PQ-C2 jusqu’à la conversion prévue par la chaîne couleur. Un FEL actif exige la couche d’amélioration de la même image, y compris après un seek. Le panneau Info rapporte le traitement de l’image présentée.
- Le mapper choisit une seule famille de trims pour la cible HDR. Traiter explicitement les cibles manquantes ou ambiguës et les contrôles HDR dont la sémantique reste à qualifier. Réserver au SDR les corrections secondaires de teinte et saturation par couleur.
- Le mode LLDV est propre à la sortie HDMI sélectionnée. Le 4:2:2 10 bits utiles est la cible commune des pilotes Generic CB1. Réutiliser le chemin natif quand il est disponible pour le format retenu et réserver le forçage au LLDV sur les autres chemins. Les circuits HDR10, HDR10+, SDR et Dolby Vision TV-led gardent leur comportement. Une transaction refusée doit conserver ou rétablir l’affichage et présenter la cause.
- Distinguer préférence enregistrée, route demandée et route active. Un choix temporaire ne change pas le défaut. Une route ou une profondeur indisponible garde sa préférence et indique la cause.

## Exécution autonome depuis `dc13405`

La branche locale `work/lldv-handshake` dispose du handshake d’essai Intel, du moteur linéaire, du packing 4:2:2 et des informations à afficher via **O**. Les essais hors écran sur le N100 valident les octets produits aux deux profondeurs. Les étapes ci-dessous ordonnent le travail restant. Les sections suivantes conservent les résultats et les références de qualification.

### A. Préparer les deux mesures physiques

**Propriétaires** `linux-9945-lldv-format-lab.patch`, `kodi-9999-zzzzzzzzzz-lldv-format.patch`, `tests/cb1/test_lldv_format.py` et les mires `work/lldv-n100-hdmi-20261111` du projet local.

- [ ] Inventorier les moyens déjà accessibles. Préparer un lot unique de rasters, codes attendus et commandes de capture. Inclure noir et gris, primaires et secondaires, phase de chroma et rampes autour des bits 0 et 1. Conserver le timing, le preset LG, la cible, les hachages des rasters et l’état restauré. La propriété DRM, les infoframes, les CRC et les PNG 8 bits servent de diagnostics.
- [ ] Sur le N100 et la LG, rejouer les **mires autonomes** aux deux profondeurs à 23,976 et 24 Hz. Lire les mots Y/Cb/Cr sur un récepteur qui préserve les codes 12 bits et vérifier la signalisation au même passage. Exiger les mêmes mots que la mire, les deux bits faibles à zéro en 10 bits utiles et des transitions distinctes de +1 et +2 en 12 bits.
- [ ] Mesurer les gris, le proche-noir, la luminance et les couleurs avec une sonde sur la LG. Comparer à une mire LLDV de référence à cible identique dans le même preset et fixer les tolérances à partir de l’incertitude de mesure et de la répétabilité avant le comparatif. Vérifier que l’insertion du récepteur de mesure conserve l’EDID et le mode observé sur la LG. Archiver les mesures de lien et de dalle avec l’état HDMI restauré.
- [ ] Identifier 25, 29,97 et 30 Hz parmi les timings réellement exposés par la LG et proposés par Kodi. Le noyau et Kodi filtrent actuellement le **VIC 93**. Étendre leur contrat ensemble pour les timings qui passent le test atomique et les mêmes mesures physiques aux deux profondeurs. Le banc à 30 i/s mesure la cadence GPU indépendamment de cette admission HDMI.

**Dépendance actuelle** Les inventaires n’ont trouvé ni lecture HDMI brute 12 bits ni sonde de dalle. Le raccordement du moteur attend ces deux mesures. Les travaux B et C avancent sur le N100 hors écran avec les ressources existantes. Une preuve externe reproductible sur le même couple et les mêmes mires peut lever la dépendance si elle devient disponible.

### B. Tenir le budget 4K30 et qualifier la fidélité hors écran

**Propriétaires** `CB1/src/dvbridge_render.c`, `CB1/src/cb1_hdr10_expert.c`, `CB1/src/dvbridge_creative.c`, `CB1/tests/player_led_pack.c`, `CB1/tests/master_reference.c` et le banc VAAPI/EGL N100 déjà utilisé.

- [ ] Mesurer l’ensemble décodage, reconstruction FEL, mapping, ajustement de l’image et packing sur le N100. Utiliser le même commit, le même PTS et les mêmes clips pour comparer mapping seul, packing seul et chaîne complète. Mesurer la latence GPU par étape, le débit, les échéances manquées, la profondeur de file et l’effet de l’échauffement. Réutiliser le P5 30 i/s et le FEL lourd *1917*, avec contrôles MEL, P8.1 et P8.4.
- [ ] Réduire en priorité la répétition du PQ dans le packing actuel. Essayer d’abord une conversion native vers PQ une fois par pixel **après** la mise à l’échelle et la composition linéaires, suivie du packing. Mesurer le coût de la texture intermédiaire. Si son coût annule le gain, comparer une invocation par paire qui écrit les deux pixels, avec les fonctions GPU déjà présentes. Garder une seule solution qualifiée pour le matériel admis. Comparer le raster complet des mires et des images choisies à l’oracle 10/12 bits sur llvmpipe et ADL-N. Vérifier les deux bits faibles, les gamuts, la phase, les aplats, les bords et les refus. Si le FEL reste au-dessus du budget après le gain sur le packing, profiler d’abord sa reconstruction.
- [ ] Rejouer le banc sur 120 images d’échauffement puis trois fenêtres de 300 images. Le critère de cadence est le respect des échéances à 30 i/s sur les clips 30 et des échéances natives sur les autres. Les images perdues doivent être mesurées par timestamp. Le 60 i/s reste un résultat optionnel. Les mesures précédentes, 29,40 i/s pour le FEL lourd avant packing et 17,32 ms pour le packing seul, servent de référence de départ.
- [ ] Préparer les vecteurs Dolby à même source, même image, même cible et même gamut. Couvrir P5, le résiduel FEL apparié, le MEL sur la BL, les trims HDR ponctuels L2/L8 et L3, et les cinq modes CM4. Isoler Tone Detail/MS Weight pour L2 et L8 avec des contrôles appariés et les codes réellement exportés. Fixer les tolérances avant comparaison. Mesurer détail des hautes lumières, halos côté sombre, aplats, noirs et stabilité temporelle. Si le rendu Dolby contrôlé reste inaccessible, consigner la limite de la comparaison publique et conserver MS Weight comme métadonnée préservée en attendant la preuve. Le panneau rapporte seulement les traitements exécutés. [Contrôles Dolby Vision](https://professionalsupport.dolby.com/s/article/The-Dolby-Vision-Trim-Controls)

### C. Préparer le raccordement dans Kodi avec des transactions simulées

**Propriétaires** `DVOutputSettings.h`, `DVOutputSelection.h`, `DVPlaybackModes.cpp`, `DVPlayerLedOutput.h`, `CWinSystemGbmGLESContext` et `CDRMAtomic::FlipPageTransactional()` dans les patches Kodi. Réutiliser les préférences de lecture, la composition et la présentation existantes.

- [ ] Écrire d’abord les tests sur le défaut, le sélecteur à la volée et les raisons de refus dans `test_playback_defaults.py`, `test_quickswitch_paused_source.py` et `test_lldv_format.py`. Préparer l’admission DV, le choix manuel 12 bits, la conservation des préférences et les raisons distinctes côté écran, pilote, timing et source. Préparer la cible avec provenance EDID, calibration ou mesure explicite.
- [ ] Dans **LLDV output format**, afficher **4:2:2 · 10 bits** sur le chemin natif et **4:2:2 · 10 bits · Forcé · expérimental** quand le pilote utilise le forçage. **Automatique** privilégie le 10 bits, y compris le 10 bits forcé qualifié face au 12 bits natif. À précision égale, il privilégie le chemin natif. Si le mode retenu est forcé, l’afficher aussi dans la ligne **Automatique**. Tester natif, forcé qualifié et indisponible, avec la raison sur toute option grisée. La mention expérimentale reste visible quand le mode forcé est actif.
- [ ] Simuler un changement de circuit dans le propriétaire de présentation existant. L’unité à présenter contient le framebuffer préparé avec la bonne image, l’identité flux/image/révision, le format de connecteur demandé et le retrait des signaux incompatibles. Publier les faits LLDV seulement après présentation confirmée et relecture du mode actif sur le bon connecteur. Le timing sélectionné sert à l’admission et le timing confirmé à la télémétrie. Le passage inverse retire la propriété et le VSIF LLDV avec le premier framebuffer du circuit suivant.
- [ ] Tester les transitions dans les deux sens avec HDR10, TV-led et SDR, puis 10 ↔ 12. Injecter un refus `TEST_ONLY`, un échec de commit, une fence ou un page-flip tardif, une image devenue ancienne après seek, une perte de connexion entre test et commit et un échec de restauration. Le dernier état confirmé et ses buffers restent valides jusqu’au remplacement. Un refus de restauration reste signalé jusqu’à une nouvelle confirmation. Après reconnexion, retester le connecteur et reprendre un état d’affichage valide via la restauration Kodi. Réutiliser `presentation_transaction`, `test_native_video_telemetry.py` et `test_lldv_player_info.py`.
- [ ] Vérifier la composition linéaire des sous-titres et de l’interface avant packing, sans remapper le film. Vérifier les bords, l’orientation et le panneau **O** sur la même image acceptée. Tester la cohérence entre circuit, profondeur active, cible, FEL, mode CM4 et trims appliqués. La préparation reste testable avec des sorties simulées pendant la qualification physique.

### D. Raccorder et qualifier une version locale sur le N100 et la LG

- [ ] Après validation physique A pour les deux profondeurs à 23,976/24 Hz et validation hors écran B/C aux cadences admises pour cette première intégration, rejouer les patches avec les sources appariées et zéro fuzz. Étendre la version locale aux cadences suivantes à mesure qu’elles passent A et B. Faire un build incrémental noyau/Kodi avec retour local au build précédent vérifié. Activer le LLDV pour les couples format/timing qualifiés. Vérifier le premier framebuffer et l’état HDMI actif, puis les relire après retour aux circuits existants.
- [ ] Lire des extraits P5, P7 FEL/MEL, P8.1 et P8.4 aux timings admis, les deux profondeurs et les modes CM4 représentatifs. Vérifier reprise après pause, seek, changement de fichier, arrêt et débranchement/rebranchement. Pour la qualification 30 i/s, lire le FEL lourd au moins 30 minutes en cumulant les passages disponibles et relever séparément chaque transition de boucle. Exiger zéro image perdue après stabilisation, une file qui ne grossit pas, une synchro audio/vidéo stable, une restauration confirmée et la disparition du signal LLDV après sortie. Mesurer séparément le délai de resynchronisation HDMI des bascules.
- [ ] Comparer les mires envoyées par Kodi aux mires de qualification et relever à nouveau codes et couleurs. Rejouer Kodi default, SDR, HDR10, HDR10+ et TV-led. Un échec déclenche le retour local vérifié et une correction ciblée avant reprise.

### E. Élargir par pilote et préparer l’intégration

- [ ] Pour tous les pilotes Generic CB1 pris en charge, couvrir le 4:2:2 10 bits utiles, notamment Intel i915/xe, AMD amdgpu et NVIDIA, y compris le chemin Pascal. Relever les capacités par génération de GPU, version de pilote, port, EDID et timing. Qualifier séparément les chemins natif et forcé. Pour chaque chemin sans prise en charge native, implémenter le forçage au niveau du pilote si la liaison peut réellement émettre le 4:2:2. Le chemin forcé programme le transport et sa signalisation LLDV dans la transaction existante. Les deux chemins transportent les 10 bits utiles dans des mots HDMI de 12 bits.
- [ ] Remonter à Kodi le type de prise en charge réellement offert par le pilote et relire le chemin actif après la présentation. Admettre le chemin forcé si l’écran annonce le LLDV 4:2:2 et si le mode passe le test atomique et la qualification sur mire. L’échec d’une de ces vérifications grise l’option avec la cause. Tester aussi le refus à l’activation et le retour au dernier état confirmé, sans effet du forçage sur les circuits existants. Consigner par combinaison le résultat des mires, de la signalisation et du retour à l’affichage précédent.
- [ ] À chaque étape, obtenir une revue Astra xhigh sur le diff et les preuves associées, corriger les écarts, puis consigner commandes, mesures et commit local. Faire une revue finale qui couvre fidélité, cadence, restauration et matrice des pilotes. Préparer un seul PR quand la qualification de bout en bout atteint le périmètre prévu, avec les limites mesurées et les procédures de test. Le travail se déroule en commits locaux sur la branche existante, sans rebase ni mise à jour de la release.

### Vérifications à rejouer

```sh
EGL_PLATFORM=surfaceless ctest --test-dir <build-cb1> -R 'player_led_pack|master_lifecycle|master_spatial|hdr10_expert_composition|presentation_transaction' --output-on-failure
python3 -m unittest discover -s tests/cb1 -p 'test_lldv_*.py'
python3 -m unittest discover -s tests/cb1 -p 'test_native_video_telemetry.py'
python3 -m unittest discover -s tests/cb1 -p 'test_playback_defaults.py'
python3 -m unittest discover -s tests/cb1 -p 'test_quickswitch_paused_source.py'
python3 scripts/cb1-stage.py --check
python3 CB1/tools/verify.py
git diff --check
```

Les tests Kodi utilisent l’arbre apparié préparé par `.github/scripts/prepare-test-sources.sh`. Consigner les tests ignorés et rejouer sur matériel ceux qui conditionnent l’admission du mode. Un blocage physique ou une référence Dolby indisponible reste documenté avec sa preuve manquante pendant que les autres tâches avancent.

Les sections suivantes gardent le plan initial et les preuves recueillies avant ce découpage.

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

Les offsets L3 utilisables modifient le maximum et la moyenne de scène L1. Le minimum participe à la validation des statistiques. Un L8 compatible sélectionne les contrôles HDR ponctuels du modèle CB1 CM4. En l’absence de cible L8 compatible, le moteur reprend les trims L2 disponibles. Le détail spatial et les secondaires SDR restent hors du rendu. Les essais hors ligne couvrent les couleurs, le noir, les hautes lumières, les résiduels FEL et les changements de trims.

### Qualification sur les extraits du catalogue

Le premier essai avec des images FFmpeg YCbCr a révélé que libplacebo écartait l’EL avant la reconstruction. Le moteur associe maintenant la représentation Dolby du RPU validé à sa copie locale de l’image FEL, avec les bits de stockage du décodeur. Le test `master_spatial` reproduit cet import et compare le résultat entier à son oracle.

FFmpeg logiciel et llvmpipe ont traité les extraits ci-dessous vers une cible BT.2020 de 1 000 nits, sauf cible P3-D65 indiquée. Pour chaque extrait FEL, 61 paires BL/EL ont été vérifiées sur leur PTS. Six images ont été rendues et huit lignes RGB ont été lues par image. Les écarts FEL sont des maxima par composante entre le résultat et le contrôle avec résiduel désactivé.

| Extrait | Profil | Résultat hors ligne |
| --- | --- | --- |
| DV-001 · 1917 | P7 FEL | 6/6 images, écart maximal de 1,72 nit avec le résiduel. Le décodeur a signalé des avertissements sur l’extrait. |
| DV-073 · Transformers | P7 FEL | 6/6 images, écart maximal de 41,56 nits avec le résiduel. |
| DV-018 · Mire CM4 | P7 FEL | 6/6 images, écart maximal de 172,48 nits avec le résiduel. Le L8 de cible SDR reste exclu du rendu HDR. |
| DV-008 · Mire CM4 en MP4 | P7 FEL | 6/6 images, écart maximal de 188,75 nits avec le résiduel pour la cible P3-D65 de 1 000 nits. |
| DV-010 · Gemini Man | P7 MEL | 6/6 images 4K sur la BL, RPU joint depuis les deux pistes par `CBlurayDovi`. Le rendu réussit sans surface EL. |
| DV-026 et DV-028 · Sol Levante | P5 et P8.4 | 6/6 images par profil au même PTS après l’introduction. Les deux encodages donnent un écart moyen de 2,43 nits par composante sur les lignes sondées. |
| DV-063 · P8.1 à 25 i/s | P8.1 CM4 | 6/6 images avec L3 et L2 pour la cible P3-D65 de 1 000 nits. |
| DV-065 · P8.4 à 25 i/s | P8.4 CM4 | 6/6 images avec L3 et L2. Désactiver L2/L3 change le résultat jusqu’à 21,20 nits sur les lignes sondées. |

Le test injecte aussi un PTS EL décalé sur chaque extrait FEL. Le moteur le rejette avant rendu. Les extraits CM4 DV-022 et DV-030 sélectionnent le L8 P3-D65 à 600 nits, et DV-030 accepte aussi une cible intermédiaire à 800 nits. Les scènes sondées y donnent les mêmes pixels que le contrôle sans trims, ce qui confirme la sélection sans démontrer un effet créatif sur ces extraits. L’effet non neutre reste couvert par les mires de test.

Ces essais couvrent les images échantillonnées et la contribution du résiduel.

### Comparaison avec la couche HDR10 publiée par Dolby

Le P5 DV-026 et le P8.1 DV-027 de *Sol Levante* correspondent aux SHA-256 Git LFS publiés par Dolby. La couche de base du P8.1 `mapDynamic1000` est en YCbCr BT.2020 non constant, PQ, plage vidéo 10 bits. Le SEI annonce un écran de mastering P3-D65 de 1 000 nits. Le XML original Netflix décrit un master CM2.9 de 1 000 nits et une cible de trims SDR à 100 nits. Les paramètres du mapping HDR employé par Dolby pour ce fichier ne sont pas publiés. [Fichiers Dolby](https://github.com/DolbyLaboratories/dolby-vision-contents) · [XML de mastering Netflix](https://s3.amazonaws.com/download.opencontent.netflix.com/SolLevante/vdm/sollevante_lp_16b_hdr_p3d65pq_dolbyvision29.xml)

FFmpeg logiciel a décodé les deux fichiers. CB1 a rendu le P5 en RGB linéaire BT.2020 pour une cible de 1 000 nits. Le contrôle a décodé le P8.1 en HDR10 depuis sa couche de base, avec la matrice BT.2020 et l’EOTF PQ. Les 24 PTS communs couvrent quatre passages entre 16 et 188,5 s. Huit lignes paires et un pixel horizontal sur deux par image donnent 1 105 920 composantes RGB comparées. Le contrôle utilise une interpolation chroma bilinéaire. CB1 emploie son filtre vertical à six coefficients pour cette phase. Un décodage séquentiel depuis l’image 0 a reproduit les trois séries à l’identique et les 24 images contrôlées ne portaient aucun indicateur FFmpeg de corruption.

| Comparaison par composante RGB | Écart absolu moyen | P95 | Écart moyen en codes PQ 12 bits |
| --- | ---: | ---: | ---: |
| P5 via CB1 et couche HDR10 Dolby P8.1 | 2,92 nits | 14,00 nits | 17,93 |
| P8.1 via CB1 et sa propre couche HDR10 | 0,20 nit | 0,76 nit | 0,53 |

La couche HDR10 décodée comporte 140 pixels échantillonnés avec au moins une composante au-dessus de 1 000 nits. Onze dépassent 1 000 nits en luminance calculée. Après exclusion des 140 pixels, l’écart P5/HDR10 reste à 2,85 nits en moyenne et 13,93 nits au P95. Les écarts incluent l’encodage et le filtrage. Pour qualifier le mapping lui-même, il reste à rendre une source et ses métadonnées avec Dolby CM Offline à la même cible, notamment avec des trims HDR non neutres. Le téléchargement de CM Offline demande une connexion au portail Dolby. [Documentation Dolby CM Offline](https://professionalsupport.dolby.com/s/dolby-vision-professional-tools)

### Cadence 4K sur le N100 hors écran

Mesures avec le moteur du commit `79e75d3`, LibreELEC RC4 Preview Update 3, Mesa 26.2.3 et l’iGPU Intel ADL-N. Le banc lit les extraits locaux, décode en VAAPI, importe les surfaces P010 via DMA-BUF et rend en RGBA32F à 1 000 nits BT.2020 dans un contexte EGL sans surface d’affichage. Le FEL exige des PTS BL/EL identiques. Chaque série comprend 120 images d’échauffement et 900 images mesurées. Les délais en série sont mesurés entre deux fins de rendu. Le test avec trois images en vol attend les fences GPU avant de libérer les surfaces et relève le débit de trois fenêtres de 300 images.

| Source 4K | Débit en série | P95 en série | Débit avec trois images en vol |
| --- | ---: | ---: | ---: |
| P5 · Jellyfin 60 i/s | 41,47 i/s | 24,93 ms | — |
| P5 · fichier 30 i/s | — | — | 51,45 i/s |
| P7 FEL · *1917* à 30 i/s | 20,83 i/s | 51,88 ms | 26,26 i/s |
| P7 FEL · *1917* original à 23,976 i/s | 20,71 i/s | 52,33 ms | 26,27 i/s |
| P7 FEL · mire CM4 à 23,976 i/s, L8 SDR écarté | 28,30 i/s | 40,76 ms | 34,33 i/s |
| P8.4 · *Sol Levante* à 24 i/s | 32,43 i/s | 38,93 ms | 43,54 i/s |

Le seuil demandé est de 30 i/s, soit 33,33 ms par image. Le P5 à 30 i/s dépasse ce débit dans les trois fenêtres. *1917* plafonne autour de 26 i/s même en chevauchant décodage et rendu. Sur une image préimportée de l’extrait original, la requête GPU donne 29,29 ms en moyenne pour la reconstruction seule et 35,23 ms avec le mapping. La série P8.4 dépasse 41,67 ms sur 32 intervalles en mode série. Les fenêtres avec trois images en vol mesurent le débit, sans comptabiliser les échéances individuelles.

Les essais n’incluent pas la composition Kodi, le packing 4:2:2 ni la présentation HDMI. Le seuil de 30 i/s reste à atteindre sur le FEL lourd testé.

Le commit `d8b7707` évite le mapping des pixels reconstruits à zéro quand la cible a un plancher nul et que le trim CM4 ne relève pas le noir. Le raster complet, le plancher calibré et les offsets créatifs positifs conservent leur traitement. Sur la même image préimportée de *1917*, deux alternances donnent une médiane GPU de 34,85/34,84 ms avant et 33,21/33,19 ms après. Avec le moteur compilé en mode optimisé et trois images en vol, les 900 images donnent **29,50 i/s** sur l’original et **29,40 i/s** sur le dérivé 30 i/s. La fenêtre la plus lente du dérivé reste à 29,26 i/s. L’essai avec la LUT PQ native a ralenti le rendu sur ce GPU.

Le contrôle du moteur final donne **58,15 i/s** sur le P5 à 30 i/s. Les lignes lues sur 36 images P5, P7 FEL, P8.4 et CM4 sont identiques octet par octet à la version précédente. Les tests synthétiques couvrent également le noir neutre, le plancher de 0,01 nit et le relèvement créatif L8. Astra xhigh a relu les comparaisons, le banc de cadence et le raccourci de rendu.

### Optimisations AMD préparées hors ligne

`210e356` accélérait l’encodage PQ du circuit Adaptive sur radeonsi. Le moteur LLDV fournit du RGB linéaire à ce stade. L’essai de la table inverse native à 4 096 entrées donne au plus 0,355 code PQ 12 bits d’écart sur les huit lignes lues dans six images de chacun des extraits DV-001, DV-073 et DV-018. La mire FEL 4K saturée dépasse le seuil d’un code avec la table native (2,064 codes) et avec une adaptation de la table FP32 compacte de `fae3c37` (2,745 codes). Le décodage PQ analytique est conservé.

Le shader CB1 applique directement la pente et l’offset CM4 quand la puissance est exactement unitaire. Il calcule la luminance uniquement pour les contrôles actifs de contraste médian et d’écrêtage. Le comparatif logiciel sur 408 cas CM4 BT.2020 et P3 donne un écart maximal de 0,000194 nit et moins de 0,0001 code PQ 12 bits. Le rendu des entrées noires est identique dans tous les cas comparés. La cadence à 30 i/s sur Radeon et sur le FEL lourd reste à qualifier sur matériel.

### Choix CM4 et détail spatial MS Weight

Le moteur hors ligne reprend **Off**, **CM2.9 without L2 trims**, **Always**, **Auto** et **Auto 2**. La décision utilise la source originale et le pic de la cible LLDV. La copie sert uniquement au mapping, avec le L3 neutre et le L9 P3-D65 par défaut déjà employés dans Reference. Le CM4 d’origine garde la priorité. Les L2 restent applicables sauf désactivation explicite, y compris si l’ajout CM4 est refusé. `applied.cmv40_status` indique la décision à l’appelant. [Règles CM4](../../../CB1/docs/CM4-APPEND.md)

Le comparatif **Off** / **Always** a rendu six images par option sur DV-026 (P5), DV-073 (P7 FEL) et DV-030 (CM4 d’origine). Always ajoute le CM4 sur les deux premiers extraits. Le CM4 d’origine produit des lignes identiques dans les deux modes. Sur les lignes sondées, l’écart maximal est de 0,270 nit sur DV-073.

Dolby décrit Tone Detail comme une récupération de détail dans les hautes lumières. SMPTE ST 2094-10 §6.4 et l’annexe B.3 décrivent un facteur de mélange en lumière linéaire, entre 0 et 1, et laissent le filtre ouvert. L’annexe E de l’ATSC A/341:2023 réserve `-1` pour son propre transport. Cela ne fixe ni la conversion des codes Dolby L2/L8 ni le filtre utilisé par Dolby. [Contrôles Dolby](https://professionalsupport.dolby.com/s/article/The-Dolby-Vision-Trim-Controls) · [SMPTE ST 2094-10](https://pub.smpte.org/pub/st2094-10/st2094-10-2021.pdf) · [ATSC A/341](https://www.atsc.org/wp-content/uploads/2023/04/A341-2023-03-Video-HEVC.pdf)

Sur les 120 premières images de chacun de 11 extraits DV (1 320 RPU), tous les L8 observés valent 2048. Côté L2, *1917* (DV-001) a un code 0 à 100 nits. *Transformers* (DV-073) a un code 512 à 100 et 1 000 nits. Les autres L2 observés valent 2048. Ces fréquences ne déterminent pas le point neutre. `master_spatial` vérifie sur du FEL apparié que changer uniquement le MS laisse aujourd’hui le rendu bit à bit identique, avec le champ conservé et déclaré non appliqué dans les deux familles.

Le filtre natif de récupération de contraste libplacebo a été essayé à part, avec le plan de tone mapping LLDV de 4 000 vers 1 000 nits, neuf mires 64×64, une carte bicubique 19×19 et une force de 0,15. Les aplats, le noir exact et la mire sans compression restent identiques. Le filtre change aussi les bords 2/5 nits (0,0173 nit au maximum) et 50/150 nits (0,466 nit). Un bord 2/1 600 nits perd jusqu’à 0,0715 nit côté sombre et les bandes 1 200/1 800 nits varient jusqu’à 7,39 nits. Ce filtre agit en dehors des hautes lumières. Le MS Weight reste conservé sans exécution dans le moteur LLDV.

La qualification Dolby demande deux rendus de la même source à la même cible HDR, pour chaque famille, en ne changeant que Tone Detail. Les tests doivent mesurer le contraste local dans les hautes lumières, les écarts côté sombre d’un bord, les aplats, le noir et la stabilité sur une séquence. Le téléchargement de CM Offline requiert une session Dolby Customer. [Guide CM Offline](https://customer.dolby.com/content-creation-and-delivery/dolby-vision-professional-tools-v564/documentation/user-guide/cm-offline) · [Téléchargement Dolby](https://customer.dolby.com/content-creation-and-delivery/dolby-vision-professional-tools-v564/)

### Packing 4:2:2 hors ligne

Le packing convertit le RGB linéaire du moteur vers le BT.2020, puis applique le PQ à partir du pic de la cible. Le filtre horizontal à trois coefficients [1, 2, 1] est centré sur le pixel pair. Les mots Y et Cb/Cr sont quantifiés en plage limitée à 10 ou 12 bits. En 10 bits, l’arrondi précède l’ajout des deux zéros de poids faible. Le résultat reprend la disposition des octets des mires dans une texture RGBA8 linéaire. [ITU-R BT.2100](https://www.itu.int/rec/R-REC-BT.2100-3-202502-I/en)

Le test compare les codes dépaquetés à un calcul indépendant en double précision. Il couvre les trois gamuts cibles, les noirs et blancs, les couleurs saturées, la phase de chroma, l’inversion verticale, les refus de format et le retour du 12 au 10 bits. Les tests hors écran comparent les pixels HDR10 et SDR avant et après le packing, puis le retour du framebuffer 4K au Dolby Vision TV-led. Le panneau est vérifié avec des présentations simulées.

Les trois essais ciblés passent aussi sur l’iGPU Intel du N100 (Mesa 26.2.3) avec un contexte EGL hors écran. Sur une mire RGB linéaire 4K déjà en mémoire, le packing seul prend 17,32 ms GPU de médiane aux deux profondeurs. Le P95 est de 17,35 ms en 10 bits et 17,32 ms en 12 bits sur 48 mesures par profondeur après échauffement. La cadence du circuit complet reste à qualifier. Les 12 bits reçus par la LG et les couleurs de la dalle restent à mesurer avant le raccordement à HDMI.

### Optimisation du packing et cadence mesurée sur le N100

Le commit `e2d54a9` calcule les deux pixels d’une paire dans une seule invocation GLES 3.1 quand la texture RGBA8 de sortie est immuable. Il réutilise le shader PQ stable de libplacebo et les mêmes règles YCbCr et d’arrondi que le packing raster. La médiane murale sur la mire 4K passe de **17,97 à 10,77 ms** aux deux profondeurs, sur 48 mesures par profondeur avec synchronisation GPU. L’essai à deux passes avec une texture PQ intermédiaire coûtait 22,42 ms GPU contre 17,32 ms pour le raster. L’essai avec mémoire partagée coûtait 15,20 ms en moyenne murale. [Documentation GLES](https://registry.khronos.org/OpenGL-Refpages/es3.1/html/glBindImageTexture.xhtml)

Deux images 4K P5 et deux images 4K FEL ont été comparées à 10 et 12 bits sur ADL-N. Les 132 710 400 mots Y/C du raster restent identiques. Le calcul par paire change 19 mots, d’un code utile chacun. Sur ces 19 positions, l’oracle CPU en double précision situe chaque valeur à moins de 0,0025 code du seuil de demi-arrondi. Les mires vérifient aussi le padding 10 bits, la phase de chroma, les trois gamuts, l’inversion verticale, les refus et la restauration des états GL sur le N100 et llvmpipe.

Le banc VAAPI/EGL couvre le décodage, l’import, la reconstruction, le mapping et le packing à la résolution native. Il conserve jusqu’à trois images en vol. Après 120 images d’échauffement, les échéances sont dérivées des PTS avec 100 ms d’avance et vérifiées à l’observation des fences. Les mesures couvrent trois fenêtres de 300 images, avant composition Kodi et présentation HDMI.

| Extrait 4K | Moteur seul | Raster 10 bits | Par paire 10 bits | Par paire 12 bits | Fences observées après l’échéance |
| --- | ---: | ---: | ---: | ---: | --- |
| P5 à 30 i/s | 57,31 i/s | 27,49 i/s | 34,29 i/s | 33,30 i/s | 0/900 à chaque profondeur |
| P7 FEL lourd · 1917 à 30 i/s | 28,06 i/s | 18,66 i/s | 20,82 i/s | 20,80 i/s | 897/900 à chaque profondeur |
| P7 FEL lourd · 1917 original | — | — | — | 21,21 i/s | 891/900 |
| P7 FEL · mire CM4 V4 | — | — | — | 24,66 i/s | 0/900 à la cadence de la source |
| P8.4 · Sol Levante | — | — | — | 29,07 i/s | 0/900 à la cadence de la source |

La grille de reconstruction chroma FEL coûte environ 10 ms dans le profil sérialisé, devant les passes verticales EL à environ 3,4 ms en luma et 1,9 ms en chroma et la passe de résolution chroma à 2,4 ms. Les prototypes de stockage vertical FP16 exact, de table de prédiction luma, de dépaquetage fusionné et de regroupement des lectures horizontales ont donné respectivement 21,01, 21,27, 20,94 et 20,56 i/s pour le FEL lourd avec packing. La cible de 30 i/s sur cet extrait reste ouverte. Les décisions de fidélité attendent toujours les mesures physiques de A.

Le commit `ee86cb0` prépare le sélecteur Kodi à distinguer les valeurs natives et forcées exposées par DRM. L’option forcée est identifiée à partir de l’enum `YCbCr 4:2:2 10 bits forced` et la route active vient de la valeur relue sur le connecteur. Les tests simulent les deux annonces, vérifient l’ordre du choix automatique et refusent une annonce sans état actif correspondant. La programmation du forçage par pilote reste dans l’étape E.

### Phases verticales FEL regroupées

Le shader commun calcule les deux phases verticales en réutilisant les taps de l’EL. Il stocke les deux codes sur 11 bits dans un texel FP32 à la hauteur de l’EL, puis le filtre horizontal récupère la phase de la ligne. La plage est bornée par la profondeur de stockage et le décalage déclarés. Les formats qui laissent plus de 10 bits accessibles et les rendus qui filtrent les lignes actives conservent le stockage par ligne. Les coefficients et les arrondis sont partagés.

| 1917 FEL 4K à 30 i/s sur N100 | Avant | Après | Fences hors échéance après |
| --- | ---: | ---: | ---: |
| 4:2:2 10 bits | 20,83 i/s | 21,49 i/s | 896/900 |
| 4:2:2 12 bits | 20,81 i/s | 21,55 i/s | 896/900 |

Les mesures couvrent le décodage jusqu’au packing, sur 900 images après 120 d’échauffement, avec les mêmes conditions de file et d’échéance. Le gain est de 1,49 à 1,65 ms par image. Trois images 4K échantillonnées sont identiques octet pour octet dans le rendu linéaire et le packing, aux deux profondeurs. Le test spatial compare aussi les mêmes codes EL en 8 et 10 bits dans des formats de stockage qui exercent les deux chemins. Revue arithmétique Astra xhigh. La mesure Radeon reste à faire.

En 12 bits sur 300 images après 60 d’échauffement, l’extrait FEL CM4 V4 passe de 24,64 à 26,82 i/s. L’extrait P5 reste à 33,6 i/s. Aucun des deux extraits ne dépasse son échéance à sa cadence source.

Les deux fusions du rendu avec le packing ont ramené l’essai de 300 images à 17,29 et 15,75 i/s. La prédiction MMR en virgule flottante avec repli entier et le regroupement entier de Cb/Cr ont donné 20,38 et 21,44 i/s sur le même essai. Les trames analysées de 1917 emploient du MMR chroma d’ordre 3 et contiennent des variations BL et EL dans les marges signalées par L5. Le banc complet reste à environ 46,4 ms par image pour un budget de 33,3 ms à 30 i/s.

## 4. Brancher le circuit dans Kodi et sécuriser les bascules

**Propriétaires.** `DVOutputSettings.h`, `DVOutputSelection.h`, `DVPlaybackModes.cpp`, `DVPlaybackInfo.h` et `CWinSystemGbmGLESContext`, dans leurs patches Kodi existants. Côté moteur, ajouter le mode dans `CB1/src/dvbridge_policy.h` et son identité dans `CB1/src/cb1_circuit.c`. Côté HDMI, réutiliser `CDRMAtomic::FlipPageTransactional()` et la propriété déjà testée.

- [ ] Étendre les tests existants des défauts et du sélecteur. Le nouveau choix est réservé aux sources DV admises. Le défaut s’applique au fichier suivant et le choix à la volée à la lecture en cours. Le circuit peut être proposé depuis l’accueil à 60 Hz si la TV et le pilote sont compatibles et que Kodi peut atteindre le timing de lecture qualifié. La disponibilité en cours de lecture suit le timing effectivement utilisable.
- [ ] Intégrer le mode au même parcours de sélection et de révision. Avant présentation, vérifier le format demandé, la cible et la capacité du pilote. Valider ensemble le premier framebuffer LLDV, la propriété du connecteur et le retrait des états HDR ou TV-led incompatibles. Déclarer le circuit actif après confirmation de la présentation.
- [ ] Réutiliser la restauration DRM et tester un refus de transaction, une déconnexion et une reprise, un seek, une pause, un arrêt et le passage au fichier suivant. Les bascules LLDV ↔ HDR10 et LLDV ↔ TV-led doivent rendre une image et récupérer le dernier état utilisable en cas d’échec. Vérifier aussi le retour SDR et l’absence de résidu LLDV sur les autres circuits.
- [ ] Vérifier la composition des sous-titres et de l’interface. Dans le panneau Info via **O**, indiquer le circuit, le format actif et les trims appliqués avec les règles de lisibilité existantes. Commit local.

Le panneau **O** et sa télémétrie LLDV sont préparés hors ligne. La synthèse demande une image rendue, la même identité côté présentation et une relecture du format actif. Elle utilise les données source de cette image. Le panneau indique le 4:2:2, distingue la précision utile des champs HDMI de 12 bits, affiche la cible et les trims actifs, et signale le CM4 ajouté localement à part. Les tests injectent une présentation simulée via le cache Kodi et couvrent le refus, une ancienne identité, les deux précisions et le retour aux circuits existants.

Le N100 répond sur le build RC4 Preview Update 3. Son inventaire USB et celui du poste Windows ne montrent aucun périphérique de capture HDMI ni de mesure de la dalle. La vérification des codes reçus et des couleurs reste ouverte. La présentation LLDV réelle attend cette qualification.

## 5. Valider l’ensemble avant le PR

- [ ] Rejouer les tests ciblés sur les sources appariées, la suite CB1 et les contrôles de staging. Rejouer les patches avec zéro fuzz, compiler le noyau et Kodi, puis démarrer le build local sur le N100.
- [ ] Lire des extraits réels P5, P7 FEL, P7 MEL et P8 en 4K24 et 23,976 Hz. Confirmer la profondeur, la signalisation et les mesures sur la LG. Mesurer les images perdues après stabilisation et tester les bascules dans les deux sens, y compris une lecture longue du FEL le plus lourd retenu.
- [ ] Étendre le 4:2:2 10 bits utiles à tous les pilotes pris en charge selon l’étape E. Vérifier la distinction natif/forcé dans le sélecteur et les chemins SDR/HDR/TV-led à chaque extension.
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
